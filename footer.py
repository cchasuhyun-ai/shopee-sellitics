"""전역 푸터
============
로그인 화면을 포함해 모든 화면 하단에 개인정보처리방침·이용약관 링크와 저작권/문의
정보를 표시합니다. st.navigation 기반 페이지 라우팅에 얽매이지 않도록 팝오버로
본문을 바로 보여줍니다.
"""

import streamlit as st

from legal import PRIVACY_POLICY_TEXT, TERMS_OF_SERVICE_TEXT


def render_footer() -> None:
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        with st.popover("개인정보처리방침"):
            st.markdown(PRIVACY_POLICY_TEXT)
    with col2:
        with st.popover("이용약관"):
            st.markdown(TERMS_OF_SERVICE_TEXT)
    with col3:
        st.caption("ⓒ Shopee Sellitics · 운영자: 차수현 · 문의: cchasuhyun@gmail.com")
