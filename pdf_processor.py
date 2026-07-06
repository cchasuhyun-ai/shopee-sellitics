"""
pdf_processor.py
================
PDF에서 표를 추출하는 핵심 로직 모음입니다.
CLI 스크립트(pdf_to_excel.py)와 웹앱(app.py)이 이 모듈을 공용으로 가져다 씁니다.

동작 방식
---------
1) 텍스트가 있는 PDF: 글자의 좌표(x, y)를 기반으로 줄/칸을 재구성합니다.
2) 그 중 '표처럼 생긴 부분'(헤더 줄 + 같은 칸 수를 가진 데이터 줄들)을 자동으로 찾아서
   실제 컬럼명이 있는 깨끗한 표로 추출합니다.
3) 텍스트가 없는 스캔본 PDF는 Tesseract OCR로 줄 단위로 읽어옵니다.
"""

import re
from pathlib import Path

import pandas as pd
import pdfplumber

try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


def check_korean_ocr_support(lang: str = "kor+eng"):
    """필요한 언어 데이터가 설치되어 있는지 확인. 문제 있으면 경고 메시지 문자열 반환(없으면 None)."""
    if not OCR_AVAILABLE:
        return None
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return None
    needed = set(lang.split("+"))
    missing = needed - installed
    if missing:
        return (
            f"Tesseract에 다음 언어 데이터가 설치되어 있지 않습니다: {', '.join(missing)}. "
            f"현재 설치된 언어: {', '.join(sorted(installed)) or '없음'}"
        )
    return None


def make_unique_columns(cols):
    """컬럼명이 비어있거나(None/"") 중복되는 경우 자동으로 구분되도록 이름을 붙여줍니다."""
    seen = {}
    unique = []
    for i, c in enumerate(cols, start=1):
        name = (c or "").strip() if isinstance(c, str) else c
        if not name:
            name = f"col_{i}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        unique.append(name)
    return unique


def words_to_rows(words, line_bucket: float = 3.0, x_gap_threshold: float = 10.0):
    """단어들의 좌표를 이용해 줄(row)과 칸(cell)을 재구성합니다."""
    if not words:
        return []

    lines = {}
    for w in words:
        key = round(w["top"] / line_bucket) * line_bucket
        lines.setdefault(key, []).append(w)

    rows = []
    for top in sorted(lines.keys()):
        ws = sorted(lines[top], key=lambda w: w["x0"])
        cells = []
        current = [ws[0]["text"]]
        prev_x1 = ws[0]["x1"]
        for w in ws[1:]:
            gap = w["x0"] - prev_x1
            if gap > x_gap_threshold:
                cells.append(" ".join(current))
                current = [w["text"]]
            else:
                current.append(w["text"])
            prev_x1 = w["x1"]
        cells.append(" ".join(current))
        rows.append(cells)
    return rows


def extract_page_rows(page, x_gap_threshold: float = 10.0):
    words = page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False)
    return words_to_rows(words, x_gap_threshold=x_gap_threshold)


def detect_table_blocks(rows, min_cols: int = 2):
    """줄 단위 rows에서 '표처럼 생긴 구간'을 자동으로 찾아냅니다.
    반환: (tables, raw_lines)
    """
    def effective_len(row):
        return sum(1 for c in row if str(c).strip())

    tables = []
    used = [False] * len(rows)

    i = 0
    while i < len(rows) - 1:
        header_len = effective_len(rows[i])
        next_len = effective_len(rows[i + 1])
        if header_len >= min_cols and header_len == next_len:
            header = rows[i]
            data_rows = []
            j = i + 1
            while j < len(rows) and effective_len(rows[j]) == header_len:
                data_rows.append(rows[j])
                j += 1
            title = ""
            if i > 0 and not used[i - 1]:
                prev_text = " ".join(c for c in rows[i - 1] if str(c).strip())
                if effective_len(rows[i - 1]) == 1:
                    title = prev_text.strip()
            columns = make_unique_columns(header)
            df = pd.DataFrame(data_rows, columns=columns)
            tables.append({"title": title, "df": df})
            for k in range(i, j):
                used[k] = True
            i = j
        else:
            i += 1

    raw_lines = []
    for idx, row in enumerate(rows):
        if not used[idx]:
            text = " ".join(c for c in row if str(c).strip())
            if text.strip():
                raw_lines.append(text.strip())

    return tables, raw_lines


