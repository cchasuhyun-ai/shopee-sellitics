"""
매입세액 입력 (매입)
====================
부가가치세 신고서의 "매입세액" 항목을 사용자가 직접 입력할 수 있는 페이지입니다.
국세청 부가가치세 신고서 서식의 매입세액 구분을 그대로 따라가며, 입력한 공급가액/
세액을 바탕으로 합계와 차감계(공제받을 매입세액)를 입력하는 즉시 자동으로 계산해서
보여줍니다.

신용카드매출전표 등 수취명세서 제출분(일반매입/고정자산매입)은 '카드사용내역 입력'
탭에서 저장(확정)한 값이 있으면 자동으로 채워집니다. 계산 결과를 확인한 뒤 '저장'
버튼을 누르면 값이 확정되며, 확정된 매입세액은 '부가세 계산' 탭에서 자동으로
불러와 사용합니다.
"""

import io

import pandas as pd
import streamlit as st

from amount_input import amount_input
from pdf_processor import VAT_HALF_OPTIONS

st.title("매입세액 입력")
st.caption("매입 · 부가가치세 매입세액 계산")
st.write(
    "부가가치세 신고서의 매입세액 세부 항목을 입력하면, 합계와 공제받을 매입세액을 "
    "자동으로 계산해서 보여줍니다."
)

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
CARD_RECEIPT_ITEMS = [
    ("card_general", "신용카드매출전표 등 수취명세서 제출분 - 일반매입", "card_usage_general_supply", "card_usage_general_tax"),
    ("card_fixed_asset", "신용카드매출전표 등 수취명세서 제출분 - 고정자산매입", "card_usage_fixed_asset_supply", "card_usage_fixed_asset_tax"),
]
OTHER_DEDUCTIBLE_ITEMS = [
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
                supply = amount_input("공급가액", supply_key)
            with cols[2]:
                tax = amount_input("세액", tax_key)
        else:
            supply = 0
            with cols[1]:
                tax = amount_input("세액", tax_key)
        values[key] = {"label": label, "supply": supply, "tax": tax}
    return values


def render_card_receipt_items():
    """'카드사용내역 입력' 탭에서 확정한 값이 있으면 그 값을 그대로 사용하고, 없으면 직접 입력받습니다."""
    card_usage_confirmed = st.session_state.get("card_usage_confirmed", False)
    values = {}
    for key, label, supply_state_key, tax_state_key in CARD_RECEIPT_ITEMS:
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.markdown(label)
        if card_usage_confirmed:
            supply = float(st.session_state.get(supply_state_key, 0))
            tax = float(st.session_state.get(tax_state_key, 0))
            with cols[1]:
                st.markdown(f"{supply:,.0f}")
            with cols[2]:
                st.markdown(f"{tax:,.0f}")
        else:
            with cols[1]:
                supply = amount_input("공급가액", f"sec3_{key}_supply")
            with cols[2]:
                tax = amount_input("세액", f"sec3_{key}_tax")
        values[key] = {"label": label, "supply": supply, "tax": tax}
    if card_usage_confirmed:
        st.caption("'카드사용내역 입력' 탭에서 확정한 값입니다.")
    else:
        st.caption("'카드사용내역 입력' 탭에서 저장하면 이 항목에 값이 자동으로 채워집니다.")
    return values


def build_summary(all_deductible, non_deductible_values):
    """매입세액 항목들을 집계해서 (요약 표, 차감계) 를 반환합니다."""
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

    return pd.DataFrame(rows), net_tax_total


def render_purchase_results(period_label, summary_df, net_total):
    """계산 결과를 화면에 표시하고, 다운로드용 엑셀 버퍼를 반환합니다."""
    st.subheader(f"6. 확인 및 저장 - {period_label}")

    result_col1, result_col2 = st.columns(2)
    with result_col1:
        st.metric("공제받을 매입세액 (차감계)", f"{net_total:,.0f} 원")
    with result_col2:
        st.dataframe(summary_df, width='stretch', hide_index=True)

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="매입세액", index=False)
    excel_buffer.seek(0)
    return excel_buffer


