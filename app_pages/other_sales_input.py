"""
그 밖의 매출 입력 (매출)
========================
'소포수령증 업로드'에서 처리하는 해외배송(영세율) 매출 외에, 국내 판매 등으로
세금계산서·신용카드매출전표·현금영수증을 발행했거나 그 밖의 매출이 있는 경우
공급가액과 매출세액을 직접 입력하고, 관련 증빙(세금계산서, 카드매출전표,
현금영수증 등) 파일을 업로드해서 함께 보관할 수 있는 페이지입니다.

입력을 모두 마치고 '저장' 버튼을 누르면 값이 확정되며, 확정된 매출/매출세액은
'부가세 계산' 탭에서 자동으로 불러와 사용합니다.
"""

import io
from datetime import date

import pandas as pd
import streamlit as st

import auth
import db
from amount_input import amount_input
from pdf_processor import RAW_DATA_UPLOAD_NOTICE, VAT_HALF_OPTIONS, get_vat_period

st.title("그 밖의 매출 입력")
st.caption("매출 · 영세율 외 과세 매출 입력 및 증빙 업로드")
st.write(
    "'소포수령증 업로드' 화면에서 처리하는 해외배송(영세율) 매출 외에, 국내 판매 등으로 "
    "세금계산서·신용카드매출전표·현금영수증을 발행했거나 그 밖의 매출이 있다면 이 화면에서 "
    "공급가액과 매출세액을 입력하세요. 관련 증빙 파일도 함께 업로드해 보관할 수 있습니다."
)

OTHER_SALES_ITEMS = [
    ("tax_invoice", "세금계산서 발급분"),
    ("card_cash_receipt", "신용카드매출전표 · 현금영수증 발행분"),
    ("etc", "기타(정규영수증 외 매출분)"),
]

confirmed = st.session_state.get("other_sales_confirmed", False)

# ------------------------------------------------------------------
# 1) 신고기간 선택
# ------------------------------------------------------------------
st.subheader("1. 과세기간 선택")

today = date.today()
default_half_index = 0  # 기본값: 상반기

period_col1, period_col2 = st.columns([1, 5])
with period_col1:
    vat_year = st.number_input(
        "신고연도",
        min_value=2000,
        max_value=2100,
        value=today.year,
        step=1,
        key="period_year",
        disabled=confirmed,
    )
with period_col2:
    vat_half = st.radio(
        "신고기간(반기)",
        VAT_HALF_OPTIONS,
        index=default_half_index,
        horizontal=True,
        key="os_half",
        disabled=confirmed,
    )

period_start, period_end, filing_deadline = get_vat_period(int(vat_year), vat_half)
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
        user["user_id"], int(vat_year), vat_half, user["company_name"]
    )
    loaded_flag_key = f"_other_sales_db_loaded_{filing_id}"
    if loaded_flag_key not in st.session_state:
        st.session_state[loaded_flag_key] = True
        if not st.session_state.get("other_sales_confirmed"):
            saved = db.load_other_sales(filing_id)
            if saved is not None:
                summary_df = saved["summary_df"]
                for item_key, item_label in OTHER_SALES_ITEMS:
                    row = (
                        summary_df.loc[summary_df["구분"] == item_label]
                        if not summary_df.empty and "구분" in summary_df.columns
                        else pd.DataFrame()
                    )
                    supply_val = float(row["공급가액"].iloc[0]) if not row.empty else 0
                    tax_val = float(row["세액"].iloc[0]) if not row.empty else 0
                    st.session_state[f"amt_os_{item_key}_supply"] = f"{int(supply_val):,}"
                    st.session_state[f"amt_os_{item_key}_tax"] = f"{int(tax_val):,}"
                st.session_state["other_sales_summary"] = summary_df
                st.session_state["other_sales_supply_total"] = saved["supply_total"]
                st.session_state["other_sales_tax_total"] = saved["tax_total"]
                st.session_state["other_sales_evidence"] = saved["evidence_files"]
                st.session_state["other_sales_period"] = f"{int(vat_year)}년 {vat_half}"
                st.session_state["other_sales_confirmed"] = True
                st.rerun()

st.divider()

# ------------------------------------------------------------------
# 2) 과세 매출 항목별 입력
# ------------------------------------------------------------------
st.subheader("2. 과세 매출 입력 (세율 10%)")
st.write("해당 사항이 없는 항목은 0으로 두면 됩니다.")

header_cols = st.columns([3, 1, 1])
header_cols[1].markdown("**공급가액**")
header_cols[2].markdown("**세액**")

item_values = {}
for key, label in OTHER_SALES_ITEMS:
    cols = st.columns([3, 1, 1])
    with cols[0]:
        st.markdown(label)
    with cols[1]:
        supply = amount_input("공급가액", f"os_{key}_supply", disabled=confirmed)
    with cols[2]:
        tax = amount_input("세액", f"os_{key}_tax", disabled=confirmed)
    item_values[key] = {"label": label, "supply": supply, "tax": tax}

