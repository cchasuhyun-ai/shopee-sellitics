"""Supabase Auth 로그인/회원가입 헬퍼
====================================
로그인 세션(access/refresh token)은 st.session_state에만 보관합니다(브라우저 탭이
바뀌거나 서버가 재시작되면 다시 로그인해야 합니다). 로그인/회원가입 자체는 세션이
없는 상태에서 매번 새 클라이언트로 호출하므로, 다른 사용자와 인증 정보가 섞이지
않습니다(공유 캐시 클라이언트에 세션을 붙이면 여러 사용자가 동시 접속할 때 서로의
세션이 섞일 수 있어 의도적으로 피합니다).
"""

from typing import Optional

import streamlit as st
from supabase import create_client


def _anon_client():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


def is_logged_in() -> bool:
    return "sb_session" in st.session_state


def current_user() -> Optional[dict]:
    return st.session_state.get("sb_session")


def is_admin() -> bool:
    """관리자(개인정보취급자) 여부. 로그인 시 profiles.is_admin 값을 세션에 담아둔
    것을 그대로 씁니다(요청마다 다시 조회하지 않음)."""
    session = current_user()
    return bool(session and session.get("is_admin"))


def _store_session(session, company_name: str, is_admin: bool) -> None:
    st.session_state["sb_session"] = {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user_id": session.user.id,
        "email": session.user.email,
        "company_name": company_name,
        "is_admin": is_admin,
    }
    # db.get_client()가 다음 호출에서 새 토큰으로 클라이언트를 다시 만들도록 캐시를 비웁니다.
    st.session_state.pop("_supabase_client", None)


def sign_up(email: str, password: str, company_name: str) -> tuple[bool, str]:
    client = _anon_client()
    try:
        res = client.auth.sign_up(
            {
                "email": email,
                "password": password,
                "options": {"data": {"company_name": company_name}},
            }
        )
    except Exception as e:
        return False, f"회원가입에 실패했습니다: {getattr(e, 'message', str(e))}"

    if res.session is None:
        return True, "가입 확인 이메일을 보냈습니다. 메일함에서 링크를 클릭한 뒤 로그인해주세요."

    # 신규 가입 계정은 항상 is_admin=false로 시작합니다(관리자 권한은 프로젝트
    # 소유자가 Supabase SQL Editor에서 수동으로만 부여할 수 있습니다. schema.sql 참고).
    _store_session(res.session, company_name, is_admin=False)
    return True, "가입이 완료되었습니다."


def sign_in(email: str, password: str) -> tuple[bool, str]:
    client = _anon_client()
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        return False, "이메일 또는 비밀번호가 올바르지 않습니다. (가입 직후라면 이메일 인증을 먼저 완료해주세요)"

    profile = (
        client.table("profiles")
        .select("company_name, is_admin")
        .eq("id", res.user.id)
        .limit(1)
        .execute()
    )
    company_name = profile.data[0]["company_name"] if profile.data else res.user.email
    is_admin = bool(profile.data[0]["is_admin"]) if profile.data else False

    _store_session(res.session, company_name, is_admin)
    return True, "로그인되었습니다."


def sign_out() -> None:
    # 각 탭 페이지가 session_state에 남겨둔 확정 상태/불러온 데이터(예: other_sales_confirmed,
    # card_usage_manual_df 등)를 그대로 두면, 같은 브라우저 탭에서 다른 계정으로 로그인했을 때
    # 이전 사용자의 데이터가 화면에 그대로 남아 보이는 문제가 있어 전체를 초기화합니다.
    st.session_state.clear()
