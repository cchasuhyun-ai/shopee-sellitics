"""
카드사용내역 입력 (매입)
========================
카드사 홈페이지에서 내려받은 카드사용내역 파일(엑셀/CSV)을 업로드하거나,
표에 직접 입력해서 카드사용내역을 정리할 수 있는 페이지입니다.

업로드한 파일은 원본 그대로 표로 보여주고, 그중 필요한 항목만 정제해
'카드사용내역 확인 및 저장' 표에 반영합니다. 이 표에서 직접 행을 추가하거나
인식된 내용을 수정할 수 있습니다.
'일반매입'과 '고정자산매입'으로 구분해 합계를 계산하고, '저장' 버튼을 누르면
값이 확정되어 '매입세액 입력' 탭의 "신용카드매출전표 등 수취명세서 제출분
(일반매입/고정자산매입)" 항목에 자동으로 반영됩니다.
"""

import io
from datetime import date

import pandas as pd
import streamlit as st

from pdf_processor import RAW_DATA_UPLOAD_NOTICE, VAT_HALF_OPTIONS, get_vat_period

st.title("카드사용내역 입력")
st.caption("매입 · 카드사용내역 업로드 및 입력")
st.write(
    "카드사 홈페이지에서 받은 카드사용내역 파일(엑셀/CSV)을 업로드하거나, "
    "표에 직접 입력해서 카드사용내역을 정리할 수 있습니다."
)

SOURCE_COLUMN = "출처"
MANUAL_ENTRY_COLUMNS = [SOURCE_COLUMN, "거래일자", "가맹점명", "사업자등록번호", "구분", "공급가액", "세액", "비고"]
CATEGORY_OPTIONS = ["일반매입", "고정자산매입"]

confirmed = st.session_state.get("card_usage_confirmed", False)

if "card_usage_manual_df" not in st.session_state:
    st.session_state["card_usage_manual_df"] = pd.DataFrame(columns=MANUAL_ENTRY_COLUMNS)
if "card_usage_processed_files" not in st.session_state:
    st.session_state["card_usage_processed_files"] = set()

# ------------------------------------------------------------------
# 1) 과세기간 선택
# ------------------------------------------------------------------
st.subheader("1. 과세기간 선택")

today = date.today()
default_half_index = 0 if today.month <= 6 else 1

period_col1, period_col2 = st.columns([1, 5])
with period_col1:
    vat_year = st.number_input(
        "신고연도", min_value=2000, max_value=2100, value=today.year, step=1, key="period_year"
    )
with period_col2:
    vat_half = st.radio(
        "신고기간(반기)", VAT_HALF_OPTIONS, index=default_half_index, horizontal=True, key="cu_half"
    )

period_start, period_end, filing_deadline = get_vat_period(int(vat_year), vat_half)
st.info(f"신고 대상기간: {period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d}  |  신고기한: {filing_deadline}")

st.divider()


def _read_uploaded_table(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 인코딩을 인식하지 못했습니다 (utf-8 / cp949 로 시도했습니다).")


def _read_uploaded_grid(uploaded_file):
    """카드사 파일 상단의 제목·요약정보 등을 그대로 둔 채, 헤더 없이 원본 그리드를 읽어옵니다."""
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data), header=None)
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), header=None, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 인코딩을 인식하지 못했습니다 (utf-8 / cp949 로 시도했습니다).")


def _drop_empty_columns(df: pd.DataFrame):
    cols_to_drop = []
    for col in df.columns:
        stripped = df[col].astype(str).str.strip()
        is_empty = stripped.isin(["", "nan", "None"]) | df[col].isna()
        if is_empty.all():
            cols_to_drop.append(col)
    return df.drop(columns=cols_to_drop)


# 카드사마다 열 이름이 제각각이라, 자주 쓰이는 표현을 표준 항목에 매핑합니다. 각 목록은 우선순위
# 순서이며(앞에 있을수록 먼저 선택), 사업자등록번호를 가맹점명보다 먼저 매칭해야 "가맹점사업자번호"
# 같은 열이 가맹점명으로 잘못 잡히지 않습니다.
_COLUMN_KEYWORDS = {
    "거래일자": [
        "매출일자", "매출일", "거래일자", "거래일", "이용일자", "이용일",
        "승인일자", "승인일", "매입일자", "매입일", "접수일자", "접수일",
    ],
    "사업자등록번호": ["사업자등록번호", "사업자번호", "가맹점사업자번호", "등록번호"],
    "가맹점명": ["가맹점명", "가맹점", "상호", "거래처명", "거래처", "사용처"],
    "공급가액": ["공급가액", "공급가"],
    "세액": ["부가가치세", "부가세액", "부가세", "세액"],
    "비고": ["비고", "메모", "적요"],
}
# 이용금액/매출금액은 보통 공급가액+세액 합계이고, 승인금액은 수수료 등이 더해질 수 있어 후순위로 둡니다.
_AMOUNT_KEYWORDS = [
    "이용금액", "매출금액", "합계금액", "결제금액", "사용금액", "매입금액", "청구금액", "승인금액", "금액",
]
_ALL_HEADER_KEYWORDS = {kw for keywords in _COLUMN_KEYWORDS.values() for kw in keywords} | set(_AMOUNT_KEYWORDS)


