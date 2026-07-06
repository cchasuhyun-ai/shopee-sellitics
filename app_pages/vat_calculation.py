"""
부가세 계산 (부가세)
====================
매출(소포수령증 취합 결과)과 매입(매입세액 입력 결과)을 모아
부가가치세 신고 금액과 납부(환급)할 세액을 계산하는 페이지입니다.

Shopee 등 해외 플랫폼을 통한 해외배송 판매는 부가가치세법상 영세율(0%) 수출 매출로
처리하는 것을 기본값으로 합니다 (매출세액 0, 과세표준만 영세율 첨부서류에 반영).
"""

import io
from datetime import date

import pandas as pd
import streamlit as st

from pdf_processor import (
    VAT_HALF_OPTIONS,
    apply_vat_period_filter,
    get_vat_period,
    to_numeric_series,
)

st.title("부가세 계산")
st.caption("부가세 · 매출/매입 취합 결과로 신고 금액 계산")
st.write(
    "'소포수령증 업로드'(매출)와 '매입세액 입력'(매입) 화면의 결과를 모아서 "
    "부가가치세 신고 금액과 납부(환급)할 세액을 계산합니다."
)

# ------------------------------------------------------------------
# 0) 신고기간 선택 (소포수령증 업로드 화면과 동일한 기준)
# ------------------------------------------------------------------
st.subheader("신고기간")

today = date.today()
default_half_index = 0 if today.month <= 6 else 1

period_col1, period_col2 = st.columns([1, 5])
with period_col1:
    vat_year = st.number_input(
        "신고연도", min_value=2000, max_value=2100, value=today.year, step=1, key="vc_year"
    )
with period_col2:
    vat_half = st.radio(
        "신고기간(반기)", VAT_HALF_OPTIONS, index=default_half_index, horizontal=True, key="vc_half"
    )

period_start, period_end, filing_deadline = get_vat_period(int(vat_year), vat_half)
st.info(f"신고 대상기간: {period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d}  |  신고기한: {filing_deadline}")

st.divider()

# ------------------------------------------------------------------
# 1) 매출세액 - 영세율(해외배송/수출) 매출
# ------------------------------------------------------------------
st.subheader("1. 영세율 매출 (해외배송/수출)")
st.write(
    "Shopee 등 해외 플랫폼을 통한 해외배송 판매는 부가가치세법상 영세율(0%) 수출 매출로 처리됩니다. "
    "'소포수령증 업로드' 화면에서 취합·저장한 결과를 가져와 영세율 과세표준(공급가액)을 계산합니다. "
    "영세율이 적용되므로 이 매출에서 발생하는 매출세액은 0원입니다."
)

sales_df = None
sales_source = None
if st.session_state.get("sales_confirmed") and "confirmed_df" in st.session_state:
    sales_df = st.session_state["confirmed_df"]
    sales_source = "확정(저장)된 소포수령증 취합 결과"
elif "combined_df" in st.session_state:
    sales_df = st.session_state["combined_df"]
    sales_source = "소포수령증 취합 결과 (아직 저장 전 임시값)"

zero_rate_base = 0.0
have_sales_data = False

if sales_df is not None and "출처파일" in sales_df.columns:
    in_period_mask, amount_cols = apply_vat_period_filter(sales_df, period_start, period_end)
    excluded_count = int((~in_period_mask).sum())
    if excluded_count:
        st.warning(
            f"신고기간({period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d})을 벗어나거나 날짜를 "
            f"인식하지 못한 {excluded_count}건은 계산에서 제외했습니다."
        )

    if amount_cols:
        base_col = st.selectbox(
            "영세율 과세표준(공급가액)으로 사용할 컬럼을 선택하세요",
            amount_cols,
            key="vc_base_col",
        )
        zero_rate_base = float(to_numeric_series(sales_df.loc[in_period_mask, base_col]).fillna(0).sum())
        have_sales_data = True
        st.metric("영세율 과세표준(공급가액) 합계", f"{zero_rate_base:,.0f} 원")
        st.caption(f"({sales_source} 기준, 신고기간 내 {int(in_period_mask.sum())}건 합계)")
    else:
        st.warning("금액으로 인식되는 컬럼을 찾지 못했습니다. 아래에 직접 입력해주세요.")
