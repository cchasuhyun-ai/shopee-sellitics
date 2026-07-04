"""
소포수령증 업로드 (매출)
========================
여러 사용자가 PDF(소포수령증 등)를 업로드하면, 표를 자동으로 인식해서
취합한 뒤 화면에 보여주고 엑셀 파일로 다운로드할 수 있게 해주는 페이지입니다.

[향후 로그인/사용자별 저장 기능 확장 지점]
- 지금은 로그인 없이 "업로드 -> 처리 -> 다운로드"만 지원합니다.
- 나중에 Supabase 등으로 로그인을 붙이면:
    1) 로그인한 사용자 ID를 얻어온다 (예: user_id = supabase.auth.get_user().id)
    2) build_result_sheets()로 만든 결과(raw_df, combined_df)를
       사용자 ID와 함께 데이터베이스에 저장한다 (아래 "TODO(로그인 연동)" 표시 참고)
    3) 로그인한 사용자가 다시 접속했을 때, DB에서 그 사용자의 이전 결과를 불러와 보여준다
  이런 지점들을 미리 함수로 분리해두었으니, 나중에 이 부분만 교체하면 됩니다.
"""

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from pdf_processor import build_result_sheets, check_korean_ocr_support, process_pdf

st.title("소포수령증 업로드")
st.caption("매출 · 소포수령증 PDF 취합")
st.write(
    "PDF 파일들을 업로드하면 표를 자동으로 인식해서 하나로 취합합니다. "
    "결과를 화면에서 확인하고 엑셀 파일로 다운로드할 수 있습니다."
)

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

force_ocr = st.checkbox("모든 페이지를 OCR로 강제 처리 (스캔본이 많을 때 체크)", value=False)

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

        # TODO(로그인 연동): 여기서 결과를 DB에 저장하면 됩니다.
        # 예시:
        #   save_result_to_db(user_id=user.id, combined_df=combined_df, raw_df=raw_df)

# ------------------------------------------------------------------
# 2) 결과 표시 + 다운로드
# ------------------------------------------------------------------
if "combined_df" in st.session_state:
    st.success("취합이 완료되었습니다.")

    tab1, tab2 = st.tabs(["취합 결과", "원본텍스트 (백업용)"])

    with tab1:
        st.dataframe(st.session_state["combined_df"], use_container_width=True)

    with tab2:
        st.dataframe(st.session_state["raw_df"], use_container_width=True)

    # 엑셀 파일 생성 (메모리 상에서 바로 생성 -> 서버에 파일을 남기지 않음)
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        st.session_state["combined_df"].to_excel(writer, sheet_name="취합", index=False)
        for sheet_name, df in st.session_state["sheet_data"].items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        st.session_state["raw_df"].to_excel(writer, sheet_name="원본텍스트", index=False)
    excel_buffer.seek(0)

    st.download_button(
        label="엑셀 파일 다운로드",
        data=excel_buffer,
        file_name="취합결과.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("PDF를 업로드하고 '취합 시작하기' 버튼을 눌러주세요.")
