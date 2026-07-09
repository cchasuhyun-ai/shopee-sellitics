"""Supabase 연결 및 저장/불러오기 헬퍼
====================================
로그인한 사용자(user_id) + 신고기간(연도/반기) 단위로 데이터를 저장/불러옵니다
(schema.sql 참고, RLS로 본인 소유 행만 조회/수정 가능합니다).

get_client()는 st.cache_resource를 쓰지 않습니다. 로그인 후에는 클라이언트에
사용자의 access token이 붙는데, cache_resource는 서버 프로세스 전체에서 공유되는
싱글턴이라 여러 사용자가 동시 접속하면 세션(=누구로 인증됐는지)이 서로 섞일 수
있기 때문입니다. 대신 브라우저 세션(st.session_state)마다 클라이언트를 하나씩 만들고,
로그인 상태(auth.sb_session)의 토큰을 매번 붙여서 씁니다.
"""

import datetime
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
from supabase import Client, create_client


def is_db_configured() -> bool:
    return "supabase" in st.secrets


def get_client() -> Client:
    if "_supabase_client" not in st.session_state:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        st.session_state["_supabase_client"] = create_client(url, key)

    client = st.session_state["_supabase_client"]
    session = st.session_state.get("sb_session")
    if session:
        client.auth.set_session(session["access_token"], session["refresh_token"])
    return client


