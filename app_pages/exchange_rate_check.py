"""
환율 조회 확인
========================
smbs.biz에서 날짜별 환율이 실제로 잘 조회되는지 직접 확인해보는 화면입니다.
소포수령증 업로드 탭에서 사용하는 것과 동일한 exchange_rate.py 로직을
그대로 사용하므로, 여기서 정상적으로 나오는데 취합 결과 표에서 계속
None/빈 값이 나온다면 도착국가/발행일 값 자체(또는 인식 실패)가
원인일 가능성이 높습니다.
"""

from datetime import date

import pandas as pd
import streamlit as st

from exchange_rate import COUNTRY_CODE_TO_CURRENCY, COUNTRY_CODE_TO_NAME, fetch_exchange_rates

st.title("환율 조회 확인")
st.write(
    "일자를 선택하면 소포수령증 업로드에서 사용하는 8개국(브라질/싱가포르/말레이시아/대만/"
    "태국/필리핀/베트남/멕시코)의 환율을 smbs.biz에서 직접 조회해서 보여줍니다."
)

selected_date = st.date_input("조회할 발행일", value=date.today())

if st.button("환율 조회", type="primary"):
    with st.spinner("smbs.biz에서 환율을 조회하는 중..."):
        rates = fetch_exchange_rates(selected_date)

    rows = []
    for code, currency in COUNTRY_CODE_TO_CURRENCY.items():
        rate = rates.get(currency)
        rows.append(
            {
                "국가코드": code,
                "국가명": COUNTRY_CODE_TO_NAME.get(code, ""),
                "화폐": currency,
                "환율": rate if rate is not None else "",
            }
        )
    result_df = pd.DataFrame(rows)

    if not rates:
        st.error(
            "smbs.biz에서 이 날짜의 환율 데이터를 전혀 받아오지 못했습니다. "
            "네트워크 문제이거나 사이트 응답 형식이 바뀌었을 수 있습니다."
        )
    else:
        missing = result_df[result_df["환율"] == ""]["국가명"].tolist()
        if missing:
            st.warning(f"다음 국가의 환율만 조회되지 않았습니다: {', '.join(missing)}")
        else:
            st.success(f"{selected_date:%Y-%m-%d} 기준 8개국 환율을 모두 정상적으로 조회했습니다.")

    st.dataframe(result_df, width="stretch", hide_index=True)
