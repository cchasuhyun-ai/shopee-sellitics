"""
소포수령증 업로드 (매출)
========================
여러 사용자가 PDF(소포수령증 등)를 업로드하면, 표를 자동으로 인식해서
취합한 뒤 화면에 보여주고 엑셀 파일로 다운로드할 수 있게 해주는 페이지입니다.

부가세 신고기한(상반기/하반기) 판정
------------------------------------
신고 대상 연도/반기를 선택하면, 표의 '발행일'을 기준으로 그 기간에 포함되는 행만
합계 계산에 반영합니다.

화폐/환율/원화환산금액
------------------------------------
'도착국가'와 '발행일'을 기준으로 화폐(통화코드)를 판별하고, smbs.biz의 날짜별
매매기준율을 조회해서 화폐/환율/원화환산금액 열을 자동으로 추가합니다
(exchange_rate.py 참고).

취합 결과 수정 및 저장
------------------------------------
자동 인식된 표에 잘못된 값이 있으면 사용자가 화면에서 직접 수정할 수 있습니다.
수정 후 문제가 없으면 '저장' 버튼을 눌러 값을 확정합니다. 확정된 값은 다시 수정할
때까지 그대로 유지되며, 엑셀 다운로드도 확정된 값을 기준으로 만들어집니다.

[향후 로그인/사용자별 저장 기능 확장 지점]
- 지금은 로그인 없이 "업로드 -> 처리 -> 수정 -> 저장(확정) -> 다운로드"만 지원합니다.
- 나중에 Supabase 등으로 로그인을 붙이면:
    1) 로그인한 사용자 ID를 얻어온다 (예: user_id = supabase.auth.get_user().id)
    2) 저장(확정)된 결과(confirmed_df, raw_df)를
       사용자 ID와 함께 데이터베이스에 저장한다 (아래 "TODO(로그인 연동)" 표시 참고)
    3) 로그인한 사용자가 다시 접속했을 때, DB에서 그 사용자의 이전 결과를 불러와 보여준다
  이런 지점들을 미리 함수로 분리해두었으니, 나중에 이 부분만 교체하면 됩니다.
"""

import io
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from openpyxl.styles import Font

from exchange_rate import fetch_exchange_rates, get_currency_for_country, get_display_country_name
from pdf_processor import (
    VAT_DATE_COLUMN,
    VAT_HALF_OPTIONS,
    apply_vat_period_filter,
    build_result_sheets,
    build_summary_row,
    check_korean_ocr_support,
    get_vat_period,
    parse_date_flexible,
    process_pdf,
    to_numeric_series,
)

ARRIVAL_COUNTRY_COLUMN = "도착국가"
EXPORT_AMOUNT_COLUMN = "수출신고금액"
SHIPMENT_QTY_COLUMN = "발송수량"
KRW_AMOUNT_COLUMN = "원화환산금액"


def add_exchange_rate_columns(df: pd.DataFrame, convert_col: str) -> tuple:
    """'도착국가'와 '발행일'을 기준으로 화폐/환율/원화환산금액 열을 제일 우측에 추가합니다.
    원화환산금액 = convert_col(기본값: '수출신고금액') 값 * 환율.
    (화폐는 환율 바로 왼쪽에 위치하며, 그 화폐 기준으로 환율을 조회합니다.)
    '발행일' 값은 인식에 성공하면 'YYYY/MM/DD' 형태로 통일해서 다시 채워 넣습니다.
    국가를 인식하지 못하거나 해당 날짜의 환율을 가져오지 못하면 빈 값으로 둡니다.

    반환: (환율 열이 추가된 df, 원인 파악용 진단 정보 dict)
    """
    df = df.copy()
    actual_columns = ", ".join(str(c) for c in df.columns)
    if ARRIVAL_COUNTRY_COLUMN not in df.columns:
        return df, {f"'{ARRIVAL_COUNTRY_COLUMN}' 컬럼을 찾을 수 없음": [f"현재 표의 실제 컬럼: {actual_columns}"]}

    display_countries = []
    display_dates = []
    currency_values = []
    rate_values = []
    krw_values = []
    unmatched_countries = set()
    unmatched_dates = set()
    unmatched_rates = set()
    for _, row in df.iterrows():
        country_raw = row.get(ARRIVAL_COUNTRY_COLUMN)
        date_raw = row.get(VAT_DATE_COLUMN)
        currency_code = get_currency_for_country(country_raw)
        ship_date = parse_date_flexible(date_raw)
        rate = None

        if currency_code is None:
            if pd.notna(country_raw) and str(country_raw).strip():
                unmatched_countries.add(str(country_raw).strip())
        elif pd.isna(ship_date):
            if pd.notna(date_raw) and str(date_raw).strip():
                unmatched_dates.add(str(date_raw).strip())
        else:
            rate = fetch_exchange_rates(ship_date.date()).get(currency_code)
            if rate is None:
                unmatched_rates.add(f"{currency_code} ({ship_date.date():%Y-%m-%d})")

        krw_amount = None
        if rate is not None and convert_col is not None:
            amount = to_numeric_series(pd.Series([row.get(convert_col)])).iloc[0]
            if pd.notna(amount):
                krw_amount = amount * rate

        display_countries.append(get_display_country_name(country_raw))
        display_dates.append(ship_date.strftime("%Y/%m/%d") if pd.notna(ship_date) else date_raw)
        currency_values.append(currency_code or "")
        rate_values.append(rate)
        krw_values.append(f"{krw_amount:,.0f}" if krw_amount is not None else "")

    df[ARRIVAL_COUNTRY_COLUMN] = display_countries
    if VAT_DATE_COLUMN in df.columns:
        df[VAT_DATE_COLUMN] = display_dates
    df["화폐"] = currency_values
    df["환율"] = rate_values
    df["원화환산금액"] = krw_values

    issues = {
        "도착국가를 인식하지 못한 값": sorted(unmatched_countries),
        "발행일을 인식하지 못한 값": sorted(unmatched_dates),
        "환율 조회에 실패한 통화/일자": sorted(unmatched_rates),
    }
    if VAT_DATE_COLUMN not in df.columns:
        issues[f"'{VAT_DATE_COLUMN}' 컬럼을 찾을 수 없음"] = [f"현재 표의 실제 컬럼: {actual_columns}"]
    if convert_col not in df.columns:
        issues[f"'{convert_col}' 컬럼을 찾을 수 없음"] = [f"현재 표의 실제 컬럼: {actual_columns}"]
    return df, issues


