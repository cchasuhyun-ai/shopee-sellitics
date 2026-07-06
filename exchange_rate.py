"""
exchange_rate.py
=================
smbs.biz '오늘의 환율' 페이지에서 특정 날짜 기준 통화별 매매기준율(원화 환산율)을 가져오는
유틸리티입니다. 이 사이트는 값을 문자 치환 방식으로 살짝 난독화해서 내려주므로, 그 규칙을
그대로 복원해서 사용합니다.
"""

import logging
import re

import requests

logger = logging.getLogger(__name__)

EXRATE_URL = "http://www.smbs.biz/ExRate/TodayExRate.jsp"

# 소포수령증의 '도착국가' 표기(2자리 국가 코드)에서 통화 코드를 추정하기 위한 매핑
COUNTRY_CODE_TO_CURRENCY = {
    "BR": "BRL", "SG": "SGD", "MY": "MYR", "TW": "TWD",
    "TH": "THB", "PH": "PHP", "VN": "VND", "MX": "MXN",
}

# 소포수령증의 '도착국가' 표기(2자리 국가 코드)를 한글 국가명으로 바꾸기 위한 매핑
COUNTRY_CODE_TO_NAME = {
    "BR": "브라질", "SG": "싱가포르", "MY": "말레이시아", "TW": "대만",
    "TH": "태국", "PH": "필리핀", "VN": "베트남", "MX": "멕시코",
}

# 소포수령증의 '도착국가' 표기(한글)에서 통화 코드를 추정하기 위한 매핑
COUNTRY_TO_CURRENCY = {
    "일본": "JPY", "중국": "CNH", "유럽": "EUR", "유로": "EUR", "영국": "GBP",
    "캐나다": "CAD", "홍콩": "HKD", "스위스": "CHF", "호주": "AUD", "뉴질랜드": "NZD",
    "몽골": "MNT", "카자흐스탄": "KZT", "태국": "THB", "대만": "TWD", "말레이시아": "MYR",
    "베트남": "VND", "브루나이": "BND", "인도네시아": "IDR", "인도": "INR",
    "파키스탄": "PKR", "방글라데시": "BDT", "멕시코": "MXN", "브라질": "BRL",
    "아르헨티나": "ARS", "러시아": "RUB", "헝가리": "HUF", "폴란드": "PLN", "체코": "CZK",
    "카타르": "QAR", "이스라엘": "ILS", "요르단": "JOD", "터키": "TRY",
    "남아프리카": "ZAR", "남아공": "ZAR", "이집트": "EGP", "캄보디아": "KHR",
    "마카오": "MOP", "네팔": "NPR", "스리랑카": "LKR", "우즈베키스탄": "UZS",
    "미얀마": "MMK", "칠레": "CLP", "콜롬비아": "COP", "루마니아": "RON", "오만": "OMR",
    "케냐": "KES", "리비아": "LYD", "에티오피아": "ETB", "피지": "FJD",
    "사우디아라비아": "SAR", "사우디": "SAR", "아랍에미리트": "AED", "쿠웨이트": "KWD",
    "바레인": "BHD", "싱가포르": "SGD", "미국": "USD", "필리핀": "PHP",
    "스웨덴": "SEK", "노르웨이": "NOK", "덴마크": "DKK",
}

_OBFUSCATION_MARKERS = ("_Z", "_A", "_B", "_C", "_D")
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_SCRIPT_RE = re.compile(r"d[1-5]\(\s*'([^']*)'\s*\)")
_TAG_RE = re.compile(r"<[^>]+>")
_CODE_RE = re.compile(r"\(([A-Z]{3})\)")

_rate_cache = {}


def _js_unescape(text):
    """JS escape()로 만들어진 %uXXXX / %XX 표기를 원래 문자로 복원합니다."""
    chars = []
    i = 0
    while i < len(text):
        if text[i] == "%" and i + 1 < len(text):
            if text[i + 1] == "u":
                chars.append(chr(int(text[i + 2:i + 6], 16)))
                i += 6
            else:
                chars.append(chr(int(text[i + 1:i + 3], 16)))
                i += 3
        else:
            chars.append(text[i])
            i += 1
    return "".join(chars)


def _decode(raw):
    for marker in _OBFUSCATION_MARKERS:
        raw = raw.replace(marker, "")
    return _js_unescape(raw)


def _cell_value(cell_html):
    """<td> 안의 값을 가져옵니다. d[1-5](...)로 난독화된 값은 복원하고,
    (일부 셀처럼) 그냥 평문으로 들어있는 값은 태그만 제거해서 반환합니다."""
    script_match = _SCRIPT_RE.search(cell_html)
    if script_match:
        return _decode(script_match.group(1))
    return _TAG_RE.sub("", cell_html).strip()


def fetch_exchange_rates(target_date):
    """지정한 날짜의 통화별 1단위당 원화 환산 매매기준율을 조회합니다.
    반환: {통화코드: 1단위당 원화}. 조회 실패 시 빈 dict를 반환합니다(같은 날짜는 캐시됨).
    """
    cache_key = target_date.isoformat()
    if cache_key in _rate_cache:
        return _rate_cache[cache_key]

    rates = {}
    try:
        response = requests.post(
            EXRATE_URL,
            data={
                "StrSch_Year": f"{target_date.year:04d}",
                "StrSch_Month": f"{target_date.month:02d}",
                "StrSch_Day": f"{target_date.day:02d}",
                "StrSchFull": target_date.strftime("%Y.%m.%d"),
            },
            timeout=10,
        )
        response.encoding = "euc-kr"
        html = response.text

        for row_html in _ROW_RE.findall(html):
            row_html = re.sub(r"<!--.*?-->", "", row_html, flags=re.S)
            cells = _CELL_RE.findall(row_html)
            if len(cells) < 2:
                continue
            label = _cell_value(cells[0])
            rate_text = _cell_value(cells[1])
            code_match = _CODE_RE.search(label)
            if not code_match:
                continue
            try:
                rate = float(rate_text.replace(",", ""))
            except ValueError:
                continue
            if "(100)" in label:
                rate /= 100
            rates[code_match.group(1)] = rate
    except Exception:
        logger.exception("환율 조회 실패 (target_date=%s)", target_date)
        rates = {}

    if rates:
        _rate_cache[cache_key] = rates
    else:
        logger.warning("환율 조회 결과가 비어있습니다 (target_date=%s)", target_date)
    return rates


def get_currency_for_country(country_text):
    """'도착국가' 표기(예: 'BR', '필리핀', '베트남(하노이)')에서 통화 코드를 추정합니다."""
    if not country_text:
        return None
    text = str(country_text).strip()
    if not text:
        return None
    if text.upper() in COUNTRY_CODE_TO_CURRENCY:
        return COUNTRY_CODE_TO_CURRENCY[text.upper()]
    if text in COUNTRY_TO_CURRENCY:
        return COUNTRY_TO_CURRENCY[text]
    for name, code in COUNTRY_TO_CURRENCY.items():
        if name in text:
            return code
    return None


def get_display_country_name(country_text):
    """'도착국가' 표기를 화면/엑셀에 보여줄 한글 국가명으로 변환합니다.
    이미 한글 국가명이 포함되어 있으면 원래 값을 그대로 두고, 'BR' 같은
    2자리 국가 코드인 경우에만 COUNTRY_CODE_TO_NAME으로 바꿔줍니다."""
    if not country_text:
        return country_text
    text = str(country_text).strip()
    if not text:
        return country_text
    if any(name in text for name in COUNTRY_TO_CURRENCY):
        return country_text
    return COUNTRY_CODE_TO_NAME.get(text.upper(), country_text)
