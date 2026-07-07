"""
카드사용내역 입력 (매입)
========================
카드사 홈페이지에서 내려받은 카드사용내역 파일(엑셀/CSV)을 업로드하거나,
표에 직접 입력해서 카드사용내역을 정리할 수 있는 페이지입니다.

업로드한 파일은 자동으로 정제되어 '카드사용내역 확인 및 저장' 표에 반영되며,
표에서 직접 행을 추가하거나 인식된 내용을 수정할 수 있습니다.
'일반매입'과 '고정자산매입'으로 구분해 합계를 계산하고, '저장' 버튼을 누르면
값이 확정되어 '매입세액 입력' 탭의 "신용카드매출전표 등 수취명세서 제출분
(일반매입/고정자산매입)" 항목에 자동으로 반영됩니다.
"""

import io
from datetime import date

import pandas as pd
import streamlit as st

from pdf_processor import VAT_HALF_OPTIONS, get_vat_period

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


# 카드사마다 열 이름이 제각각이라, 자주 쓰이는 표현을 표준 항목에 매핑합니다.
# 사업자등록번호를 먼저 매칭해야 "가맹점사업자번호" 같은 열이 가맹점명으로 잘못 잡히지 않습니다.
_COLUMN_KEYWORDS = {
    "거래일자": ["거래일자", "거래일", "이용일자", "이용일", "승인일자", "승인일", "매입일자", "매입일"],
    "사업자등록번호": ["사업자등록번호", "사업자번호", "가맹점사업자번호", "등록번호"],
    "가맹점명": ["가맹점명", "가맹점", "상호", "거래처명", "거래처", "사용처"],
    "공급가액": ["공급가액", "공급가"],
    "세액": ["부가가치세", "부가세액", "부가세", "세액"],
    "비고": ["비고", "메모", "적요"],
}
_AMOUNT_KEYWORDS = ["합계금액", "이용금액", "승인금액", "결제금액", "사용금액", "매입금액", "청구금액", "금액"]


def _clean_column_name(col) -> str:
    return str(col).replace(" ", "").replace("\n", "")


def _normalize_uploaded_df(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """카드사 파일마다 다른 열 이름을 표준 항목으로 매핑하고, 의미 없는 행/열을 제외합니다."""
    matched_cols = set()
    result = pd.DataFrame(index=df.index)

    for target, keywords in _COLUMN_KEYWORDS.items():
        for col in df.columns:
            if col in matched_cols:
                continue
            col_name = _clean_column_name(col)
            if any(keyword in col_name for keyword in keywords):
                result[target] = df[col]
                matched_cols.add(col)
                break

    # 공급가액/세액 열을 찾지 못했다면 이용(합계)금액에서 부가세를 역산합니다.
    if "공급가액" not in result.columns and "세액" not in result.columns:
        for col in df.columns:
            if col in matched_cols:
                continue
            col_name = _clean_column_name(col)
            if any(keyword in col_name for keyword in _AMOUNT_KEYWORDS):
                amount = pd.to_numeric(df[col], errors="coerce")
                supply = (amount / 1.1).round()
                result["공급가액"] = supply
                result["세액"] = amount - supply
                matched_cols.add(col)
                break

    for col in ["거래일자", "가맹점명", "사업자등록번호", "공급가액", "세액", "비고"]:
        if col not in result.columns:
            result[col] = pd.NA

    result["구분"] = "일반매입"
    result[SOURCE_COLUMN] = source_name

    # 의미 없는 행(합계/소계 행, 가맹점명·금액이 모두 비어있는 행) 제외
    # NaN을 먼저 빈 문자열로 바꾼 뒤 문자열로 변환해야, pandas 버전에 따라 astype(str)이
    # NaN을 문자열 "nan"으로 바꾸지 않는 경우에도 빈 값이 올바르게 인식됩니다.
    merchant = result["가맹점명"].fillna("").astype(str).str.strip()
    supply_num = pd.to_numeric(result["공급가액"], errors="coerce")
    tax_num = pd.to_numeric(result["세액"], errors="coerce")
    is_summary_row = merchant.str.contains("합계|소계|총계|total", case=False, na=False, regex=True)
    is_blank_row = (merchant == "") & supply_num.isna() & tax_num.isna()
    result = result[~(is_summary_row | is_blank_row)]

    return result[MANUAL_ENTRY_COLUMNS].reset_index(drop=True)


# ------------------------------------------------------------------
# 2) 파일 업로드
# ------------------------------------------------------------------
st.subheader("2. 파일 업로드")
st.caption(
    "업로드한 파일은 자동으로 정제되어 아래 '3. 카드사용내역 확인 및 저장' 표에 반영됩니다. "
    "고정자산매입 건이 섞여 있다면 반영된 표에서 해당 행의 '구분'을 '고정자산매입'으로 바꿔주세요."
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
        new_rows = []
        for uploaded_file in uploaded_files:
            signature = (uploaded_file.name, uploaded_file.size)
            if signature in st.session_state["card_usage_processed_files"]:
                continue
            try:
                raw_df = _read_uploaded_table(uploaded_file)
                cleaned_df = _normalize_uploaded_df(raw_df, uploaded_file.name)
                new_rows.append(cleaned_df)
                st.session_state["card_usage_processed_files"].add(signature)
            except Exception as e:
                st.error(f"'{uploaded_file.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")

        if new_rows:
            st.session_state["card_usage_manual_df"] = pd.concat(
                [st.session_state["card_usage_manual_df"], *new_rows], ignore_index=True
            )
            st.success(f"{sum(len(d) for d in new_rows)}건의 내역을 정리해 아래 표에 추가했습니다.")

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
