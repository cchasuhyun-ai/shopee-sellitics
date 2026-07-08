"""
Shopee Sellitics 웹앱 진입점
============================
왼쪽 사이드바 내비게이션(단일 목록 + 카테고리 배지)만 담당합니다.
실제 화면 로직은 app_pages/ 아래의 각 페이지 파일에서 처리합니다.

탭 구성 (카테고리 배지 - 탭 이름)
--------------------------------
- [안내] 부가세 신고안내 (app_pages/vat_guide.py)
- [안내] 자주 묻는 질문 (app_pages/vat_faq.py)
- [매출] 소포수령증 업로드 (app_pages/sales_upload.py)
- [매출] 그 밖의 매출 입력 (app_pages/other_sales_input.py)
- [매입] 카드사용내역 입력 (app_pages/card_usage.py)
- [매입] 매입세액 입력 (app_pages/purchase_input.py)
- [신고] 부가세 계산 (app_pages/vat_calculation.py)
- [신고] 부가세 신고 (app_pages/vat_filing.py)
- [문의] 문의하기 (app_pages/contact.py)

카테고리 그룹 헤더(아코디언) 대신, 각 탭 이름 앞에 작은 배지로 카테고리를
표시합니다. 배지는 사이드바 목록에서의 순서(nth-child)로 매칭되므로,
NAV_ITEMS의 순서를 바꾸면 배지 CSS도 함께 맞춰서 수정해야 합니다.
"""

import streamlit as st

import auth
import db
from amount_input import inject_amount_input_css
from style import inject_app_style

st.set_page_config(page_title="Shopee Sellitics", layout="wide")
inject_app_style()
inject_amount_input_css()


def render_login_page() -> None:
    st.title("Shopee Sellitics")
    st.caption("로그인 후 이용할 수 있습니다.")

    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("이메일", key="login_email")
            password = st.text_input("비밀번호", type="password", key="login_password")
            submitted = st.form_submit_button("로그인")
        if submitted:
            ok, message = auth.sign_in(email.strip(), password)
            if ok:
                st.rerun()
            else:
                st.error(message)

    with signup_tab:
        with st.form("signup_form"):
            company_name = st.text_input("거래처명 (회사명)", key="signup_company_name")
            email = st.text_input("이메일", key="signup_email")
            password = st.text_input("비밀번호 (8자 이상)", type="password", key="signup_password")
            password_confirm = st.text_input(
                "비밀번호 확인", type="password", key="signup_password_confirm"
            )
            submitted = st.form_submit_button("회원가입")
        if submitted:
            if not company_name.strip() or not email.strip() or not password:
                st.error("모든 항목을 입력해주세요.")
            elif password != password_confirm:
                st.error("비밀번호가 일치하지 않습니다.")
            elif len(password) < 8:
                st.error("비밀번호는 8자 이상이어야 합니다.")
            else:
                ok, message = auth.sign_up(email.strip(), password, company_name.strip())
                if ok:
                    if auth.is_logged_in():
                        st.rerun()
                    st.success(message)
                else:
                    st.error(message)


if not db.is_db_configured():
    st.error("Supabase가 아직 연결되지 않아 로그인을 사용할 수 없습니다. .streamlit/secrets.toml을 확인해주세요.")
    st.stop()

if not auth.is_logged_in():
    render_login_page()
    st.stop()

NAV_ITEMS = [
    ("안내", st.Page("app_pages/vat_guide.py", title="부가세 신고안내", default=True)),
    ("안내", st.Page("app_pages/vat_faq.py", title="자주 묻는 질문")),
    ("매출", st.Page("app_pages/sales_upload.py", title="소포수령증 업로드")),
    ("매출", st.Page("app_pages/other_sales_input.py", title="그 밖의 매출 입력")),
    ("매입", st.Page("app_pages/card_usage.py", title="카드사용내역 입력")),
    ("매입", st.Page("app_pages/purchase_input.py", title="매입세액 입력")),
    ("신고", st.Page("app_pages/vat_calculation.py", title="부가세 계산")),
    ("신고", st.Page("app_pages/vat_filing.py", title="부가세 신고")),
    ("신고", st.Page("app_pages/saved_filings.py", title="저장된 신고내역")),
    ("문의", st.Page("app_pages/contact.py", title="문의하기")),
]

_badge_content_rules = "\n".join(
    f'[data-testid="stSidebarNavItems"] > *:nth-child({i}) '
    f'[data-testid="stSidebarNavLink"]::before {{ content: "{label}"; }}'
    for i, (label, _page) in enumerate(NAV_ITEMS, start=1)
)

st.markdown(
    f"""
    <style>
    [data-testid="stSidebarNavLink"]::before {{
        display: inline-block;
        margin-right: 6px;
        padding: 1px 7px;
        border-radius: 4px;
        background-color: rgba(37, 99, 235, 0.12);
        color: #1D4ED8;
        font-size: 0.72rem;
        font-weight: 600;
        vertical-align: middle;
        white-space: nowrap;
    }}
    {_badge_content_rules}
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    user = auth.current_user()
    st.markdown(f"**{user['company_name']}**")
    st.caption(user["email"])
    if st.button("로그아웃", width="stretch"):
        auth.sign_out()
        st.rerun()

navigation = st.navigation([page for _label, page in NAV_ITEMS])
navigation.run()