st.title("소포수령증 업로드")
st.caption("매출 · 소포수령증 PDF 취합")
st.write(
    "소포수령증을 PDF로 업로드하면 매출내역을 하나의 표로 취합합니다. "
    "결과를 화면에서 확인하고 누락되거나 잘못 입력된 값을 수정하세요. "
    "완료된 데이터는 엑셀 파일로 다운로드 할 수 있습니다."
)

# ------------------------------------------------------------------
# 0) 부가세 신고기한 설정
# ------------------------------------------------------------------
st.subheader("부가세 신고기한 설정")

today = date.today()
default_half_index = 0 if today.month <= 6 else 1

period_col1, period_col2 = st.columns([1, 3])
with period_col1:
    vat_year = st.number_input("신고연도", min_value=2000, max_value=2100, value=today.year, step=1)
with period_col2:
    vat_half = st.radio("신고기간(반기)", VAT_HALF_OPTIONS, index=default_half_index, horizontal=True)

period_start, period_end, filing_deadline = get_vat_period(int(vat_year), vat_half)
st.info(f"신고 대상기간: {period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d}  |  신고기한: {filing_deadline}")

# ------------------------------------------------------------------
# (참고) 한글 OCR 지원 여부 확인 - 서버에 Tesseract 한국어 언어팩이 없으면 경고 표시
# ------------------------------------------------------------------
warning_msg = check_korean_ocr_support("kor+eng")
if warning_msg:
    st.warning(warning_msg)

# ------------------------------------------------------------------
# 1) 파일 업로드
# ------------------------------------------------------------------
uploaded_files = st.file_uploader(
    "PDF 파일을 선택하세요 (여러 개 선택 가능)",
    type=["pdf"],
    accept_multiple_files=True,
)

force_ocr = st.checkbox("모든 페이지를 OCR로 처리 (PDF 파일을 스캔하여 그림파일로 인식되는 경우 체크)", value=False)

# TODO(로그인 연동): 로그인 기능을 붙이면 여기서 현재 로그인한 사용자 정보를 가져와서
# 아래 처리 결과를 사용자 ID와 함께 저장하도록 확장하면 됩니다.
# 예시:
#   user = get_current_user()  # 로그인 모듈에서 제공
#   if user is None:
#       st.info("로그인 후 이용해주세요.")
#       st.stop()

if uploaded_files:
    if st.button("취합 시작하기", type="primary"):
        results_by_file = {}
        progress = st.progress(0, text="처리 준비 중...")

        for idx, uploaded_file in enumerate(uploaded_files, start=1):
            progress.progress(
                idx / len(uploaded_files),
                text=f"처리 중... ({idx}/{len(uploaded_files)}) {uploaded_file.name}",
            )
            # Streamlit이 주는 업로드 파일은 메모리 상의 바이트 스트림이라서,
            # OCR(pdf2image)이 실제 파일 경로를 필요로 하므로 임시 파일로 저장합니다.
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name

            try:
                page_tables, raw_records = process_pdf(tmp_path, force_ocr=force_ocr)
                results_by_file[uploaded_file.name] = (page_tables, raw_records)
            except Exception as e:
                st.error(f"'{uploaded_file.name}' 처리 중 오류가 발생했습니다: {e}")
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        progress.empty()

        combined_df, sheet_data, raw_df = build_result_sheets(results_by_file)

        # 처리 결과를 세션에 저장해서, 버튼을 눌러도 화면이 초기화되지 않게 함
        st.session_state["combined_df"] = combined_df
        st.session_state["sheet_data"] = sheet_data
        st.session_state["raw_df"] = raw_df

        # 새로 취합했으므로, 이전에 수정/확정했던 내용은 초기화합니다.
        st.session_state["sales_confirmed"] = False
        st.session_state.pop("confirmed_df", None)
        st.session_state.pop("combined_editor", None)