def extract_text_pdf(pdf_source, x_gap_threshold: float = 10.0):
    """텍스트가 있는 PDF를 처리.
    pdf_source: 파일 경로(str/Path) 또는 파일 객체(업로드된 파일 등 바이트 스트림) 모두 가능.
    반환: (page_tables, ocr_needed_pages, raw_records)
    """
    page_tables = []
    raw_records = []
    ocr_needed_pages = []
    with pdfplumber.open(pdf_source) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            if len(page.chars) == 0:
                ocr_needed_pages.append(i)
                continue
            rows = extract_page_rows(page, x_gap_threshold=x_gap_threshold)
            if not rows:
                ocr_needed_pages.append(i)
                continue
            tables, raw_lines = detect_table_blocks(rows)
            if not tables and not raw_lines:
                ocr_needed_pages.append(i)
                continue
            for t in tables:
                page_tables.append((i, t["title"], t["df"]))
            for idx, line in enumerate(raw_lines, start=1):
                raw_records.append((i, idx, line))
    return page_tables, ocr_needed_pages, raw_records


def extract_pages_with_ocr(pdf_path, page_numbers=None, dpi: int = 300, lang: str = "kor+eng"):
    """스캔본 페이지를 OCR로 줄 단위 텍스트 추출.
    pdf_path: 파일 경로(str/Path) - OCR은 pdf2image가 경로를 필요로 하므로 경로만 지원.
    반환: [(page_no, line_no, text), ...]
    """
    if not OCR_AVAILABLE:
        raise RuntimeError(
            "pytesseract / pdf2image가 설치되어 있지 않습니다. "
            "pip install pytesseract pdf2image 후 다시 시도하세요."
        )

    records = []
    if page_numbers is not None and len(page_numbers) == 0:
        return records

    if page_numbers is None:
        images = convert_from_path(str(pdf_path), dpi=dpi)
        page_image_pairs = list(enumerate(images, start=1))
    else:
        page_image_pairs = []
        for p in page_numbers:
            imgs = convert_from_path(str(pdf_path), dpi=dpi, first_page=p, last_page=p)
            page_image_pairs.append((p, imgs[0]))

    for page_no, image in page_image_pairs:
        text = pytesseract.image_to_string(image, lang=lang, config="--psm 4")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for idx, line in enumerate(lines, start=1):
            records.append((page_no, idx, line))

    return records


def process_pdf(pdf_path, force_ocr: bool = False, lang: str = "kor+eng"):
    """PDF 1개 처리. pdf_path는 디스크상의 실제 경로여야 합니다 (OCR 지원 위해).
    반환: (page_tables, raw_records)
    """
    pdf_path = Path(pdf_path)

    if force_ocr:
        raw_records = extract_pages_with_ocr(pdf_path, page_numbers=None, lang=lang)
        return [], raw_records

    page_tables, ocr_needed_pages, raw_records = extract_text_pdf(pdf_path)

    if ocr_needed_pages:
        ocr_records = extract_pages_with_ocr(pdf_path, page_numbers=ocr_needed_pages, lang=lang)
        raw_records.extend(ocr_records)

    return page_tables, raw_records


TARGET_TABLE_TITLE = "3.해외배송 내역"


def _normalize_title(title) -> str:
    """표제목 비교용: 공백 차이(예: "3. 해외배송  내역")를 무시하기 위해 공백을 모두 제거합니다."""
    return "".join(str(title).split())


def _is_target_table(title) -> bool:
    return _normalize_title(title) == _normalize_title(TARGET_TABLE_TITLE)


