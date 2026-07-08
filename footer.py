"""전역 푸터
============
로그인 화면을 포함해 모든 화면 하단에 개인정보처리방침·이용약관 링크와 저작권/문의
정보를 표시합니다. 버튼을 클릭하면 st.dialog로 별도의 작은 창을 띄워 본문을 보여줍니다.
"""

import streamlit as st

from legal import PRIVACY_POLICY_TEXT, TERMS_OF_SERVICE_TEXT


_DIALOG_CONTENT_HEIGHT = 480


@st.dialog("개인정보처리방침")
def _show_privacy_policy() -> None:
    with st.container(height=_DIALOG_CONTENT_HEIGHT):
        st.markdown(PRIVACY_POLICY_TEXT)


@st.dialog("이용약관")
def _show_terms_of_service() -> None:
    with st.container(height=_DIALOG_CONTENT_HEIGHT):
        st.markdown(TERMS_OF_SERVICE_TEXT)


def render_footer() -> None:
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("개인정보처리방침", key="footer_privacy_btn"):
            _show_privacy_policy()
    with col2:
        if st.button("이용약관", key="footer_terms_btn"):
            _show_terms_of_service()
    with col3:
        st.caption("ⓒ Shopee Sellitics · 운영자: 차수현 · 문의: cchasuhyun@gmail.com")
