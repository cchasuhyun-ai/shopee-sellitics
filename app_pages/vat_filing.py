"""
부가세 신고 (신고)
====================
홈택스 부가가치세 신고서 화면에 이 앱에서 계산한 금액을 어느 항목에 입력해야 하는지
안내하는 페이지입니다.

부가가치세 신고서 입력 화면은 홈택스 로그인(공동인증서/간편인증) 후에만 접근할 수 있어
실제 화면을 캡처해서 보여줄 수 없습니다. 대신 국세청 부가가치세 신고서(일반과세자, 별지
제21호 서식)의 항목 구분번호·명칭을 기준으로 한 표를 만들고, '소포수령증 업로드', '그 밖의
매출 입력', '매입세액 입력' 탭에서 저장(확정)한 값을 함께 보여줘서 어떤 금액을 신고서의
어느 항목에 입력하면 되는지 확인할 수 있게 했습니다.
"""

from datetime import date

import pandas as pd
import streamlit as st

from pdf_processor import (
    VAT_HALF_OPTIONS,
    apply_vat_period_filter,
    get_vat_period,
    to_numeric_series,
)

EXPORT_AMOUNT_COLUMN = "수출신고금액"

st.title("부가세 신고")
st.caption("신고 · 홈택스 부가가치세 신고서 작성 안내")
st.write(
    "이 앱의 각 탭에서 저장(확정)한 매출·매입 금액을 국세청 부가가치세 신고서 항목에 맞춰 "
    "정리했습니다. 홈택스 신고서 작성 화면에서 아래 표의 '구분번호'에 해당하는 칸에 금액을 "
    "그대로 입력하면 됩니다."
)

st.info(
    "ℹ️ **안내**: 부가가치세 신고서 입력 화면은 홈택스 로그인(공동인증서/간편인증) 후에만 "
    "접근할 수 있어 실제 화면 캡처 대신 국세청 공식 서식의 항목 구분번호·명칭을 기준으로 한 "
    "표로 안내합니다. 서식 항목 번호는 국세청 고시 개정에 따라 달라질 수 있으니, 정확한 위치는 "
    "홈택스 화면의 항목명(구분)을 기준으로 확인하세요."
)

st.divider()

# ------------------------------------------------------------------
# 1) 홈택스 신고서 작성 화면 진입 경로
# ------------------------------------------------------------------
st.subheader("1. 홈택스 신고서 작성 화면 진입 경로")
st.markdown(
    """
1. 홈택스(www.hometax.go.kr) 로그인 (공동인증서 · 금융인증서 · 간편인증 중 선택)
2. 상단 메뉴 `세금신고` → `부가가치세신고` 클릭
3. 사업자 유형에서 `일반과세자` 선택 → 신고서 종류에서 `정기신고(확정신고)` 선택
   (예정신고 대상이 아닌 개인사업자는 보통 확정신고만 진행하면 됩니다)
4. 기본정보(사업자등록번호, 과세기간 등)를 확인하고 `저장 후 다음이동`
5. 아래 "2. 과세표준 및 매출세액"과 "3. 매입세액" 표를 참고해 각 항목 금액을 입력
6. 입력을 마치면 자동 계산되는 `차가감하여 납부할세액(환급받을세액)`이 "4. 납부(환급)세액
   계산 확인"의 값과 비슷한지 확인 후 신고서를 제출
"""
)

st.divider()

# ------------------------------------------------------------------
# 2) 과세기간 선택
# ------------------------------------------------------------------
st.subheader("2. 과세기간 선택")

today = date.today()
default_half_index = 0 if today.month <= 6 else 1

period_col1, period_col2 = st.columns([1, 5])
with period_col1:
    vat_year = st.number_input(
        "신고연도", min_value=2000, max_value=2100, value=today.year, step=1, key="period_year"
    )
with period_col2:
    vat_half = st.radio(
        "신고기간(반기)", VAT_HALF_OPTIONS, index=default_half_index, horizontal=True, key="vf_half"
    )

period_start, period_end, filing_deadline = get_vat_period(int(vat_year), vat_half)
st.info(f"신고 대상기간: {period_start:%Y-%m-%d} ~ {period_end:%Y-%m-%d}  |  신고기한: {filing_deadline}")

st.divider()