supply_total = sum(v["supply"] for v in item_values.values())
tax_total = sum(v["tax"] for v in item_values.values())

st.caption(
    "**입력 예시** (개인사업자가 주로 입력하게 되는 항목)\n"
    "- 세금계산서 발급분: 국내 거래처에 물품·용역을 공급하고 세금계산서를 발행한 매출 "
    "(홈택스 로그인 → 조회/발급 → 전자세금계산서 → 목록조회(매출) 메뉴에서 신고기간을 지정해 "
    "발행 내역과 합계를 확인할 수 있습니다.)\n"
    "- 신용카드매출전표 · 현금영수증 발행분: 스마트스토어 등 국내 오픈마켓 판매분, "
    "매장·사무실에서 카드결제·현금영수증으로 받은 매출 (현금영수증 발행분은 홈택스 로그인 → "
    "조회/발급 → 현금영수증 → 매출내역(사업자) 메뉴에서 조회할 수 있습니다.)\n"
    "- 기타(정규영수증 외 매출분): 간이영수증만 발행했거나 증빙 없이 현금으로 받은 매출 등\n\n"
    "**신용카드매출전표(카드 결제분) 자료 받는 방법**\n"
    "이용 중인 각 카드사(비씨/삼성/신한/국민/현대/롯데카드 등) 홈페이지의 '가맹점/사업자용' 페이지에 "
    "로그인한 뒤 '매출조회' 또는 '가맹점 매출내역 조회' 메뉴로 들어가, 조회 기간을 신고기간(반기)으로 "
    "설정하고 '전체 매출내역'을 엑셀(또는 CSV) 파일로 다운로드하세요. 카드사를 여러 곳 이용 중이라면 "
    "카드사별로 각각 내려받아, 공급가액과 세액(부가가치세) 합계를 더해서 위 표에 입력하면 됩니다."
)

st.divider()

# ------------------------------------------------------------------
# 3) 증빙 업로드
# ------------------------------------------------------------------
st.subheader("3. 증빙 업로드")

if not confirmed:
    st.write(
        "위에서 입력한 매출에 대한 증빙(세금계산서, 신용카드매출전표, 현금영수증 등)을 "
        "업로드하세요. (선택 사항이며, 여러 개 업로드할 수 있습니다.)"
    )
    uploaded_evidence = st.file_uploader(
        "증빙 파일 업로드 (PDF, 이미지 등, 여러 개 선택 가능)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="os_evidence_uploader",
    )
    evidence_files = (
        [{"name": f.name, "size": f.size} for f in uploaded_evidence] if uploaded_evidence else []
    )
else:
    evidence_files = st.session_state.get("other_sales_evidence", [])
    if evidence_files:
        st.write("확정된 증빙 파일 목록:")
        for f in evidence_files:
            st.write(f"- {f['name']} ({f['size']:,} bytes)")
    else:
        st.caption("업로드된 증빙 파일이 없습니다.")

st.divider()

# ------------------------------------------------------------------
# 4) 확인 및 저장
# ------------------------------------------------------------------
st.subheader("4. 확인 및 저장")

summary_rows = [{"구분": v["label"], "공급가액": v["supply"], "세액": v["tax"]} for v in item_values.values()]
summary_rows.append({"구분": "합계", "공급가액": supply_total, "세액": tax_total})
summary_df = pd.DataFrame(summary_rows)

st.dataframe(summary_df, width="stretch", hide_index=True)

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    summary_df.to_excel(writer, sheet_name="매출요약", index=False)
    evidence_df = pd.DataFrame(evidence_files) if evidence_files else pd.DataFrame(columns=["name", "size"])
    evidence_df.to_excel(writer, sheet_name="증빙파일목록", index=False)
excel_buffer.seek(0)

st.caption(RAW_DATA_UPLOAD_NOTICE)

if confirmed:
    st.success(
        f"{st.session_state.get('other_sales_period', '')} 값이 확정되어 저장되었습니다. "
        "'부가세 계산' 탭에서 이 값을 자동으로 불러옵니다."
    )
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name=f"{int(vat_year)}년_{vat_half}_그밖의매출_입력결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("다시 수정하기"):
            st.session_state["other_sales_confirmed"] = False
            st.rerun()
else:
    st.write("입력과 증빙 업로드를 모두 마쳤으면 '저장' 버튼을 눌러 매출 및 매출세액을 확정하세요.")
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name=f"{int(vat_year)}년_{vat_half}_그밖의매출_입력결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("저장", type="primary"):
            st.session_state["other_sales_summary"] = summary_df
            st.session_state["other_sales_supply_total"] = supply_total
            st.session_state["other_sales_tax_total"] = tax_total
            st.session_state["other_sales_evidence"] = evidence_files
            st.session_state["other_sales_period"] = f"{int(vat_year)}년 {vat_half}"
            st.session_state["other_sales_confirmed"] = True

            if filing_id:
                db.save_other_sales(filing_id, summary_df, supply_total, tax_total, evidence_files)

            st.rerun()
