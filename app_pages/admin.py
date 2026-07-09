"""
관리자 전용 (전체 이용자 신고 데이터 조회)
========================================
profiles.is_admin = true인 계정에게만 사이드바에 노출되는 읽기 전용 화면입니다.
전체 회원의 신고 건과, 각 탭(소포수령증 업로드/그 밖의 매출/카드사용내역/매입세액)에서
저장한 데이터를 조회할 수 있습니다(수정/삭제는 불가 - DB의 RLS 정책 자체가 관리자에게
select 권한만 부여합니다).

개인정보 보호법 제28조(개인정보취급자에 대한 감독) 대응으로, 이 화면에 들어올 때마다
관리자 접근기록을 남깁니다(admin_access_log 테이블).
"""

import streamlit as st

import auth
import db

st.title("관리자 전용")
st.caption("전체 회원의 신고 데이터 열람 (읽기 전용)")
st.warning(
    "이 화면은 개인정보취급자(관리자)만 접근할 수 있습니다. CS 대응, 오류 확인 등 "
    "정당한 업무 목적 범위 안에서만 열람해주세요. 접근 시각은 자동으로 기록됩니다."
)

if not db.is_db_configured():
    st.warning("Supabase가 아직 연결되지 않아 관리자 화면을 사용할 수 없습니다.")
    st.stop()

user = auth.current_user()

# 같은 로그인 세션에서 이 페이지를 다시 열 때마다(위젯 조작으로 인한 재실행 포함)
# 매번 기록하면 로그가 과도하게 쌓이므로, 세션당 한 번만 접근기록을 남깁니다.
if not st.session_state.get("_admin_access_logged"):
    db.log_admin_access(user["user_id"], user["email"])
    st.session_state["_admin_access_logged"] = True

filings = db.list_all_filings()

if not filings:
    st.info("아직 저장된 신고 건이 없습니다.")
    st.stop()


def _label(filing: dict) -> str:
    updated = str(filing.get("updated_at") or "")[:16].replace("T", " ")
    return (
        f"{filing['client_name']} · {filing['period_year']}년 {filing['period_half']} "
        f"(마지막 저장: {updated})"
    )


options = {_label(f): f for f in filings}
selected_label = st.selectbox("신고 건 선택 (전체 회원)", list(options.keys()))
selected = options[selected_label]
filing_id = selected["id"]

st.divider()

sales_saved = db.load_sales_upload(filing_id)
other_sales_saved = db.load_other_sales(filing_id)
card_usage_saved = db.load_card_usage(filing_id)
purchase_saved = db.load_purchase_tax(filing_id)

st.subheader("소포수령증 업로드")
if sales_saved is None or sales_saved["confirmed_df"].empty:
    st.caption("저장된 데이터가 없습니다.")
else:
    st.dataframe(sales_saved["confirmed_df"], width="stretch", hide_index=True)
    st.caption(
        "※ 구매자(제3자) 성명·주소·연락처 등 부가세 계산에 불필요한 식별정보는 "
        "저장 시점에 이미 제외된 데이터입니다."
    )

st.subheader("그 밖의 매출 입력")
if other_sales_saved is None or other_sales_saved["summary_df"].empty:
    st.caption("저장된 데이터가 없습니다.")
else:
    st.dataframe(other_sales_saved["summary_df"], width="stretch", hide_index=True)

st.subheader("카드사용내역 입력")
if card_usage_saved is None or card_usage_saved["rows_df"].empty:
    st.caption("저장된 데이터가 없습니다.")
else:
    st.dataframe(card_usage_saved["rows_df"], width="stretch", hide_index=True)

st.subheader("매입세액 입력")
if purchase_saved is None or purchase_saved["summary_df"].empty:
    st.caption("저장된 데이터가 없습니다.")
else:
    st.dataframe(purchase_saved["summary_df"], width="stretch", hide_index=True)

st.divider()
with st.expander("관리자 접근기록 (최근 50건)"):
    log_rows = db.list_admin_access_log()
    if not log_rows:
        st.caption("기록이 없습니다.")
    else:
        st.dataframe(log_rows, width="stretch", hide_index=True)
