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
from datetime import date

import pandas as pd
import streamlit as st

import auth
import db
from amount_input import amount_input
from pdf_processor import RAW_DATA_UPLOAD_NOTICE, VAT_HALF_OPTIONS, get_vat_period

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

    st.caption(RAW_DATA_UPLOAD_NOTICE)

    return excel_buffer


confirmed = st.session_state.get("purchase_confirmed", False)

if not confirmed:
    # ------------------------------------------------------------------
    # 1) 신고 기간 선택
    # ------------------------------------------------------------------
    st.subheader("1. 과세기간 선택")
    today = date.today()
    period_col1, period_col2 = st.columns([1, 5])
    with period_col1:
        report_year = st.number_input(
            "과세연도", min_value=2000, max_value=2100, value=today.year, step=1, key="period_year"
        )
    with period_col2:
        report_term = st.radio("과세기간", VAT_HALF_OPTIONS, index=0, horizontal=True)

    period_start, period_end, filing_deadline = get_vat_period(int(report_year), report_term)
    st.info(f"신고 대상기간: {period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d}  |  신고기한: {filing_deadline}")

    # ------------------------------------------------------------------
    # DB 연결 및 이전 저장 결과 불러오기 (로그인한 사용자 단위로 구분)
    # ------------------------------------------------------------------
    db_ready = db.is_db_configured()
    user = auth.current_user()
    filing_id = None

    if not db_ready:
        st.caption("※ Supabase가 아직 연결되지 않아, 이번 브라우저 세션에서만 데이터가 유지됩니다.")
    else:
        filing_id = db.get_or_create_filing(
            user["user_id"], int(report_year), report_term, user["company_name"]
        )
        loaded_flag_key = f"_purchase_tax_db_loaded_{filing_id}"
        if loaded_flag_key not in st.session_state:
            st.session_state[loaded_flag_key] = True
            saved = db.load_purchase_tax(filing_id)
            if saved is not None:
                st.session_state["purchase_tax_summary"] = saved["summary_df"]
                st.session_state["purchase_tax_period"] = f"{int(report_year)}년 {report_term}"
                st.session_state["purchase_tax_net_total"] = saved["net_tax_total"]
                st.session_state["purchase_confirmed"] = True
                st.rerun()

    st.divider()

    st.subheader("2. 세금계산서 수취분")
    header_cols = st.columns([3, 1, 1])
    header_cols[1].markdown("**공급가액**")
    header_cols[2].markdown("**세액**")
    tax_invoice_values = render_item_inputs(TAX_INVOICE_ITEMS, "sec1")
    st.caption(
        "**홈택스에서 매입세금계산서 조회하는 방법**\n"
        "1. 홈택스(www.hometax.go.kr) 로그인 → 상단 메뉴 `조회/발급` → `전자세금계산서` → "
        "`목록조회(매입)`으로 이동합니다.\n"
        "2. 조회 기간을 과세기간으로 설정하고 "
        "조회하면 발급받은 매입세금계산서 목록과 공급가액·세액 합계를 확인할 수 있습니다.\n"
        "3. 결과를 엑셀로 다운로드해 공급가액·세액 합계를 위 표에 입력하세요. 종이(수기)로 받은 "
        "세금계산서는 홈택스에 조회되지 않으므로 별도로 합산해야 합니다.\n"
        "4. 고정자산(비품·인테리어·차량 등) 매입분은 '세금계산서 수취분 - 고정자산 매입' 항목에 "
        "별도로 구분해 입력하세요."
    )

    st.subheader("3. 예정신고 누락분 / 매입자발행 세금계산서")
    header_cols = st.columns([3, 1, 1])
    header_cols[1].markdown("**공급가액**")
    header_cols[2].markdown("**세액**")
    misc_values = render_item_inputs(MISC_ITEMS, "sec2")
    st.caption(
        "**참고**\n"
        "- 예정신고 누락분: 직전 예정신고(또는 확정신고) 때 반영하지 못한 매입세금계산서가 있다면 "
        "해당 확정신고에 함께 반영하는 항목입니다. 위 '홈택스에서 매입세금계산서 조회하는 방법'과 "
        "동일하게 조회하되, 조회 기간을 누락분이 발생한 과거 기간으로 바꿔서 확인하세요.\n"
        "- 매입자발행 세금계산서: 거래상대방이 세금계산서를 발급해주지 않아 관할 세무서의 확인을 받아 "
        "매입자가 직접 발행한 경우입니다. 홈택스 로그인 → `조회/발급` → `전자세금계산서` → "
        "`매입자발행세금계산서 발행` 메뉴에서 처리 및 조회할 수 있습니다."
    )

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
    if not st.session_state.get("card_usage_confirmed", False):
        st.caption(
            "**홈택스에서 신용카드매출전표 등 수취내역 조회하는 방법**\n"
            "국세청 홈택스에 사업용신용카드로 등록해둔 카드라면, 홈택스 로그인 → `조회/발급` → "
            "`현금영수증·신용카드` → `사업용신용카드 사용내역 조회` 메뉴에서 매입세액공제 대상 여부까지 "
            "함께 확인할 수 있습니다. 직접 입력하는 대신 '카드사용내역 입력' 탭에서 파일을 업로드하고 "
            "저장하면 이 항목에 자동으로 반영됩니다."
        )
    other_values = render_item_inputs(OTHER_DEDUCTIBLE_ITEMS, "sec3")
    st.caption(
        "**참고** (그 밖의 공제매입세액 중 자주 발생하는 항목)\n"
        "- 의제매입세액: 면세로 공급받은 농·축·수산물 등을 원재료로 사용한 경우 공제받는 세액으로, "
        "홈택스에서 자동 조회되지 않고 매입 자료를 근거로 직접 계산해서 입력해야 합니다.\n"
        "- 재활용폐자원 등 매입세액: 폐자원 등을 사업자가 아닌 자로부터 매입한 경우로, 역시 직접 계산이 "
        "필요합니다.\n"
        "- 위 항목들은 관련 매입 사실이 없다면 0으로 두면 됩니다."
    )

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

            if filing_id:
                db.save_purchase_tax(filing_id, summary_df, net_tax_total)

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