def get_row_value(df: pd.DataFrame | None, label: str, column: str = "세액") -> float:
    """요약 표(df)에서 '구분' 열이 label과 일치하는 행의 값을 찾아 반환. 없으면 0."""
    if df is None or df.empty or "구분" not in df.columns:
        return 0.0
    matched = df.loc[df["구분"] == label, column]
    if matched.empty:
        return 0.0
    value = matched.iloc[0]
    return float(value) if pd.notna(value) else 0.0


missing_notices = []

# 영세율 과세표준 (해외배송/수출) - '소포수령증 업로드' 탭 확정값
zero_rate_base = 0.0
if st.session_state.get("sales_confirmed") and "confirmed_df" in st.session_state:
    sales_df = st.session_state["confirmed_df"]
    if not sales_df.empty and "출처파일" in sales_df.columns:
        in_period_mask, amount_cols = apply_vat_period_filter(sales_df, period_start, period_end)
        base_col = EXPORT_AMOUNT_COLUMN if EXPORT_AMOUNT_COLUMN in amount_cols else (
            amount_cols[0] if amount_cols else None
        )
        if base_col:
            zero_rate_base = float(to_numeric_series(sales_df.loc[in_period_mask, base_col]).fillna(0).sum())
else:
    missing_notices.append("'소포수령증 업로드' 탭에서 저장(확정)된 매출 데이터가 없습니다.")

# 그 밖의 매출 입력 (국내 과세 매출) - 항목별 세부값
other_sales_df = st.session_state.get("other_sales_summary")
if not st.session_state.get("other_sales_confirmed"):
    missing_notices.append("'그 밖의 매출 입력' 탭에서 저장(확정)된 값이 없습니다.")

tax_invoice_issued_supply = get_row_value(other_sales_df, "세금계산서 발급분", "공급가액")
tax_invoice_issued_tax = get_row_value(other_sales_df, "세금계산서 발급분", "세액")
card_cash_issued_supply = get_row_value(other_sales_df, "신용카드매출전표 · 현금영수증 발행분", "공급가액")
card_cash_issued_tax = get_row_value(other_sales_df, "신용카드매출전표 · 현금영수증 발행분", "세액")
etc_sales_supply = get_row_value(other_sales_df, "기타(정규영수증 외 매출분)", "공급가액")
etc_sales_tax = get_row_value(other_sales_df, "기타(정규영수증 외 매출분)", "세액")

# 매입세액 입력 - 항목별 세부값
purchase_df = st.session_state.get("purchase_tax_summary")
if not st.session_state.get("purchase_confirmed"):
    missing_notices.append("'매입세액 입력' 탭에서 저장(확정)된 값이 없습니다.")

if missing_notices:
    st.warning(
        "다음 탭에서 값을 먼저 저장(확정)해야 정확한 금액이 표시됩니다 "
        "(해당 사항이 없으면 0으로 표시됩니다):\n" + "\n".join(f"- {m}" for m in missing_notices)
    )

# ------------------------------------------------------------------
# 3) 과세표준 및 매출세액
# ------------------------------------------------------------------
st.subheader("3. 과세표준 및 매출세액 입력 항목")

sales_mapping_df = pd.DataFrame(
    [
        {
            "구분번호": "①",
            "신고서 항목명": "과세 - 세금계산서발급분",
            "공급가액": tax_invoice_issued_supply,
            "세액": tax_invoice_issued_tax,
            "데이터 출처": "그 밖의 매출 입력 - 세금계산서 발급분",
        },
        {
            "구분번호": "③",
            "신고서 항목명": "과세 - 신용카드·현금영수증발행분",
            "공급가액": card_cash_issued_supply,
            "세액": card_cash_issued_tax,
            "데이터 출처": "그 밖의 매출 입력 - 신용카드매출전표·현금영수증 발행분",
        },
        {
            "구분번호": "④",
            "신고서 항목명": "과세 - 기타(정규영수증외매출분)",
            "공급가액": etc_sales_supply,
            "세액": etc_sales_tax,
            "데이터 출처": "그 밖의 매출 입력 - 기타(정규영수증 외 매출분)",
        },
        {
            "구분번호": "⑥",
            "신고서 항목명": "영세율 - 기타",
            "공급가액": zero_rate_base,
            "세액": 0.0,
            "데이터 출처": "소포수령증 업로드 (해외배송/수출, 영세율)",
        },
    ]
)
st.dataframe(sales_mapping_df, width="stretch", hide_index=True)
st.caption(
    "※ 세금계산서를 발급하지 않은 해외배송(역직구) 매출은 통상 '영세율 - 기타(⑥)' 항목에 "
    "입력하고, 영세율 첨부서류(수출실적명세서 등)를 함께 제출합니다. 국내 거래처에 전자세금계산서를 "
    "발급한 매출이 있다면 '과세 - 세금계산서발급분(①)'에 반영하세요."
)

