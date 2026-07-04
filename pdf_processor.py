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


def build_result_sheets(results_by_file: dict):
    """여러 PDF의 처리 결과를 취합해서 엑셀 시트용 DataFrame들을 만듭니다.

    results_by_file: {파일명: (page_tables, raw_records)}
    반환: (combined_df, sheet_data(dict), raw_df)
    """
    all_combined_tables = []
    sheet_data = {}
    all_raw_records = []

    for filename, (page_tables, raw_records) in results_by_file.items():
        for page_no, line_no, text in raw_records:
            all_raw_records.append((filename, page_no, line_no, text))

        if not page_tables:
            continue

        per_file_dfs = []
        for page_no, title, df in page_tables:
            df = df.copy()
            df.insert(0, "표제목", title)
            df.insert(0, "페이지", page_no)
            per_file_dfs.append(df)

            combined_df = df.copy()
            combined_df.insert(0, "출처파일", filename)
            all_combined_tables.append(combined_df)

        file_df = pd.concat(per_file_dfs, ignore_index=True, sort=False)
        safe_name = "".join(c for c in Path(filename).stem if c not in r'[]:*?/\\')[:31]
        sheet_data[safe_name or Path(filename).stem[:31]] = file_df

    combined_df = (
        pd.concat(all_combined_tables, ignore_index=True, sort=False)
        if all_combined_tables
        else pd.DataFrame({"안내": ["표로 인식된 내용이 없습니다. '원본텍스트' 시트를 확인하세요."]})
    )
    raw_df = pd.DataFrame(all_raw_records, columns=["출처파일", "페이지", "줄번호", "내용"])

    return combined_df, sheet_data, raw_df