confirmed = st.session_state.get("purchase_confirmed", False)

if not confirmed:
    # ------------------------------------------------------------------
    # 1) 신고 기간 선택
    # ------------------------------------------------------------------
    st.subheader("1. 과세기간 선택")
    period_col1, period_col2 = st.columns([1, 5])
    with period_col1:
        report_year = st.number_input(
            "과세연도", min_value=2000, max_value=2100, value=2026, step=1, key="period_year"
        )
    with period_col2:
        report_term = st.radio("과세기간", VAT_HALF_OPTIONS, horizontal=True)

    st.divider()

    st.subheader("2. 세금계산서 수취분")
    header_cols = st.columns([3, 1, 1])
    header_cols[1].markdown("**공급가액**")
    header_cols[2].markdown("**세액**")
    tax_invoice_values = render_item_inputs(TAX_INVOICE_ITEMS, "sec1")

    st.subheader("3. 예정신고 누락분 / 매입자발행 세금계산서")
    header_cols = st.columns([3, 1, 1])
    header_cols[1].markdown("**공급가액**")
    header_cols[2].markdown("**세액**")
    misc_values = render_item_inputs(MISC_ITEMS, "sec2")

    st.subheader("4. 그 밖의 공제매입세액")
    st.markdown(
        """
        <style>
        div.st-key-card_receipt_highlight {
            background-color: rgba(37, 99, 235, 0.06);
            border-radius: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="card_receipt_highlight", border=True):
        card_values = render_card_receipt_items()
    other_values = render_item_inputs(OTHER_DEDUCTIBLE_ITEMS, "sec3")

    st.subheader("5. 공제받지 못할 매입세액")
    non_deductible_values = render_item_inputs(NON_DEDUCTIBLE_ITEMS, "sec4")
    st.caption(
        "**참고** (개인사업자에게 주로 발생하는 불공제 항목 예시)\n"
        "- 공제받지 못할 매입세액: 사업과 무관한 지출(가사경비), 비영업용 소형승용차(개별소비세 "
        "과세대상, 8인승 이하 승용차) 구입·유지비, 거래처 접대비 관련 매입세액, 세금계산서를 "
        "받지 못했거나 필요적 기재사항이 부실한 매입 등\n"
        "- 공통매입세액 면세사업분: 과세·면세 겸용 사업자가 공통으로 사용한 매입 중 면세사업에 "
        "대응하는 매입세액\n"
        "- 대손처분받은 세액: 이미 대손세액공제를 받았던 매출채권을 이후 회수한 경우 등"
    )

    st.divider()

    all_deductible = {**tax_invoice_values, **misc_values, **card_values, **other_values}
    summary_df, net_tax_total = build_summary(all_deductible, non_deductible_values)
    period_label = f"{int(report_year)}년 {report_term}"

    excel_buffer = render_purchase_results(period_label, summary_df, net_tax_total)

    st.write("계산 결과 확인을 마쳤으면 '저장' 버튼을 눌러 매입세액을 확정하세요.")
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name=f"{period_label.replace(' ', '_')}_매입세액_입력결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("저장", type="primary"):
            st.session_state["purchase_tax_summary"] = summary_df
            st.session_state["purchase_tax_period"] = period_label
            st.session_state["purchase_tax_net_total"] = net_tax_total
            st.session_state["purchase_confirmed"] = True
            st.rerun()
else:
    st.success(
        f"{st.session_state.get('purchase_tax_period', '')} 값이 확정되어 저장되었습니다. "
        "'부가세 계산' 탭에서 이 값을 자동으로 불러옵니다."
    )
    st.divider()
    excel_buffer = render_purchase_results(
        st.session_state["purchase_tax_period"],
        st.session_state["purchase_tax_summary"],
        st.session_state["purchase_tax_net_total"],
    )
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name=f"{st.session_state['purchase_tax_period'].replace(' ', '_')}_매입세액_입력결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("다시 수정하기"):
            st.session_state["purchase_confirmed"] = False
            st.rerun()