st.divider()

# ------------------------------------------------------------------
# 4) 매입세액
# ------------------------------------------------------------------
st.subheader("4. 매입세액 입력 항목")

general_purchase_supply = get_row_value(purchase_df, "세금계산서 수취분 - 일반매입", "공급가액")
general_purchase_tax = get_row_value(purchase_df, "세금계산서 수취분 - 일반매입", "세액")
deferred_supply = get_row_value(purchase_df, "세금계산서 수취분 - 수출기업 수입분 납부유예", "공급가액")
deferred_tax = get_row_value(purchase_df, "세금계산서 수취분 - 수출기업 수입분 납부유예", "세액")
fixed_asset_supply = get_row_value(purchase_df, "세금계산서 수취분 - 고정자산 매입", "공급가액")
fixed_asset_tax = get_row_value(purchase_df, "세금계산서 수취분 - 고정자산 매입", "세액")
missed_supply = get_row_value(purchase_df, "예정신고 누락분", "공급가액")
missed_tax = get_row_value(purchase_df, "예정신고 누락분", "세액")
buyer_issued_supply = get_row_value(purchase_df, "매입자발행 세금계산서", "공급가액")
buyer_issued_tax = get_row_value(purchase_df, "매입자발행 세금계산서", "세액")

other_deductible_labels = [
    "신용카드매출전표 등 수취명세서 제출분 - 일반매입",
    "신용카드매출전표 등 수취명세서 제출분 - 고정자산매입",
    "의제매입세액",
    "재활용폐자원 등 매입세액",
    "과세사업전환 매입세액",
    "재고매입세액",
    "변제대손세액",
    "외국인관광객에 대한 환급세액",
]
other_deductible_supply = sum(get_row_value(purchase_df, label, "공급가액") for label in other_deductible_labels)
other_deductible_tax = sum(get_row_value(purchase_df, label, "세액") for label in other_deductible_labels)

purchase_total_supply = get_row_value(purchase_df, "매입세액 합계", "공급가액")
purchase_total_tax = get_row_value(purchase_df, "매입세액 합계", "세액")
non_deductible_total_supply = get_row_value(purchase_df, "공제받지 못할 매입세액 합계", "공급가액")
non_deductible_total_tax = get_row_value(purchase_df, "공제받지 못할 매입세액 합계", "세액")
net_purchase_tax = get_row_value(purchase_df, "차감계 (공제받을 매입세액)", "세액")

purchase_mapping_df = pd.DataFrame(
    [
        {
            "구분번호": "⑩",
            "신고서 항목명": "세금계산서수취분 - 일반매입",
            "공급가액": general_purchase_supply,
            "세액": general_purchase_tax,
            "데이터 출처": "매입세액 입력 - 세금계산서 수취분(일반매입)",
        },
        {
            "구분번호": "⑩-1",
            "신고서 항목명": "수출기업 수입분 납부유예",
            "공급가액": deferred_supply,
            "세액": deferred_tax,
            "데이터 출처": "매입세액 입력 - 수출기업 수입분 납부유예",
        },
        {
            "구분번호": "⑪",
            "신고서 항목명": "세금계산서수취분 - 고정자산매입",
            "공급가액": fixed_asset_supply,
            "세액": fixed_asset_tax,
            "데이터 출처": "매입세액 입력 - 세금계산서 수취분(고정자산 매입)",
        },
        {
            "구분번호": "⑫",
            "신고서 항목명": "예정신고 누락분",
            "공급가액": missed_supply,
            "세액": missed_tax,
            "데이터 출처": "매입세액 입력 - 예정신고 누락분",
        },
        {
            "구분번호": "⑬",
            "신고서 항목명": "매입자발행세금계산서",
            "공급가액": buyer_issued_supply,
            "세액": buyer_issued_tax,
            "데이터 출처": "매입세액 입력 - 매입자발행 세금계산서",
        },
        {
            "구분번호": "⑭",
            "신고서 항목명": "그 밖의 공제매입세액",
            "공급가액": other_deductible_supply,
            "세액": other_deductible_tax,
            "데이터 출처": "매입세액 입력 - 신용카드매출전표등수취명세서제출분 + 의제매입세액 등",
        },
        {
            "구분번호": "⑮ = ⑩+⑩-1+⑪+⑫+⑬+⑭",
            "신고서 항목명": "매입세액 합계",
            "공급가액": purchase_total_supply,
            "세액": purchase_total_tax,
            "데이터 출처": "자동 합계",
        },
        {
            "구분번호": "⑯",
            "신고서 항목명": "공제받지못할매입세액",
            "공급가액": non_deductible_total_supply,
            "세액": non_deductible_total_tax,
            "데이터 출처": "매입세액 입력 - 공제받지 못할 매입세액 등",
        },
        {
            "구분번호": "⑰ = ⑮-⑯",
            "신고서 항목명": "차감계 (공제받을 매입세액)",
            "공급가액": None,
            "세액": net_purchase_tax,
            "데이터 출처": "자동 계산",
        },
    ]
)
st.dataframe(purchase_mapping_df, width="stretch", hide_index=True)
st.caption(
    "※ '카드사용내역 입력' 탭에서 저장한 값은 '매입세액 입력' 탭의 신용카드매출전표 등 항목에 "
    "자동 반영된 뒤 이 표의 ⑭ 그 밖의 공제매입세액에 합산되어 표시됩니다."
)