def _drop_empty_columns(df: pd.DataFrame, protect=()):
    """모든 값이 비어있는(NaN 또는 공백) 열을 제거합니다. 서로 다른 표를 이어붙이면서
    생기는 빈 열(다른 표에만 있던 칸)을 화면/엑셀에 보여주지 않기 위함입니다."""
    cols_to_drop = []
    for col in df.columns:
        if col in protect:
            continue
        stripped = df[col].astype(str).str.strip()
        is_empty = stripped.isin(["", "nan", "None"]) | df[col].isna()
        if is_empty.all():
            cols_to_drop.append(col)
    return df.drop(columns=cols_to_drop)


def build_result_sheets(results_by_file: dict):
    """여러 PDF의 처리 결과를 취합해서 엑셀 시트용 DataFrame들을 만듭니다.
    표제목이 "3.해외배송 내역"인 표만 결과에 포함하고, 그 결과 값이 전혀 들어오지 않는
    열은 표시하지 않습니다.

    results_by_file: {파일명: (page_tables, raw_records)}
    반환: (combined_df, sheet_data(dict), raw_df)
    """
    all_combined_tables = []
    sheet_data = {}
    all_raw_records = []

    for filename, (page_tables, raw_records) in results_by_file.items():
        for page_no, line_no, text in raw_records:
            all_raw_records.append((filename, page_no, line_no, text))

        target_tables = [t for t in page_tables if _is_target_table(t[1])]
        if not target_tables:
            continue

        per_file_dfs = []
        for page_no, title, df in target_tables:
            df = df.copy()
            df.insert(0, "표제목", title)
            df.insert(0, "페이지", page_no)
            per_file_dfs.append(df)

            combined_df = df.copy()
            combined_df.insert(0, "출처파일", filename)
            all_combined_tables.append(combined_df)

        file_df = pd.concat(per_file_dfs, ignore_index=True, sort=False)
        file_df = _drop_empty_columns(file_df, protect=("페이지", "표제목"))
        safe_name = "".join(c for c in Path(filename).stem if c not in r'[]:*?/\\')[:31]
        sheet_data[safe_name or Path(filename).stem[:31]] = file_df

    if all_combined_tables:
        combined_df = pd.concat(all_combined_tables, ignore_index=True, sort=False)
        combined_df = _drop_empty_columns(combined_df, protect=("출처파일", "페이지", "표제목"))
    else:
        combined_df = pd.DataFrame(
            {"안내": [f"표제목이 '{TARGET_TABLE_TITLE}'인 표를 찾지 못했습니다. '원본텍스트' 시트를 확인하세요."]}
        )
    raw_df = pd.DataFrame(all_raw_records, columns=["출처파일", "페이지", "줄번호", "내용"])

    return combined_df, sheet_data, raw_df


# ----------------------------------------------------------------------
# 부가세 신고기한(상반기/하반기) 판정 및 기간 외 데이터 배제
# ----------------------------------------------------------------------

VAT_DATE_COLUMN = "발행일"
VAT_HALF_OPTIONS = ("상반기", "하반기")
VAT_META_COLUMNS = ("출처파일", "페이지", "표제목")


def get_vat_period(year: int, half: str):
    """지정한 연도/반기의 부가세 신고 대상기간과 신고기한을 반환.
    반환: (period_start, period_end, filing_deadline_text)
    - 상반기(1~6월분): 신고기한 해당연도 7월 25일
    - 하반기(7~12월분): 신고기한 다음연도 1월 25일
    """
    if half == "상반기":
        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year, month=6, day=30)
        deadline = f"{year}년 7월 25일"
    else:
        start = pd.Timestamp(year=year, month=7, day=1)
        end = pd.Timestamp(year=year, month=12, day=31)
        deadline = f"{year + 1}년 1월 25일"
    return start, end, deadline


