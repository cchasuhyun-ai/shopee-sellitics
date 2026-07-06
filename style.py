"""앱 전체에 적용되는 전역 디자인(타이포그래피, 여백, 카드 스타일) CSS.

색상은 .streamlit/config.toml의 테마와 맞춰서, 전문적이면서 절제된 슬레이트/블루
톤으로 통일합니다. 여기서는 테마가 다루지 않는 세부 요소(사이드바 내비게이션,
카드형 컨테이너, 지표, 표, 구분선 등)의 여백과 모서리를 다듬습니다.
"""

import streamlit as st

APP_STYLE_CSS = """
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Pretendard",
        "Malgun Gothic", Roboto, Helvetica, Arial, sans-serif;
}

.block-container {
    padding-top: 2.4rem;
    padding-bottom: 3rem;
    max-width: 1180px;
}

h1 {
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #0F172A;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #E2E8F0;
    margin-bottom: 1rem;
}
h2, h3 {
    font-weight: 600;
    color: #1E293B;
}

[data-testid="stSidebar"] {
    background-color: #F8FAFC;
    border-right: 1px solid #E2E8F0;
}
[data-testid="stSidebarNavLink"] {
    border-radius: 8px;
    margin: 1px 8px;
    transition: background-color 0.15s ease;
}
[data-testid="stSidebarNavLink"]:hover {
    background-color: #E2E8F0;
}

button[kind="primary"], button[kind="primaryFormSubmit"] {
    border-radius: 8px;
    font-weight: 600;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}
button[kind="secondary"] {
    border-radius: 8px;
}

div[data-testid="stExpander"] {
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 10px;
}

div[data-testid="stMetric"] {
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 0.9rem 1rem;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    overflow: hidden;
}

div[data-testid="stAlert"] {
    border-radius: 8px;
}

hr {
    margin: 1.6rem 0;
    border-color: #E2E8F0;
}

div[class*="st-key-period_year"] input {
    text-align: center !important;
}
</style>
"""


def inject_app_style() -> None:
    """전역 디자인 CSS를 적용합니다. (앱 진입점에서 한 번만 호출)"""
    st.markdown(APP_STYLE_CSS, unsafe_allow_html=True)