st.divider()

# ------------------------------------------------------------------
# 5) 납부(환급)세액 계산 확인
# ------------------------------------------------------------------
st.subheader("5. 납부(환급)세액 계산 확인")

taxable_base_total = zero_rate_base + tax_invoice_issued_supply + card_cash_issued_supply + etc_sales_supply
output_tax_total = tax_invoice_issued_tax + card_cash_issued_tax + etc_sales_tax
payable_tax = output_tax_total - net_purchase_tax

check_df = pd.DataFrame(
    [
        {"구분": "과세표준 및 매출세액 합계 (⑨)", "금액": taxable_base_total, "세액": output_tax_total},
        {"구분": "매입세액 차감계 (⑰)", "금액": None, "세액": net_purchase_tax},
        {"구분": "차가감하여 납부할세액(환급받을세액)", "금액": None, "세액": payable_tax},
    ]
)
st.dataframe(check_df, width="stretch", hide_index=True)

result_col1, result_col2 = st.columns(2)
with result_col1:
    st.metric("과세표준 및 매출세액 합계", f"{output_tax_total:,.0f} 원")
with result_col2:
    if payable_tax >= 0:
        st.metric("납부할 세액 (예상)", f"{payable_tax:,.0f} 원")
    else:
        st.metric("환급받을 세액 (예상)", f"{-payable_tax:,.0f} 원")

st.caption(
    "※ 경감·공제세액, 가산세, 예정신고 미환급세액·예정고지세액 등은 반영되지 않은 단순 계산 "
    "결과입니다. 홈택스에 항목별 금액을 모두 입력하면 신고서 화면에서 자동으로 최종 "
    "납부(환급)세액이 계산되니, 위 예상 금액과 큰 차이가 없는지 최종 확인하시기 바랍니다."
)

st.divider()

# ------------------------------------------------------------------
# 6) 함께 제출해야 하는 부속서식 작성방법
# ------------------------------------------------------------------
st.subheader("6. 함께 제출해야 하는 부속서식 작성방법")
st.write(
    "부가가치세(확정)신고서 본문 외에, Shopee 등 해외 오픈마켓을 통해 역직구 판매를 하는 "
    "개인사업자가 일반적으로 함께 작성·제출하게 되는 부속서식의 작성방법을 안내합니다. "
    "실제 해당 여부와 서식은 거래 내역에 따라 달라질 수 있으니 참고용으로 확인하세요."
)

