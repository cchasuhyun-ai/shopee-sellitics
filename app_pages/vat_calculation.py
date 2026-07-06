"""
부가세 계산 (부가세)
====================
'소포수령증 업로드', '그 밖의 매출 입력', '매입세액 입력' 탭에서 저장(확정)한
값을 그대로 모아서 부가가치세 신고 금액과 납부(환급)할 세액을 계산 결과로
요약해서 보여주는 페이지입니다. 이 화면에서는 값을 다시 입력하지 않으며,
각 탭에서 먼저 저장(확정)해야 정확한 계산 결과가 반영됩니다.

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

EXPORT_AMOUNT_COLUMN = "수출신고금액"

st.title("부가세 계산")
st.caption("부가세 · 매출/매입 취합 결과로 신고 금액 계산")
st.write(
    "'소포수령증 업로드', '그 밖의 매출 입력', '매입세액 입력' 탭에서 저장(확정)한 결과를 "
    "모아서 부가가치세 신고 금액과 납부(환급)할 세액 계산 결과를 요약해서 보여줍니다."
)

# ------------------------------------------------------------------
# 신고기간 선택 (영세율 매출 계산 시 기간 필터링에 사용)
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
# 각 탭에서 저장(확정)된 값 가져오기
# ------------------------------------------------------------------
missing_notices = []

zero_rate_base = 0.0
if st.session_state.get("sales_confirmed") and "confirmed_df" in st.session_state:
    sales_df = st.session_state["confirmed_df"]
    if "출처파일" in sales_df.columns:
        in_period_mask, amount_cols = apply_vat_period_filter(sales_df, period_start, period_end)
        base_col = EXPORT_AMOUNT_COLUMN if EXPORT_AMOUNT_COLUMN in amount_cols else (
            amount_cols[0] if amount_cols else None
        )
        if base_col:
            zero_rate_base = float(to_numeric_series(sales_df.loc[in_period_mask, base_col]).fillna(0).sum())
        else:
            missing_notices.append("'소포수령증 업로드' 데이터에서 금액 컬럼을 찾지 못했습니다.")
else:
    missing_notices.append("'소포수령증 업로드' 탭에서 저장(확정)된 매출 데이터가 없습니다.")

if st.session_state.get("other_sales_confirmed") and "other_sales_supply_total" in st.session_state:
    regular_sales_base = float(st.session_state["other_sales_supply_total"])
    regular_sales_tax = float(st.session_state["other_sales_tax_total"])
else:
    regular_sales_base = 0.0
    regular_sales_tax = 0.0
    missing_notices.append("'그 밖의 매출 입력' 탭에서 저장(확정)된 값이 없습니다.")

if "purchase_tax_net_total" in st.session_state:
    purchase_tax_total = float(st.session_state["purchase_tax_net_total"])
else:
    purchase_tax_total = 0.0
    missing_notices.append("'매입세액 입력' 탭에서 계산한 값이 없습니다.")

if missing_notices:
    st.warning(
        "다음 탭에서 값을 먼저 저장(확정)해야 정확한 계산 결과가 반영됩니다 "
        "(해당 사항이 없으면 0으로 계산됩니다):\n" + "\n".join(f"- {m}" for m in missing_notices)
    )

st.divider()

# ------------------------------------------------------------------
# 신고 금액 계산 결과
# ------------------------------------------------------------------
st.subheader("신고 금액 계산 결과")

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
    label="다운로드",
    data=excel_buffer,
    file_name=f"부가세계산_{int(vat_year)}년_{vat_half}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
