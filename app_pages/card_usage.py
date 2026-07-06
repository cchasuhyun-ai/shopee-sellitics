"""
카드사용내역 입력 (매입)
========================
카드사 홈페이지에서 내려받은 카드사용내역 파일(엑셀/CSV)을 업로드하거나,
표에 직접 입력해서 카드사용내역을 정리할 수 있는 페이지입니다.

업로드/직접입력 내역을 '일반매입'과 '고정자산매입'으로 구분해 합계를 계산하고,
'저장' 버튼을 누르면 값이 확정되어 '매입세액 입력' 탭의 "신용카드매출전표 등
수취명세서 제출분(일반매입/고정자산매입)" 항목에 자동으로 반영됩니다.
"""

import io

import pandas as pd
import streamlit as st

st.title("카드사용내역 입력")
st.caption("매입 · 카드사용내역 업로드 및 입력")
st.write(
    "카드사 홈페이지에서 받은 카드사용내역 파일(엑셀/CSV)을 업로드하거나, "
    "표에 직접 입력해서 카드사용내역을 정리할 수 있습니다."
)

MANUAL_ENTRY_COLUMNS = ["거래일자", "가맹점명", "사업자등록번호", "구분", "공급가액", "세액", "비고"]
CATEGORY_OPTIONS = ["일반매입", "고정자산매입"]

confirmed = st.session_state.get("card_usage_confirmed", False)