def _clean_column_name(col) -> str:
    return str(col).replace(" ", "").replace("\n", "")


def _find_header_row(grid: pd.DataFrame, max_scan: int = 30):
    """제목/요약정보가 위에 붙어있는 카드사 파일에서, 실제 열 이름이 있는 행을 찾습니다."""
    best_idx, best_score = None, 0
    for i in range(min(max_scan, len(grid))):
        score = sum(
            1
            for cell in grid.iloc[i]
            if _clean_column_name(cell) and any(keyword in _clean_column_name(cell) for keyword in _ALL_HEADER_KEYWORDS)
        )
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx if best_score >= 2 else None


def _extract_data_table(grid: pd.DataFrame) -> pd.DataFrame:
    """헤더 없이 읽은 원본 그리드에서 실제 열 이름 행을 찾아, 그 아래 데이터만 표로 만듭니다."""
    header_idx = _find_header_row(grid)
    if header_idx is None:
        header_idx = 0
    data = grid.iloc[header_idx + 1 :].copy()
    data.columns = grid.iloc[header_idx]
    return data.reset_index(drop=True)


def _normalize_uploaded_df(grid: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """카드사 파일마다 다른 열 이름을 표준 항목으로 매핑하고, 의미 없는 행/열을 제외합니다."""
    df = _extract_data_table(grid)
    matched_cols = set()
    result = pd.DataFrame(index=df.index)

    for target, keywords in _COLUMN_KEYWORDS.items():
        for keyword in keywords:
            found_col = None
            for col in df.columns:
                if col in matched_cols:
                    continue
                if keyword in _clean_column_name(col):
                    found_col = col
                    break
            if found_col is not None:
                result[target] = df[found_col]
                matched_cols.add(found_col)
                break

    def _find_amount_col():
        for keyword in _AMOUNT_KEYWORDS:
            for col in df.columns:
                if col in matched_cols:
                    continue
                if keyword in _clean_column_name(col):
                    return col
        return None

    has_supply = "공급가액" in result.columns
    has_tax = "세액" in result.columns

    # 공급가액/세액 중 하나 이상이 없으면 이용(합계)금액을 이용해 부족한 값을 채웁니다.
    if not has_supply or not has_tax:
        amount_col = _find_amount_col()
        if amount_col is not None:
            amount = pd.to_numeric(df[amount_col], errors="coerce")
            matched_cols.add(amount_col)
            if not has_supply and not has_tax:
                supply = (amount / 1.1).round()
                result["공급가액"] = supply
                result["세액"] = amount - supply
            elif not has_supply:
                result["공급가액"] = amount - pd.to_numeric(result["세액"], errors="coerce")
            elif not has_tax:
                result["세액"] = amount - pd.to_numeric(result["공급가액"], errors="coerce")

    for col in ["거래일자", "가맹점명", "사업자등록번호", "공급가액", "세액", "비고"]:
        if col not in result.columns:
            result[col] = pd.NA

    result["구분"] = "일반매입"
    result[SOURCE_COLUMN] = source_name

    # 의미 없는 행(합계/소계 행, 가맹점명·금액이 모두 비어있는 행) 제외
    # 날짜를 datetime으로 바꾸기 전에 걸러야 합니다. "합 계"처럼 날짜가 아닌 텍스트가 거래일자
    # 칸에 들어있는 경우, datetime 변환 시 NaT가 되어 텍스트 기반 판별이 불가능해지기 때문입니다.
    # NaN을 먼저 빈 문자열로 바꾼 뒤 문자열로 변환해야, pandas 버전에 따라 astype(str)이
    # NaN을 문자열 "nan"으로 바꾸지 않는 경우에도 빈 값이 올바르게 인식됩니다.
    merchant = result["가맹점명"].fillna("").astype(str).str.strip()
    supply_num = pd.to_numeric(result["공급가액"], errors="coerce")
    tax_num = pd.to_numeric(result["세액"], errors="coerce")
    # "합계"가 가맹점명이 아니라 거래일자 칸에 "합 계"처럼 공백과 함께 들어있는 카드사도 있어,
    # 두 열을 합쳐서(공백 제거 후) 합계/소계 행 여부를 판단합니다.
    summary_text = (
        result["거래일자"].fillna("").astype(str) + merchant
    ).str.replace(" ", "", regex=False)
    is_summary_row = summary_text.str.contains("합계|소계|총계|total", case=False, na=False, regex=True)
    is_blank_row = (merchant == "") & supply_num.isna() & tax_num.isna()
    result = result[~(is_summary_row | is_blank_row)]

    # 원본 파일을 헤더 없이 읽으면 열 전체가 문자열로 남는 경우가 있어, 숫자/날짜 열은 명시적으로
    # 변환합니다. 거래일자가 문자열(예: "2026.06.30")로 남아있으면 표의 DateColumn 설정과 타입이
    # 맞지 않아 화면 자체가 에러로 멈추므로 반드시 datetime으로 변환해야 합니다.
    result["공급가액"] = pd.to_numeric(result["공급가액"], errors="coerce")
    result["세액"] = pd.to_numeric(result["세액"], errors="coerce")
    result["거래일자"] = pd.to_datetime(result["거래일자"], errors="coerce")

    return result[MANUAL_ENTRY_COLUMNS].reset_index(drop=True)


# ------------------------------------------------------------------
# 2) 파일 업로드
# ------------------------------------------------------------------
st.subheader("2. 파일 업로드")
st.caption(
    "업로드한 파일은 아래에 표로 그대로 정리해서 보여주고, 그중 필요한 항목만 정제해 "
    "'3. 카드사용내역 확인 및 저장' 표에 반영합니다. 고정자산매입 건이 섞여 있다면 반영된 표에서 "
    "해당 행의 '구분'을 '고정자산매입'으로 바꿔주세요."
)
st.markdown(
    "**카드사 홈페이지에서 카드사용내역 받는 방법**\n"
    "1. 이용 중인 카드사(비씨/삼성/신한/국민/현대/롯데/우리/하나카드 등) 홈페이지에 로그인합니다. "
    "개인 명의 카드는 '마이페이지 > 이용내역조회', 법인·사업용카드는 '기업(카드)회원 > 이용내역조회' "
    "메뉴에서 확인할 수 있습니다.\n"
    f"2. 조회 기간을 이번 과세기간({period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d})으로 설정하고 "
    "'전체 이용내역'(또는 매입내역)을 조회합니다.\n"
    "3. 조회 결과를 엑셀(.xlsx) 또는 CSV 파일로 다운로드합니다. 거래일자, 가맹점명(상호), 공급가액, "
    "세액(부가가치세) 열이 포함된 파일이면 아래 업로드 시 자동으로 인식되며, 공급가액·세액이 별도로 "
    "없고 합계(이용)금액만 있는 파일도 자동으로 부가세를 역산해 반영합니다.\n"
    "4. 국세청 홈택스에 사업용신용카드로 등록해둔 카드라면, 홈택스 로그인 → 조회/발급 → "
    "현금영수증·신용카드 → 사업용신용카드 사용내역 조회 메뉴에서도 동일한 자료를 내려받을 수 있습니다.\n\n"
    "카드를 여러 장 사용 중이라면 카드(사)별로 각각 내려받아 모두 업로드하세요."
)

if not confirmed:
    uploaded_files = st.file_uploader(
        "카드사용내역 파일을 선택하세요 (엑셀 또는 CSV, 여러 개 선택 가능)",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="card_usage_uploader",
    )

    if uploaded_files:
        raw_parsed_dfs = []
        new_cleaned_rows = []
        for uploaded_file in uploaded_files:
            try:
                raw_df = _read_uploaded_table(uploaded_file)
            except Exception as e:
                st.error(f"'{uploaded_file.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")
                continue

            raw_display_df = raw_df.copy()
            raw_display_df.insert(0, "출처파일", uploaded_file.name)
            raw_parsed_dfs.append(raw_display_df)

            signature = (uploaded_file.name, uploaded_file.size)
            if signature not in st.session_state["card_usage_processed_files"]:
                try:
                    grid_df = _read_uploaded_grid(uploaded_file)
                    new_cleaned_rows.append(_normalize_uploaded_df(grid_df, uploaded_file.name))
                except Exception as e:
                    st.error(f"'{uploaded_file.name}' 파일을 정리하는 중 오류가 발생했습니다: {e}")
                st.session_state["card_usage_processed_files"].add(signature)

        if raw_parsed_dfs:
            uploaded_df = pd.concat(raw_parsed_dfs, ignore_index=True, sort=False)
            st.session_state["card_usage_uploaded_df"] = _drop_empty_columns(uploaded_df)

        if new_cleaned_rows:
            st.session_state["card_usage_manual_df"] = pd.concat(
                [st.session_state["card_usage_manual_df"], *new_cleaned_rows], ignore_index=True
            )
            st.success(f"{sum(len(d) for d in new_cleaned_rows)}건의 내역을 정리해 아래 '3. 카드사용내역 확인 및 저장' 표에 추가했습니다.")

if "card_usage_uploaded_df" in st.session_state:
    st.dataframe(st.session_state["card_usage_uploaded_df"], width='stretch')
elif not confirmed:
    st.info("카드사용내역 파일을 업로드하면 표로 정리해서 보여줍니다.")

st.divider()

# ------------------------------------------------------------------
# 3) 카드사용내역 확인 및 저장
# ------------------------------------------------------------------
st.subheader("3. 카드사용내역 확인 및 저장")
st.write(
    "업로드한 내역이 아래 표에 정리되어 표시됩니다. 잘못 인식된 값은 직접 수정하고, 업로드 파일에 "
    "없는 거래는 표 아래쪽의 + 로 행을 추가하세요. '구분' 열에서 일반매입/고정자산매입을 선택할 수 있습니다."
)

edited_df = st.data_editor(
    st.session_state["card_usage_manual_df"],
    num_rows="dynamic",
    width='stretch',
    column_config={
        SOURCE_COLUMN: st.column_config.TextColumn(SOURCE_COLUMN, disabled=True),
        "거래일자": st.column_config.DateColumn("거래일자"),
        "구분": st.column_config.SelectboxColumn("구분", options=CATEGORY_OPTIONS, default="일반매입"),
        "공급가액": st.column_config.NumberColumn("공급가액", min_value=0, step=100, format="%,d"),
        "세액": st.column_config.NumberColumn("세액", min_value=0, step=10, format="%,d"),
    },
    key="card_usage_manual_editor",
    disabled=confirmed,
)
st.session_state["card_usage_manual_df"] = edited_df

category = edited_df["구분"].fillna("일반매입")
supply = pd.to_numeric(edited_df["공급가액"], errors="coerce").fillna(0)
tax = pd.to_numeric(edited_df["세액"], errors="coerce").fillna(0)
is_fixed_asset = category == "고정자산매입"

general_supply_total = supply[~is_fixed_asset].sum()
general_tax_total = tax[~is_fixed_asset].sum()
fixed_asset_supply_total = supply[is_fixed_asset].sum()
fixed_asset_tax_total = tax[is_fixed_asset].sum()

total_col1, total_col2 = st.columns(2)
with total_col1:
    st.metric("일반매입 공급가액/세액", f"{general_supply_total:,.0f} 원 / {general_tax_total:,.0f} 원")
with total_col2:
    st.metric("고정자산매입 공급가액/세액", f"{fixed_asset_supply_total:,.0f} 원 / {fixed_asset_tax_total:,.0f} 원")

has_data = not edited_df.dropna(how="all").empty

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    (edited_df if has_data else pd.DataFrame(columns=MANUAL_ENTRY_COLUMNS)).to_excel(
        writer, sheet_name="카드사용내역", index=False
    )
excel_buffer.seek(0)

if confirmed:
    st.success(
        "값이 확정되어 저장되었습니다. '매입세액 입력' 탭의 신용카드매출전표 등 수취명세서 "
        "제출분(일반매입/고정자산매입) 항목에 자동으로 반영됩니다."
    )
    st.caption(RAW_DATA_UPLOAD_NOTICE)
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name=f"{int(vat_year)}년_{vat_half}_카드사용내역_입력결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("다시 수정하기"):
            st.session_state["card_usage_confirmed"] = False
            st.rerun()
elif has_data:
    st.write("내역 확인을 마쳤으면 '저장' 버튼을 눌러 값을 확정하세요.")
    st.caption(RAW_DATA_UPLOAD_NOTICE)
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name=f"{int(vat_year)}년_{vat_half}_카드사용내역_입력결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("저장", type="primary"):
            st.session_state["card_usage_general_supply"] = general_supply_total
            st.session_state["card_usage_general_tax"] = general_tax_total
            st.session_state["card_usage_fixed_asset_supply"] = fixed_asset_supply_total
            st.session_state["card_usage_fixed_asset_tax"] = fixed_asset_tax_total
            st.session_state["card_usage_confirmed"] = True
            st.rerun()
else:
    st.info("파일을 업로드하거나 직접 입력한 뒤 저장할 수 있습니다.")
