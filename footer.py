"""전역 푸터
============
로그인 화면을 포함해 모든 화면 하단에 개인정보처리방침·이용약관 링크와 저작권/문의
정보를 표시합니다. 버튼을 클릭하면 st.dialog로 별도의 작은 창을 띄워 본문을 보여줍니다.
"""

import streamlit as st
import streamlit.components.v1 as components

from legal import PRIVACY_POLICY_TEXT, TERMS_OF_SERVICE_TEXT


_DIALOG_CONTENT_HEIGHT = 480

_SCROLL_BOX_CSS = """
<style>
.st-key-privacy_scroll_box, .st-key-terms_scroll_box {{
    max-height: {height}px;
    overflow-y: auto;
    overflow-anchor: none;
    padding-right: 0.8rem;
}}
</style>
""".format(height=_DIALOG_CONTENT_HEIGHT)


def _reset_scroll_to_top() -> None:
    """일부 브라우저에서 모달 안의 링크로 포커스가 이동하며 스크롤 영역이 아래로
    밀려 열리는 경우가 있어, 렌더링 직후 강제로 맨 위로 되돌립니다."""
    components.html(
        """
        <script>
        setTimeout(function () {
            const doc = window.parent.document;
            doc.querySelectorAll('.st-key-privacy_scroll_box, .st-key-terms_scroll_box')
                .forEach(function (box) { box.scrollTop = 0; });
        }, 50);
        </script>
        """,
        height=0,
    )


@st.dialog("개인정보처리방침")
def _show_privacy_policy() -> None:
    st.markdown(_SCROLL_BOX_CSS, unsafe_allow_html=True)
    with st.container(key="privacy_scroll_box"):
        st.markdown(PRIVACY_POLICY_TEXT)
    _reset_scroll_to_top()


@st.dialog("이용약관")
def _show_terms_of_service() -> None:
    st.markdown(_SCROLL_BOX_CSS, unsafe_allow_html=True)
    with st.container(key="terms_scroll_box"):
        st.markdown(TERMS_OF_SERVICE_TEXT)
    _reset_scroll_to_top()


def render_footer() -> None:
    st.divider()
    st.markdown(
        """
        <style>
        .st-key-footer_row {
            display: flex;
            flex-direction: row;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.3rem;
        }
        .st-key-footer_row [data-testid="stButton"] button {
            white-space: nowrap;
        }
        .st-key-footer_row [data-testid="stCaptionContainer"] {
            margin-left: 0.6rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="footer_row"):
        if st.button("개인정보처리방침", key="footer_privacy_btn"):
            _show_privacy_policy()
        if st.button("이용약관", key="footer_terms_btn"):
            _show_terms_of_service()
        st.caption("ⓒ Shopee Sellitics · 운영자: 차수현 · 문의: cchasuhyun@gmail.com")
