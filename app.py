"""
Shopee Sellitics 웹앱 진입점
============================
왼쪽 사이드바 내비게이션(카테고리 - 탭 구조)만 담당합니다.
실제 화면 로직은 app_pages/ 아래의 각 페이지 파일에서 처리합니다.

카테고리 구성
-------------
- 매출
    - 소포수령증 업로드 (app_pages/sales_upload.py)
- 매입
    - 매입세액 입력 (app_pages/purchase_input.py)
"""

import streamlit as st

st.set_page_config(page_title="Shopee Sellitics", layout="wide")

pages = {
    "매출": [
        st.Page("app_pages/sales_upload.py", title="소포수령증 업로드", default=True),
    ],
    "매입": [
        st.Page("app_pages/purchase_input.py", title="매입세액 입력"),
    ],
}

navigation = st.navigation(pages)
navigation.run()
