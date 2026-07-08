"""
저장된 신고내역 (신고)
========================
지금까지 저장(확정)한 신고 건(연도/반기) 목록을 보여주고, 각 신고 건을 저장 당시
값으로 다시 계산해서 '부가세 계산' 결과 엑셀을 다시 받을 수 있는 페이지입니다.

소포수령증 PDF, 카드사용내역 원본 파일 자체는 DB에 보관하지 않으므로, 여기서
다운로드되는 엑셀은 저장 시점에 확정된 공급가액/세액 등의 값으로 다시 계산한
결과입니다.
"""

import io

import pandas as pd
import streamlit as st

import auth
import db
from pdf_processor import apply_vat_period_filter, get_vat_period, to_numeric_series
from vat_summary import EXPORT_AMOUNT_COLUMN, build_vat_summary

st.title("저장된 신고내역")
st.caption("신고 · 저장된 신고 건 목록 조회 및 재다운로드")
st.write(
    "지금까지 저장(확정)한 신고 건의 목록입니다. 신고 건을 선택하면 저장 당시 값으로 "
    "다시 계산한 '부가세 계산' 결과를 엑셀로 다시 받을 수 있습니다."
)

if not db.is_db_configured():
    st.warning("Supabase가 아직 연결되지 않아 저장된 신고내역을 볼 수 없습니다.")
    st.stop()

user = auth.current_user()
filings = db.list_filings(user["user_id"])

if not filings:
    st.info("아직 저장(확정)된 신고 건이 없습니다. 각 탭에서 값을 저장하면 여기에 표시됩니다.")
    st.stop()


def _label(filing: dict) -> str:
    updated = str(filing.get("updated_at") or "")[:16].replace("T", " ")
    return f"{filing['period_year']}년 {filing['period_half']} (마지막 저장: {updated})"


options = {_label(f): f for f in filings}
selected_label = st.selectbox("신고 건 선택", list(options.keys()))
selected = options[selected_label]

st.divider()

filing_id = selected["id"]
period_year = int(selected["period_year"])
period_half = selected["period_half"]
period_start, period_end, filing_deadline = get_vat_period(period_year, period_half)
st.info(f"신고 대상기간: {period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d}  |  신고기한: {filing_deadline}")

sales_saved = db.load_sales_upload(filing_id)
other_sales_saved = db.load_other_sales(filing_id)
purchase_saved = db.load_purchase_tax(filing_id)

missing_notices = []

zero_rate_base = 0.0
if sales_saved is None:
    missing_notices.append("'소포수령증 업로드' 탭에서 저장된 데이터가 없습니다.")
else:
    sales_df = sales_saved["confirmed_df"]
    if not sales_df.empty and "출처파일" in sales_df.columns:
        in_period_mask, amount_cols = apply_vat_period_filter(sales_df, period_start, period_end)
        base_col = EXPORT_AMOUNT_COLUMN if EXPORT_AMOUNT_COLUMN in amount_cols else (
            amount_cols[0] if amount_cols else None
        )
        if base_col:
            zero_rate_base = float(to_numeric_series(sales_df.loc[in_period_mask, base_col]).fillna(0).sum())
        else:
            missing_notices.append("'소포수령증 업로드' 저장 데이터에서 금액 컬럼을 찾지 못했습니다.")

if other_sales_saved is not None:
    regular_sales_base = float(other_sales_saved["supply_total"])
    regular_sales_tax = float(other_sales_saved["tax_total"])
else:
    regular_sales_base = 0.0
    regular_sales_tax = 0.0
    missing_notices.append("'그 밖의 매출 입력' 탭에서 저장된 값이 없습니다.")

if purchase_saved is not None:
    purchase_tax_total = float(purchase_saved["net_tax_total"])
else:
    purchase_tax_total = 0.0
    missing_notices.append("'매입세액 입력' 탭에서 저장된 값이 없습니다.")

if missing_notices:
    st.warning(
        "이 신고 건에는 아직 저장되지 않은 탭이 있습니다 (해당 사항이 없으면 0으로 계산됩니다):\n"
        + "\n".join(f"- {m}" for m in missing_notices)
    )

summary_df, taxable_base_total, output_tax_total, payable_tax = build_vat_summary(
    zero_rate_base, regular_sales_base, regular_sales_tax, purchase_tax_total
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

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    summary_df.to_excel(writer, sheet_name="부가세계산", index=False)
excel_buffer.seek(0)

st.caption(
    "※ 이 엑셀은 저장 당시 입력된 값으로 다시 계산한 결과입니다. 소포수령증 PDF, 카드사용내역 "
    "등 원본(raw) 파일 자체는 보관하지 않으므로 재다운로드되지 않습니다."
)

st.download_button(
    label="다운로드",
    data=excel_buffer,
    file_name=f"{period_year}년_{period_half}_부가세_계산결과.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