def _sanitize_value(value):
    """jsonb 컬럼에 그대로 넣을 수 없는 pandas/numpy 타입(Timestamp, NaT, int64 등)을
    JSON 직렬화 가능한 값으로 바꿉니다."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _df_to_records(df: Optional[pd.DataFrame]) -> list:
    if df is None or df.empty:
        return []
    records = df.astype(object).where(pd.notna(df), None).to_dict("records")
    return [{k: _sanitize_value(v) for k, v in row.items()} for row in records]


def _records_to_df(records: Optional[list]) -> pd.DataFrame:
    return pd.DataFrame(records or [])


def get_or_create_filing(user_id: str, year: int, half: str, company_name: str) -> str:
    """로그인한 사용자+신고연도+반기에 해당하는 vat_filings 행을 찾아서 id를 반환하고,
    없으면 새로 만듭니다."""
    supabase = get_client()
    payload = {
        "user_id": user_id,
        "client_name": company_name,
        "period_year": int(year),
        "period_half": half,
    }
    result = (
        supabase.table("vat_filings")
        .upsert(payload, on_conflict="user_id,period_year,period_half")
        .execute()
    )
    return result.data[0]["id"]


def list_filings(user_id: str) -> list:
    """로그인한 사용자가 지금까지 저장한 신고 건(연도/반기) 목록을 최신순으로 반환합니다."""
    supabase = get_client()
    result = (
        supabase.table("vat_filings")
        .select("id, period_year, period_half, updated_at")
        .eq("user_id", user_id)
        .order("period_year", desc=True)
        .order("period_half", desc=True)
        .execute()
    )
    return result.data or []


# ------------------------------------------------------------------
# [매출] 소포수령증 업로드
# ------------------------------------------------------------------

def save_sales_upload(filing_id: str, confirmed_df, raw_df, sheet_data: dict) -> None:
    supabase = get_client()
    payload = {
        "filing_id": filing_id,
        "confirmed_rows": _df_to_records(confirmed_df),
        "raw_rows": _df_to_records(raw_df),
        "sheet_data": {name: _df_to_records(df) for name, df in (sheet_data or {}).items()},
    }
    supabase.table("sales_uploads").upsert(payload, on_conflict="filing_id").execute()


def load_sales_upload(filing_id: str) -> Optional[dict]:
    supabase = get_client()
    res = supabase.table("sales_uploads").select("*").eq("filing_id", filing_id).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    return {
        "confirmed_df": _records_to_df(row["confirmed_rows"]),
        "raw_df": _records_to_df(row["raw_rows"]),
        "sheet_data": {name: _records_to_df(records) for name, records in (row["sheet_data"] or {}).items()},
    }


# ------------------------------------------------------------------
# [매출] 그 밖의 매출 입력
# ------------------------------------------------------------------

def save_other_sales(filing_id: str, summary_df, supply_total: float, tax_total: float, evidence_files: list) -> None:
    supabase = get_client()
    payload = {
        "filing_id": filing_id,
        "summary": _df_to_records(summary_df),
        "supply_total": float(supply_total),
        "tax_total": float(tax_total),
        "evidence_files": evidence_files or [],
    }
    supabase.table("other_sales").upsert(payload, on_conflict="filing_id").execute()


def load_other_sales(filing_id: str) -> Optional[dict]:
    supabase = get_client()
    res = supabase.table("other_sales").select("*").eq("filing_id", filing_id).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    return {
        "summary_df": _records_to_df(row["summary"]),
        "supply_total": row["supply_total"],
        "tax_total": row["tax_total"],
        "evidence_files": row["evidence_files"] or [],
    }


# ------------------------------------------------------------------
# [매입] 카드사용내역 입력
# ------------------------------------------------------------------

def save_card_usage(
    filing_id: str,
    rows_df,
    general_supply_total: float,
    general_tax_total: float,
    fixed_asset_supply_total: float,
    fixed_asset_tax_total: float,
) -> None:
    supabase = get_client()
    payload = {
        "filing_id": filing_id,
        "rows": _df_to_records(rows_df),
        "general_supply_total": float(general_supply_total),
        "general_tax_total": float(general_tax_total),
        "fixed_asset_supply_total": float(fixed_asset_supply_total),
        "fixed_asset_tax_total": float(fixed_asset_tax_total),
    }
    supabase.table("card_usage").upsert(payload, on_conflict="filing_id").execute()


def load_card_usage(filing_id: str) -> Optional[dict]:
    supabase = get_client()
    res = supabase.table("card_usage").select("*").eq("filing_id", filing_id).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    rows_df = _records_to_df(row["rows"])
    if "거래일자" in rows_df.columns:
        # pandas 3.x는 pd.to_datetime 결과를 us/s 단위로 추론하기도 하는데, 현재 Streamlit
        # 버전의 data_editor(DateColumn)는 datetime64[ns]만 날짜 타입으로 인식하므로 명시 변환합니다.
        rows_df["거래일자"] = pd.to_datetime(rows_df["거래일자"], errors="coerce").astype("datetime64[ns]")
    return {
        "rows_df": rows_df,
        "general_supply_total": row["general_supply_total"],
        "general_tax_total": row["general_tax_total"],
        "fixed_asset_supply_total": row["fixed_asset_supply_total"],
        "fixed_asset_tax_total": row["fixed_asset_tax_total"],
    }


# ------------------------------------------------------------------
# [매입] 매입세액 입력
# ------------------------------------------------------------------

def save_purchase_tax(filing_id: str, summary_df, net_tax_total: float) -> None:
    supabase = get_client()
    payload = {
        "filing_id": filing_id,
        "summary": _df_to_records(summary_df),
        "net_tax_total": float(net_tax_total),
    }
    supabase.table("purchase_tax").upsert(payload, on_conflict="filing_id").execute()


def load_purchase_tax(filing_id: str) -> Optional[dict]:
    supabase = get_client()
    res = supabase.table("purchase_tax").select("*").eq("filing_id", filing_id).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    return {
        "summary_df": _records_to_df(row["summary"]),
        "net_tax_total": row["net_tax_total"],
    }


# ------------------------------------------------------------------
# [관리자] 전체 이용자 신고 데이터 열람 (읽기 전용)
# ------------------------------------------------------------------
# 아래 함수들은 schema.sql의 "admin select all ..." RLS 정책에 의존합니다.
# 로그인한 사용자의 profiles.is_admin이 true가 아니면 DB가 빈 결과만 돌려주므로,
# 여기서 별도로 권한을 다시 검사하지 않습니다(단일 진실 소스는 RLS).

def list_all_filings() -> list:
    """관리자 전용: 모든 회원의 신고 건 목록을 최신순으로 반환합니다."""
    supabase = get_client()
    result = (
        supabase.table("vat_filings")
        .select("id, user_id, client_name, period_year, period_half, updated_at")
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data or []


def log_admin_access(admin_id: str, admin_email: str) -> None:
    """관리자가 전체 이용자 데이터 조회 화면에 들어올 때마다 접근기록을 남깁니다
    (개인정보 보호법 제28조 개인정보취급자 접근기록 관리 의무 대응)."""
    supabase = get_client()
    supabase.table("admin_access_log").insert(
        {"admin_id": admin_id, "admin_email": admin_email}
    ).execute()


def list_admin_access_log(limit: int = 50) -> list:
    supabase = get_client()
    result = (
        supabase.table("admin_access_log")
        .select("admin_email, viewed_at")
        .order("viewed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []
