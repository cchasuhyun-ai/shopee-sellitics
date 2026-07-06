"""
Shopee Sellitics 웹앱 진입점
============================
왼쪽 사이드바 내비게이션(단일 목록 + 카테고리 배지)만 담당합니다.
실제 화면 로직은 app_pages/ 아래의 각 페이지 파일에서 처리합니다.

탭 구성 (카테고리 배지 - 탭 이름)
--------------------------------
- [안내] 부가세 신고안내 (app_pages/vat_guide.py)
- [매출] 소포수령증 업로드 (app_pages/sales_upload.py)
- [매출] 그 밖의 매출 입력 (app_pages/other_sales_input.py)
- [매입] 카드사용내역 입력 (app_pages/card_usage.py)
- [매입] 매입세액 입력 (app_pages/purchase_input.py)
- [부가세] 부가세 계산 (app_pages/vat_calculation.py)

카테고리 그룹 헤더(아코디언) 대신, 각 탭 이름 앞에 작은 배지로 카테고리를
표시합니다. 배지는 사이드바 목록에서의 순서(nth-child)로 매칭되므로,
NAV_ITEMS의 순서를 바꾸면 배지 CSS도 함께 맞춰서 수정해야 합니다.
"""

import streamlit as st

from amount_input import inject_amount_input_css

st.set_page_config(page_title="Shopee Sellitics", layout="wide")
inject_amount_input_css()

NAV_ITEMS = [
    ("안내", st.Page("app_pages/vat_guide.py", title="부가세 신고안내", default=True)),
    ("매출", st.Page("app_pages/sales_upload.py", title="소포수령증 업로드")),
    ("매출", st.Page("app_pages/other_sales_input.py", title="그 밖의 매출 입력")),
    ("매입", st.Page("app_pages/card_usage.py", title="카드사용내역 입력")),
    ("매입", st.Page("app_pages/purchase_input.py", title="매입세액 입력")),
    ("부가세", st.Page("app_pages/vat_calculation.py", title="부가세 계산")),
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
        background-color: rgba(128, 128, 128, 0.18);
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

navigation = st.navigation([page for _label, page in NAV_ITEMS])
navigation.run()