st.markdown("**6-1. 영세율 첨부서류 - 수출실적명세서**")
st.write(
    "세금계산서를 발급하지 않은 해외배송(역직구) 매출, 즉 위 표의 '영세율 - 기타(⑥)' 금액에 "
    "대한 영세율 적용 근거를 소명하는 서식입니다. 제출하지 않으면 영세율 적용이 부인되어 "
    "가산세가 부과될 수 있으니 반드시 함께 제출하세요."
)
st.markdown(
    """
1. 홈택스 신고서 작성 화면에서 '과세표준 및 매출세액' 입력을 마치면, 영세율 매출(⑥)에 대해
   '영세율 첨부서류(수출실적명세서 등)' 작성 화면으로 이동하는 링크가 나타납니다. 이 화면에서
   건별로 작성합니다.
2. 건별 작성 항목: 수출(발송)일자, 상대국, 결제조건(예: 사전결제), 통화코드, 외화금액, 적용환율,
   원화금액. 세금계산서를 발급하지 않은 수출이므로 거래처는 최종 소비자(불특정 다수)로 처리하는
   경우가 일반적입니다.
3. 이 앱의 **'소포수령증 업로드'** 탭에서 저장(확정)한 표의 발행일(→ 수출일자), 도착국가(→
   상대국), 화폐/환율/원화환산금액, 수출신고금액(→ 외화금액) 열을 그대로 옮겨 적으면 됩니다.
4. 수출신고필증이 없는 우편(EMS 등) 발송 건은 수출신고번호 대신 우체국이 발급한 접수번호(등기
   번호) 등 발송을 증명할 수 있는 자료를 근거 자료로 보관해두고, 관련 항목 기재 방식은 홈택스
   안내 또는 세무 전문가를 통해 다시 한 번 확인하시기 바랍니다.
"""
)

st.markdown("**6-2. 신용카드매출전표 등 수령명세서**")
st.write(
    "카드사용내역이나 현금영수증으로 매입세액을 공제받는 경우('그 밖의 공제매입세액' ⑭ 중 "
    "신용카드매출전표 등 수취명세서 제출분) 함께 제출하는 서식입니다."
)
st.markdown(
    """
1. 홈택스 신고서 작성 화면의 '매입세액' 단계에서 '신용카드매출전표 등 수취명세서 제출분' 항목을
   선택하면 건별 입력 화면으로 이동합니다.
2. 건별 작성 항목: 거래일자, 가맹점명(공급자 상호), 가맹점 사업자등록번호, 카드회원번호(카드번호),
   공급가액, 세액, 구분(일반매입/고정자산매입).
3. 이 앱의 **'카드사용내역 입력'** 탭에서 저장(확정)한 표를 그대로 활용하면 됩니다. 이미 거래일자·
   가맹점명·사업자등록번호·공급가액·세액과 일반매입/고정자산매입 구분까지 정리되어 있으므로 표의
   행을 그대로 옮겨 적으면 됩니다.
4. 사업용신용카드로 국세청 홈택스에 등록된 카드는 홈택스 로그인 → `조회/발급` → `현금영수증·
   신용카드` → `사업용신용카드 사용내역 조회` 메뉴에서 매입세액공제 대상 여부까지 함께 확인할
   수 있습니다.
"""
)

st.markdown("**6-3. 건물등감가상각자산취득명세서**")
st.write(
    "비품, 인테리어, 차량, 컴퓨터·촬영장비 등 감가상각자산(고정자산)을 매입한 경우 함께 제출하는 "
    "서식으로, '매입세액 입력' 탭의 고정자산 매입 항목과 연결됩니다."
)
st.markdown(
    """
1. 홈택스 신고서 작성 화면의 '매입세액' 단계에서 '건물등감가상각자산취득명세서' 항목을 선택하면
   자산 유형별(건물·구축물 / 기계장치 / 차량운반구 / 기타감가상각자산) 입력 화면으로 이동합니다.
2. 건별 작성 항목: 자산 유형, 취득일, 거래처 상호(공급자), 사업자등록번호, 공급가액, 세액.
3. 이 앱의 **'매입세액 입력'** 탭에서 입력한 '세금계산서 수취분 - 고정자산 매입'과 **'카드사용내역
   입력'** 탭에서 '고정자산매입'으로 구분한 내역을 근거 세금계산서/카드매출전표 단위로 정리해
   자산 유형에 맞춰 입력하세요.
"""
)

st.info(
    "위 부속서식은 모두 홈택스 신고서 작성 화면 안에서 해당 항목에 금액을 입력할 때 자동으로 "
    "작성 화면으로 연결되는 경우가 많습니다. 별도로 파일을 첨부하는 방식이 아니라, 신고서 작성 "
    "흐름을 따라가며 건별로 입력하면 됩니다."
)

st.divider()

st.caption(
    "※ 이 페이지는 참고용이며 법적 효력이 있는 신고 자료가 아닙니다. 국세청 서식의 항목 구성은 "
    "고시 개정에 따라 변경될 수 있으므로, 실제 신고 시에는 홈택스 화면에 표시되는 항목명을 "
    "기준으로 최종 확인하시기 바랍니다."
)
