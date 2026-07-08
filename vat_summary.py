"""부가세 계산 결과 요약표 생성 로직
====================================
'부가세 계산' 탭과 '저장된 신고내역' 탭에서 공통으로 사용합니다. 매출/매입 자료가
현재 세션의 확정값에서 오든, DB에 저장된 과거 값에서 오든 계산 방식은 항상 같아야
하므로 이 모듈로 분리했습니다.
"""

import pandas as pd

EXPORT_AMOUNT_COLUMN = "수출신고금액"


def build_vat_summary(
    zero_rate_base: float,
    regular_sales_base: float,
    regular_sales_tax: float,
    purchase_tax_total: float,
) -> tuple[pd.DataFrame, float, float, float]:
    """영세율/과세 매출, 매입세액으로 신고 금액 요약표와 합계값을 계산합니다.

    반환값: (요약표 DataFrame, 과세표준 합계, 매출세액 합계, 납부(환급)할 세액)
    """
    taxable_base_total = zero_rate_base + regular_sales_base
    output_tax_total = regular_sales_tax  # 영세율분은 세액 0
    payable_tax = output_tax_total - purchase_tax_total

    summary_df = pd.DataFrame(
        [
            {"구분": "영세율 과세표준 (해외배송/수출)", "공급가액": zero_rate_base, "세액": 0},
            {"구분": "과세 매출 (일반, 10%)", "공급가액": regular_sales_base, "세액": regular_sales_tax},
            {"구분": "과세표준 및 매출세액 합계", "공급가액": taxable_base_total, "세액": output_tax_total},
            {"구분": "매입세액 (차감계)", "공급가액": None, "세액": purchase_tax_total},
            {"구분": "납부(환급)할 세액", "공급가액": None, "세액": payable_tax},
        ]
    )
    return summary_df, taxable_base_total, output_tax_total, payable_tax