# ------------------------------------------------------------------
# 2) 결과 확인 + 수정 + 저장(확정) + 다운로드
# ------------------------------------------------------------------
if "combined_df" in st.session_state:
    st.success("취합이 완료되었습니다.")

    combined_df = st.session_state["combined_df"]
    has_aggregated_table = "출처파일" in combined_df.columns
    confirmed = st.session_state.get("sales_confirmed", False)

    active_df = combined_df
    preview_df = combined_df
    summary_row_idx = None

    if not has_aggregated_table:
        st.dataframe(combined_df, width='stretch')
    elif confirmed:
        active_df = st.session_state["confirmed_df"]
        st.success("값이 확정되어 저장되었습니다. 값을 다시 고치려면 아래 버튼을 누르세요.")
        if st.button("다시 수정하기"):
            st.session_state["sales_confirmed"] = False
            st.rerun()
    else:
        st.write(
            "표에 잘못 인식된 값이 있으면 셀을 더블클릭해서 직접 수정하거나, 표 아래쪽 "
            "'+'/휴지통 아이콘으로 행을 추가·삭제하세요. 문제가 없으면 '저장' 버튼을 눌러 값을 확정합니다."
        )
        active_df = st.data_editor(
            combined_df,
            num_rows="dynamic",
            width='stretch',
            key="combined_editor",
        )

    if has_aggregated_table:
        in_period_mask, amount_cols = apply_vat_period_filter(active_df, period_start, period_end)
        result_df, rate_issues = add_exchange_rate_columns(active_df, EXPORT_AMOUNT_COLUMN)

        # 발송수량/수출신고금액은 합계를 표시하지 않고, 원화환산금액만 합계로 표시합니다.
        summary_amount_cols = [
            col for col in amount_cols if col not in (SHIPMENT_QTY_COLUMN, EXPORT_AMOUNT_COLUMN)
        ]
        summary_row = build_summary_row(result_df, in_period_mask, summary_amount_cols)
        if KRW_AMOUNT_COLUMN in result_df.columns:
            krw_total = to_numeric_series(result_df.loc[in_period_mask, KRW_AMOUNT_COLUMN]).fillna(0).sum()
            summary_row[KRW_AMOUNT_COLUMN] = f"{krw_total:,.0f}"
        preview_df = pd.concat([result_df, pd.DataFrame([summary_row])], ignore_index=True)
        summary_row_idx = len(result_df)

        right_align_cols = [SHIPMENT_QTY_COLUMN, EXPORT_AMOUNT_COLUMN, KRW_AMOUNT_COLUMN]
        column_config = {
            col: st.column_config.TextColumn(col, alignment="right")
            for col in right_align_cols
            if col in preview_df.columns
        }
        st.dataframe(preview_df, width='stretch', column_config=column_config)

        issue_lines = [f"- {label}: {', '.join(values)}" for label, values in rate_issues.items() if values]
        if issue_lines:
            st.warning("일부 행의 환율을 채우지 못했습니다. 원인:\n" + "\n".join(issue_lines))

        if not confirmed:
            if st.button("저장", type="primary"):
                st.session_state["confirmed_df"] = active_df.reset_index(drop=True)
                st.session_state["sales_confirmed"] = True

                # TODO(로그인 연동): 여기서 확정된 값을 DB에 저장하면 됩니다.
                # 예시:
                #   save_result_to_db(
                #       user_id=user.id,
                #       combined_df=st.session_state["confirmed_df"],
                #       raw_df=st.session_state["raw_df"],
                #   )

                st.rerun()

    # 엑셀 파일 생성 (메모리 상에서 바로 생성 -> 서버에 파일을 남기지 않음)
    # 화면에 표시 중인 현재 값(수정 중이면 수정본, 저장했으면 확정본) 기준으로 만듭니다.
    export_df = preview_df

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name="취합", index=False)
        for sheet_name, df in st.session_state["sheet_data"].items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        st.session_state["raw_df"].to_excel(writer, sheet_name="원본텍스트", index=False)

        if summary_row_idx is not None:
            worksheet = writer.sheets["취합"]
            bold_font = Font(bold=True)
            n_cols = export_df.shape[1]
            excel_row = summary_row_idx + 2  # 1행은 헤더
            for col_idx in range(1, n_cols + 1):
                worksheet.cell(row=excel_row, column=col_idx).font = bold_font
    excel_buffer.seek(0)

    st.download_button(
        label="엑셀 파일 다운로드",
        data=excel_buffer,
        file_name="취합결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("PDF를 업로드하고 '취합 시작하기' 버튼을 눌러주세요.")