def _read_uploaded_table(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 인코딩을 인식하지 못했습니다 (utf-8 / cp949 로 시도했습니다).")


def _drop_empty_columns(df: pd.DataFrame):
    cols_to_drop = []
    for col in df.columns:
        stripped = df[col].astype(str).str.strip()
        is_empty = stripped.isin(["", "nan", "None"]) | df[col].isna()
        if is_empty.all():
            cols_to_drop.append(col)
    return df.drop(columns=cols_to_drop)


# ------------------------------------------------------------------
# 1) 파일 업로드
# ------------------------------------------------------------------
st.subheader("파일 업로드")
st.caption("업로드한 파일의 내역은 모두 '일반매입'으로 집계됩니다. 고정자산매입 건은 아래 '직접 입력'에서 구분해 추가하세요.")

if not confirmed:
    uploaded_files = st.file_uploader(
        "카드사용내역 파일을 선택하세요 (엑셀 또는 CSV, 여러 개 선택 가능)",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="card_usage_uploader",
    )

    if uploaded_files:
        parsed_dfs = []
        for uploaded_file in uploaded_files:
            try:
                df = _read_uploaded_table(uploaded_file)
                df.insert(0, "출처파일", uploaded_file.name)
                parsed_dfs.append(df)
            except Exception as e:
                st.error(f"'{uploaded_file.name}' 파일을 읽는 중 오류가 발생했습니다: {e}")

        if parsed_dfs:
            uploaded_df = pd.concat(parsed_dfs, ignore_index=True, sort=False)
            uploaded_df = _drop_empty_columns(uploaded_df)
            st.session_state["card_usage_uploaded_df"] = uploaded_df

if "card_usage_uploaded_df" in st.session_state:
    st.dataframe(st.session_state["card_usage_uploaded_df"], width='stretch')
else:
    st.info("카드사용내역 파일을 업로드하면 표로 정리해서 보여줍니다.")

st.divider()

# ------------------------------------------------------------------
# 2) 직접 입력
# ------------------------------------------------------------------
st.subheader("직접 입력")
st.write(
    "업로드한 파일에 없는 거래는 아래 표에 직접 추가할 수 있습니다. 표 아래쪽의 + 로 행을 추가하고, "
    "'구분' 열에서 일반매입/고정자산매입을 선택하세요."
)

if "card_usage_manual_df" not in st.session_state:
    st.session_state["card_usage_manual_df"] = pd.DataFrame(columns=MANUAL_ENTRY_COLUMNS)

edited_df = st.data_editor(
    st.session_state["card_usage_manual_df"],
    num_rows="dynamic",
    width='stretch',
    column_config={
        "거래일자": st.column_config.DateColumn("거래일자"),
        "구분": st.column_config.SelectboxColumn("구분", options=CATEGORY_OPTIONS, default="일반매입"),
        "공급가액": st.column_config.NumberColumn("공급가액", min_value=0, step=100, format="%,d"),
        "세액": st.column_config.NumberColumn("세액", min_value=0, step=10, format="%,d"),
    },
    key="card_usage_manual_editor",
    disabled=confirmed,
)
st.session_state["card_usage_manual_df"] = edited_df

manual_category = edited_df["구분"].fillna("일반매입")
manual_supply = pd.to_numeric(edited_df["공급가액"], errors="coerce").fillna(0)
manual_tax = pd.to_numeric(edited_df["세액"], errors="coerce").fillna(0)
is_fixed_asset = manual_category == "고정자산매입"

manual_general_supply_total = manual_supply[~is_fixed_asset].sum()
manual_general_tax_total = manual_tax[~is_fixed_asset].sum()
manual_fixed_asset_supply_total = manual_supply[is_fixed_asset].sum()
manual_fixed_asset_tax_total = manual_tax[is_fixed_asset].sum()

uploaded_df = st.session_state.get("card_usage_uploaded_df")
if uploaded_df is not None and "공급가액" in uploaded_df.columns:
    uploaded_general_supply_total = pd.to_numeric(uploaded_df["공급가액"], errors="coerce").fillna(0).sum()
else:
    uploaded_general_supply_total = 0.0
if uploaded_df is not None and "세액" in uploaded_df.columns:
    uploaded_general_tax_total = pd.to_numeric(uploaded_df["세액"], errors="coerce").fillna(0).sum()
else:
    uploaded_general_tax_total = 0.0

general_supply_total = uploaded_general_supply_total + manual_general_supply_total
general_tax_total = uploaded_general_tax_total + manual_general_tax_total
fixed_asset_supply_total = manual_fixed_asset_supply_total
fixed_asset_tax_total = manual_fixed_asset_tax_total

total_col1, total_col2 = st.columns(2)
with total_col1:
    st.metric("일반매입 공급가액/세액", f"{general_supply_total:,.0f} 원 / {general_tax_total:,.0f} 원")
with total_col2:
    st.metric("고정자산매입 공급가액/세액", f"{fixed_asset_supply_total:,.0f} 원 / {fixed_asset_tax_total:,.0f} 원")

st.divider()

# ------------------------------------------------------------------
# 3) 확인 및 저장
# ------------------------------------------------------------------
st.subheader("확인 및 저장")

has_uploaded = "card_usage_uploaded_df" in st.session_state
has_manual = not edited_df.dropna(how="all").empty

excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
    if has_uploaded:
        st.session_state["card_usage_uploaded_df"].to_excel(writer, sheet_name="업로드내역", index=False)
    if has_manual:
        edited_df.to_excel(writer, sheet_name="직접입력내역", index=False)
    if not has_uploaded and not has_manual:
        pd.DataFrame(columns=MANUAL_ENTRY_COLUMNS).to_excel(writer, sheet_name="직접입력내역", index=False)
excel_buffer.seek(0)

if confirmed:
    st.success(
        "값이 확정되어 저장되었습니다. '매입세액 입력' 탭의 신용카드매출전표 등 수취명세서 "
        "제출분(일반매입/고정자산매입) 항목에 자동으로 반영됩니다."
    )
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name="카드사용내역.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("다시 수정하기"):
            st.session_state["card_usage_confirmed"] = False
            st.rerun()
elif has_uploaded or has_manual:
    st.write("내역 확인을 마쳤으면 '저장' 버튼을 눌러 값을 확정하세요.")
    with st.container(horizontal=True, horizontal_alignment="left", gap="xxsmall"):
        st.download_button(
            label="다운로드",
            data=excel_buffer,
            file_name="카드사용내역.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("저장", type="primary"):
            st.session_state["card_usage_general_supply"] = general_supply_total
            st.session_state["card_usage_general_tax"] = general_tax_total
            st.session_state["card_usage_fixed_asset_supply"] = fixed_asset_supply_total
            st.session_state["card_usage_fixed_asset_tax"] = fixed_asset_tax_total
            st.session_state["card_usage_confirmed"] = True
            st.rerun()
else:
    st.info("파일을 업로드하거나 직접 입력한 뒤 저장할 수 있습니다.")
