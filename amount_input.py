"""공급가액/세액 등 금액을 입력받는 위젯 헬퍼.

st.number_input의 +/- 버튼을 없애고 직접 타이핑으로만 입력받되, 입력을 마치면
(포커스 아웃 또는 Enter) 천 단위 콤마가 자동으로 표시되도록 st.text_input을
감싸서 제공합니다.
"""

import streamlit as st

AMOUNT_INPUT_CSS = """
<style>
button[data-testid="stNumberInputStepUp"],
button[data-testid="stNumberInputStepDown"] {
    display: none;
}
div[data-testid="stNumberInputContainer"] input {
    text-align: right;
}
div[class*="st-key-amt_"] input {
    text-align: right;
}
</style>
"""


def inject_amount_input_css() -> None:
    """숫자 입력의 +/- 버튼 숨김 및 오른쪽 정렬 CSS를 적용합니다. (앱 진입점에서 한 번만 호출)"""
    st.markdown(AMOUNT_INPUT_CSS, unsafe_allow_html=True)


def amount_input(label: str, key: str, *, disabled: bool = False, label_visibility: str = "collapsed") -> int:
    """콤마(,)가 포함된 금액을 직접 타이핑으로 입력받고, 정수(int) 값을 반환합니다."""
    widget_key = f"amt_{key}"
    raw = st.session_state.get(widget_key, "0")
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    st.session_state[widget_key] = f"{int(digits):,}" if digits else "0"

    st.text_input(label, key=widget_key, disabled=disabled, label_visibility=label_visibility)

    digits = "".join(ch for ch in str(st.session_state[widget_key]) if ch.isdigit())
    return int(digits) if digits else 0