def parse_date_flexible(value):
    """'2026-01-15', '2026.01.15', '2026/01/15', '2026년1월15일', '20260115' 등
    다양한 표기의 날짜를 pandas Timestamp로 변환합니다. 인식 실패 시 NaT."""
    if value is None:
        return pd.NaT
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none"):
        return pd.NaT

    normalized = text.replace("년", "-").replace("월", "-").replace("일", "")
    normalized = re.sub(r"[./]", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip(" -")

    # 연-월-일 순서를 명시적으로 고정합니다. pd.to_datetime에 그냥 맡기면
    # "26-07-03"처럼 연도가 2자리인 표기를 "일-월-연"으로 잘못 해석해
    # (예: 2003-07-26으로 오인식) 전혀 다른 날짜가 되어버리는 문제가 있습니다.
    parts = normalized.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        year_text, month_text, day_text = parts
        try:
            year = int(year_text)
            if len(year_text) <= 2:
                year += 2000
            return pd.Timestamp(year=year, month=int(month_text), day=int(day_text))
        except (ValueError, TypeError):
            pass

    try:
        return pd.to_datetime(normalized)
    except (ValueError, TypeError):
        pass

    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        try:
            return pd.to_datetime(digits, format="%Y%m%d")
        except (ValueError, TypeError):
            pass

    return pd.NaT


def to_numeric_series(series: pd.Series) -> pd.Series:
    """'1,234' 같은 표기의 문자열 숫자 컬럼을 실수로 변환(콤마/공백 제거 후 변환)."""
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.replace(" ", "", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def detect_amount_columns(df: pd.DataFrame, exclude=()):
    """표 안에서 '금액류 숫자 컬럼'을 자동으로 찾아냅니다.
    (비어있지 않은 값 중 80% 이상이 숫자로 변환되는 컬럼을 금액 컬럼으로 판단)
    """
    amount_cols = []
    for col in df.columns:
        if col in exclude:
            continue
        raw = df[col].astype(str).str.strip()
        non_blank = raw[~raw.isin(["", "nan", "None"])]
        if len(non_blank) == 0:
            continue
        converted = to_numeric_series(non_blank)
        if converted.notna().mean() >= 0.8:
            amount_cols.append(col)
    return amount_cols


def apply_vat_period_filter(combined_df: pd.DataFrame, period_start, period_end, date_col: str = VAT_DATE_COLUMN):
    """combined_df의 각 행이 신고 대상기간(period_start~period_end) 안에 있는지 판정합니다.
    날짜를 인식하지 못하거나 기간을 벗어난 행은 기간 외(False)로 처리합니다.

    반환: (in_period_mask, amount_cols)
    """
    exclude = VAT_META_COLUMNS + (date_col,)
    amount_cols = detect_amount_columns(combined_df, exclude=exclude)

    if date_col not in combined_df.columns:
        return pd.Series(True, index=combined_df.index), amount_cols

    parsed_dates = combined_df[date_col].apply(parse_date_flexible)
    in_period_mask = parsed_dates.notna() & (parsed_dates >= period_start) & (parsed_dates <= period_end)
    return in_period_mask, amount_cols


def build_summary_row(combined_df: pd.DataFrame, in_period_mask: pd.Series, amount_cols, label_col: str = "출처파일"):
    """신고기간 내 행만 이용해 금액류 컬럼의 합계 행을 만듭니다."""
    summary = {}
    for col in combined_df.columns:
        if col == label_col:
            summary[col] = "합계 (신고기간 내)"
        elif col in amount_cols:
            total = to_numeric_series(combined_df.loc[in_period_mask, col]).fillna(0).sum()
            # 원본 금액 컬럼이 문자열("1,000" 등)이므로, 같은 컬럼 안에서 자료형이 섞이지
            # 않도록 합계도 동일한 문자열 형식(천단위 콤마)으로 맞춤
            summary[col] = f"{total:,.0f}"
        elif pd.api.types.is_numeric_dtype(combined_df[col]):
            # 숫자형이지만 금액 컬럼이 아닌 경우(예: 페이지 번호)는 빈 값(NaN)으로 두어
            # 엑셀/화면 표시 시 문자열과 섞여 자료형 오류가 나지 않게 함
            summary[col] = pd.NA
        else:
            summary[col] = ""
    return summary