else:
    st.info(
        "아직 '소포수령증 업로드'에서 취합된 매출 데이터가 없습니다. "
        "먼저 그 화면에서 취합하거나, 아래에 합계를 직접 입력하세요."
    )

if not have_sales_data:
    zero_rate_base = st.number_input(
        "영세율 과세표준(공급가액) 합계 (원) - 직접 입력",
        min_value=0.0,
        step=1000.0,
        key="vc_zero_rate_base_manual",
    )

st.divider()

# ------------------------------------------------------------------
# 2) 매출세액 - 그 밖의 과세(일반) 매출
# ------------------------------------------------------------------
st.subheader("2. 그 밖의 과세 매출 (일반, 10%, 해당 시 입력)")
st.write(
    "해외배송 외에 국내 판매 등 세율 10%가 적용되는 매출이 있다면 공급가액과 세액을 "
    "직접 입력하세요. 해당 사항이 없으면 0으로 두면 됩니다."
)

reg_col1, reg_col2 = st.columns(2)
with reg_col1:
    regular_sales_base = st.number_input(
        "과세 매출 공급가액 (원)", min_value=0.0, step=1000.0, key="vc_regular_base"
    )
with reg_col2:
    regular_sales_tax = st.number_input(
        "과세 매출 세액 (원)", min_value=0.0, step=100.0, key="vc_regular_tax"
    )

st.divider()

# ------------------------------------------------------------------
# 3) 매입세액 - '매입세액 입력' 탭 결과 가져오기
# ------------------------------------------------------------------
st.subheader("3. 매입세액 (공제받을 매입세액)")

if "purchase_tax_net_total" in st.session_state:
    purchase_tax_total = float(st.session_state["purchase_tax_net_total"])
    st.metric("매입세액(차감계)", f"{purchase_tax_total:,.0f} 원")
    st.caption(f"'매입세액 입력' 탭({st.session_state.get('purchase_tax_period', '')})에서 가져온 값입니다.")
else:
    st.warning("아직 '매입세액 입력' 탭에서 계산한 값이 없습니다. 먼저 그 화면에서 매입세액을 계산해주세요.")
    purchase_tax_total = st.number_input(
        "매입세액(차감계) (원) - 직접 입력",
        min_value=0.0,
        step=100.0,
        key="vc_purchase_tax_manual",
    )

st.divider()

# ------------------------------------------------------------------
# 4) 최종 계산
# ------------------------------------------------------------------
st.subheader("4. 신고 금액 계산 결과")

taxable_base_total = zero_rate_base + regular_sales_base
output_tax_total = regular_sales_tax  # 영세율분은 세액 0
payable_tax = output_tax_total - purchase_tax_total

summary_df = pd.DataFrame(
    [
        {"구분": "영세율 과세표준 (해외배송/수출)", "공급가액": zero_rate_base, "세액": 0},
        {"구분": "과세 매출 (일반, 10%)", "공급가액": regular_sales_base, "세액": regular_sales_tax},
        {"구분": "과세표준 및 매출세액 합계", "공급가액": taxable_base_total, "세액": output_tax_total},
        {"구분": "매입세액 (차감계)", "공급가액": None, "세액": purchase_tax_total},
        {"구분": "납부(환급)할 세액", "공급가액": None, "세액": payable_tax},
    ]
)

st.dataframe(summary_df, width='stretch', hide_index=True)

result_col1, result_col2, result_col3 = st.columns(3)
with result_col1:
    st.metric("과세표준 합계", f"{taxable_base_total:,.0f} 원")
with result_col2:
    st.metric("매출세액 합계", f"{output_tax_total:,.0f} 원")
with result_col3:
    if payable_tax >= 0:
        st.metric("납부할 세액", f"{payable_tax:,.0f} 원")
    else:
        st.metric("환급받을 세액", f"{-payable_tax:,.0f} 원")

st.caption(
    "※ 경감·공제세액, 가산세, 예정신고 미환급세액 등 세부 항목은 반영되지 않은 단순 계산 결과입니다. "
    "정확한 신고 금액은 홈택스 신고서 화면에서 최종 확인하시기 바랍니다."
)

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    summary_df.to_excel(writer, sheet_name="부가세계산", index=False)
excel_buffer.seek(0)

st.download_button(
    label="엑셀 파일 다운로드",
    data=excel_buffer,
    file_name=f"부가세계산_{int(vat_year)}년_{vat_half}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
