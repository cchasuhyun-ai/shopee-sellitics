"""
매입세액 입력 (매입)
====================
부가가치세 신고서의 "매입세액" 항목을 사용자가 직접 입력할 수 있는 페이지입니다.
국세청 부가가치세 신고서 서식의 매입세액 구분을 그대로 따라가며,
입력한 공급가액/세액을 바탕으로 합계와 차감계(공제받을 매입세액)를 자동으로 계산합니다.
"""

import io

import pandas as pd
import streamlit as st

st.title("매입세액 입력")
st.caption("매입 · 부가가치세 매입세액 계산")
st.write(
    "부가가치세 신고서의 매입세액 세부 항목을 입력하면, 합계와 공제받을 매입세액을 "
    "자동으로 계산해서 보여줍니다."
)

# ------------------------------------------------------------------
# 신고 기간 선택
# ------------------------------------------------------------------
period_col1, period_col2 = st.columns(2)
with period_col1:
    report_year = st.number_input("과세연도", min_value=2000, max_value=2100, value=2026, step=1)
with period_col2:
    report_term = st.selectbox("과세기간", ["1기 예정", "1기 확정", "2기 예정", "2기 확정"])

st.divider()

# 항목 정의: (세션 상태 키, 표시명, 공급가액 입력 여부)
TAX_INVOICE_ITEMS = [
    ("tax_invoice_general", "세금계산서 수취분 - 일반매입", True),
    ("tax_invoice_deferred", "세금계산서 수취분 - 수출기업 수입분 납부유예", True),
    ("tax_invoice_fixed_asset", "세금계산서 수취분 - 고정자산 매입", True),
]
MISC_ITEMS = [
    ("missed_report", "예정신고 누락분", True),
    ("buyer_issued_invoice", "매입자발행 세금계산서", True),
]
OTHER_DEDUCTIBLE_ITEMS = [
    ("card_general", "신용카드매출전표 등 수취명세서 제출분 - 일반매입", True),
    ("card_fixed_asset", "신용카드매출전표 등 수취명세서 제출분 - 고정자산매입", True),
    ("deemed_purchase", "의제매입세액", True),
    ("recycling", "재활용폐자원 등 매입세액", True),
    ("taxable_conversion", "과세사업전환 매입세액", False),
    ("inventory", "재고매입세액", False),
    ("bad_debt_relief", "변제대손세액", False),
    ("foreign_tourist_refund", "외국인관광객에 대한 환급세액", False),
]
NON_DEDUCTIBLE_ITEMS = [
    ("non_deductible", "공제받지 못할 매입세액", True),
    ("common_exempt", "공통매입세액 면세사업분", True),
    ("bad_debt_disposed", "대손처분받은 세액", False),
]


def render_item_inputs(items, section_key):
    """항목 목록을 받아 공급가액/세액 입력 위젯을 그리고, 입력값 딕셔너리를 반환합니다."""
    values = {}
    for key, label, has_supply in items:
        cols = st.columns([3, 1, 1]) if has_supply else st.columns([3, 2])
        with cols[0]:
            st.markdown(label)
        supply_key = f"{section_key}_{key}_supply"
        tax_key = f"{section_key}_{key}_tax"
        if has_supply:
            with cols[1]:
                supply = st.number_input(
                    "공급가액", min_value=0, step=1000, key=supply_key, label_visibility="collapsed"
                )
            with cols[2]:
                tax = st.number_input(
                    "세액", min_value=0, step=100, key=tax_key, label_visibility="collapsed"
                )
        else:
            supply = 0
            with cols[1]:
                tax = st.number_input(
                    "세액", min_value=0, step=100, key=tax_key, label_visibility="collapsed"
                )
        values[key] = {"label": label, "supply": supply, "tax": tax}
    return values


with st.form("purchase_tax_form"):
    st.subheader("세금계산서 수취분")
    header_cols = st.columns([3, 1, 1])
    header_cols[1].markdown("**공급가액**")
    header_cols[2].markdown("**세액**")
    tax_invoice_values = render_item_inputs(TAX_INVOICE_ITEMS, "sec1")

    st.subheader("예정신고 누락분 / 매입자발행 세금계산서")
    header_cols = st.columns([3, 1, 1])
    header_cols[1].markdown("**공급가액**")
    header_cols[2].markdown("**세액**")
    misc_values = render_item_inputs(MISC_ITEMS, "sec2")

    with st.expander("그 밖의 공제매입세액 (펼쳐서 입력)"):
        other_values = render_item_inputs(OTHER_DEDUCTIBLE_ITEMS, "sec3")

    with st.expander("공제받지 못할 매입세액 (펼쳐서 입력)"):
        non_deductible_values = render_item_inputs(NON_DEDUCTIBLE_ITEMS, "sec4")

    submitted = st.form_submit_button("계산하기", type="primary")

if submitted:
    all_deductible = {**tax_invoice_values, **misc_values, **other_values}

    deductible_supply_total = sum(v["supply"] for v in all_deductible.values())
    deductible_tax_total = sum(v["tax"] for v in all_deductible.values())

    non_deductible_supply_total = sum(v["supply"] for v in non_deductible_values.values())
    non_deductible_tax_total = sum(v["tax"] for v in non_deductible_values.values())

    net_tax_total = deductible_tax_total - non_deductible_tax_total

    rows = []
    for v in all_deductible.values():
        rows.append({"구분": v["label"], "공급가액": v["supply"], "세액": v["tax"]})
    rows.append({"구분": "매입세액 합계", "공급가액": deductible_supply_total, "세액": deductible_tax_total})
    for v in non_deductible_values.values():
        rows.append({"구분": v["label"], "공급가액": v["supply"], "세액": v["tax"]})
    rows.append(
        {
            "구분": "공제받지 못할 매입세액 합계",
            "공급가액": non_deductible_supply_total,
            "세액": non_deductible_tax_total,
        }
    )
    rows.append({"구분": "차감계 (공제받을 매입세액)", "공급가액": None, "세액": net_tax_total})

    summary_df = pd.DataFrame(rows)

    st.session_state["purchase_tax_summary"] = summary_df
    st.session_state["purchase_tax_period"] = f"{int(report_year)}년 {report_term}"
    st.session_state["purchase_tax_net_total"] = net_tax_total

if "purchase_tax_summary" in st.session_state:
    st.divider()
    st.subheader(f"계산 결과 - {st.session_state['purchase_tax_period']}")

    result_col1, result_col2 = st.columns(2)
    with result_col1:
        st.metric("공제받을 매입세액 (차감계)", f"{st.session_state['purchase_tax_net_total']:,.0f} 원")
    with result_col2:
        st.dataframe(st.session_state["purchase_tax_summary"], width='stretch', hide_index=True)

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        st.session_state["purchase_tax_summary"].to_excel(writer, sheet_name="매입세액", index=False)
    excel_buffer.seek(0)

    st.download_button(
        label="엑셀 파일 다운로드",
        data=excel_buffer,
        file_name=f"매입세액_{st.session_state['purchase_tax_period']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("항목을 입력한 뒤 '계산하기' 버튼을 눌러주세요.")
