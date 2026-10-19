"""정형쿼리 FQ-01 ~ FQ-14와 LLM 실패 시 쓰는 키워드 규칙(설계서 부록 B, 키워드 표).

번호는 설계서(2026-10-19, 3조 반영)를 따름. FQ-01 ~ FQ-09는 기본 예제, FQ-10 ~ FQ-14는 3조(VIP 이탈 방지)가 더함.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class FixedQuery:
    """검사까지 끝낸 고정 조회 1개."""

    query_id: str
    description: str
    view: str  # 읽는 허용 뷰. S-R3 기간 판정에 씀
    sql: str  # 설계서 work/fixed_queries.json의 SQL 그대로(LIMIT은 S-R4 검사기가 붙임)


# SQL 전문 출처: design/sql-retriever/work/fixed_queries.json (FQ-10 ~ FQ-14는 3조가 2026-10-19에 더함)
FIXED_QUERIES: dict[str, FixedQuery] = {
    q.query_id: q
    for q in (
        FixedQuery(
            "FQ-01",
            "고객 기본정보",
            "app.customer_profile",
            "SELECT join_date, age_band FROM app.customer_profile",
        ),
        FixedQuery(
            "FQ-02",
            "보유 카드 목록",
            "app.customer_cards",
            "SELECT card_ref, product_name, brand, issue_date, current_status, annual_fee\n"
            "FROM app.customer_cards ORDER BY card_ref",
        ),
        FixedQuery(
            "FQ-03",
            "카드별 월 이용금액(6개월)",
            "app.monthly_usage",
            "SELECT card_ref, month, approved_amount, transaction_count\n"
            "FROM app.monthly_usage ORDER BY month, card_ref",
        ),
        FixedQuery(
            "FQ-04",
            "월별 이용금액 합계(6개월)",
            "app.monthly_usage",
            "SELECT month, sum(approved_amount)::bigint AS approved_amount, "
            "sum(transaction_count)::integer AS transaction_count\n"
            "FROM app.monthly_usage GROUP BY month ORDER BY month",
        ),
        FixedQuery(
            "FQ-05",
            "최근 연체 현황",
            "app.customer_delinquency",
            "SELECT base_month, as_of_date, overdue_amount, overdue_days, overdue_count_12m\n"
            "FROM app.customer_delinquency",
        ),
        FixedQuery(
            "FQ-06",
            "연체 이력(12개월)",
            "app.customer_delinquency_history",
            "SELECT base_month, as_of_date, overdue_amount, overdue_days, overdue_count_12m\n"
            "FROM app.customer_delinquency_history ORDER BY base_month",
        ),
        FixedQuery(
            "FQ-07",
            "일별 이용금액(90일)",
            "app.customer_daily_usage",
            "SELECT usage_date, approved_amount, transaction_count\n"
            "FROM app.customer_daily_usage ORDER BY usage_date",
        ),
        FixedQuery(
            "FQ-08",
            "업종별 이용금액(6개월)",
            "app.merchant_usage",
            "SELECT category, sum(approved_amount)::bigint AS approved_amount, "
            "sum(transaction_count)::integer AS transaction_count\n"
            "FROM app.merchant_usage GROUP BY category ORDER BY approved_amount DESC",
        ),
        FixedQuery(
            "FQ-09",
            "가맹점 이용 상위 10곳",
            "app.merchant_usage",
            "SELECT merchant_name, category, sum(approved_amount)::bigint AS approved_amount, "
            "sum(transaction_count)::integer AS transaction_count\n"
            "FROM app.merchant_usage GROUP BY merchant_name, category ORDER BY approved_amount DESC LIMIT 10",
        ),
        # ---- 3조 추가(VIP 이탈 방지) ----
        FixedQuery(
            "FQ-10",
            "월 사용액 추이와 전월 대비",
            "app.vip_monthly_trend",
            "SELECT month, approved_amount, transaction_count, change_amount, change_rate_pct, is_partial_month\n"
            "FROM app.vip_monthly_trend ORDER BY month",
        ),
        FixedQuery(
            "FQ-11",
            "연회비 대비 사용액",
            "app.vip_annual_fee_burden",
            "SELECT card_ref, product_name, annual_fee, recent_period_amount, avg_monthly_amount, "
            "yearly_usage_to_fee_ratio\n"
            "FROM app.vip_annual_fee_burden ORDER BY card_ref",
        ),
        FixedQuery(
            "FQ-12",
            "최근 활동 신호",
            "app.vip_activity_signal",
            "SELECT last_approved_date, days_since_last_approved, approved_count_last_30d, "
            "approved_count_prev_30d, approved_amount_last_30d, approved_amount_prev_30d\n"
            "FROM app.vip_activity_signal",
        ),
        FixedQuery(
            "FQ-13",
            "업종별 사용액 비중과 순위",
            "app.vip_category_share",
            "SELECT category, approved_amount, transaction_count, share_pct, amount_rank\n"
            "FROM app.vip_category_share ORDER BY amount_rank, category",
        ),
        FixedQuery(
            "FQ-14",
            "이탈 신호 종합",
            "app.vip_churn_signal_summary",
            "SELECT recent_3m_avg_amount, prev_avg_amount, recent_month_count, prev_month_count, "
            "change_rate_pct, days_since_last_approved, approved_count_last_30d, approved_count_prev_30d\n"
            "FROM app.vip_churn_signal_summary",
        ),
    )
}


def _any(*words: str) -> Callable[[str], bool]:
    return lambda text: any(word in text for word in words)


def _all_of(*groups: tuple[str, ...]) -> Callable[[str], bool]:
    """각 묶음에서 낱말을 하나 이상 포함해야 맞는 규칙을 만듦."""
    return lambda text: all(any(word in text for word in group) for group in groups)


_HISTORY_WORDS = ("이력", "내역", "12개월")

# 대체 경로 키워드(설계서 키워드 표, 설계 가정 A-4). 위에서부터 차례로 맞춰 처음 맞는 1개를 씀.
# 띄어쓰기는 지우고 비교함(사용자 승인 P-05). 그래서 키워드도 띄어쓰기 없이 적음.
# 3조 규칙(FQ-14, 11, 13, 12, 10)은 "연회비", "업종"처럼 기본 규칙과 겹치는 낱말이 있어 기본 규칙보다 앞에 둠.
# 그래야 "연회비 얼마예요"는 FQ-02가, "연회비 대비 사용액"은 FQ-11이 받음.
KEYWORD_RULES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("FQ-14", _all_of(("이탈",), ("신호", "위험", "징후"))),
    ("FQ-11", _all_of(("연회비",), ("대비", "부담", "본전"))),
    ("FQ-13", _all_of(("업종",), ("비중", "비율", "순위", "주로"))),
    ("FQ-12", _any("마지막", "경과", "활동", "휴면")),
    ("FQ-10", _any("추이", "증감", "전월")),
    ("FQ-01", _any("가입일", "연령")),
    ("FQ-02", _any("보유카드", "카드목록", "연회비")),
    ("FQ-03", lambda text: "카드별" in text and _any("월", "사용")(text)),
    ("FQ-04", _any("월별", "월사용", "지난달", "이번달")),
    # FQ-05는 "연체"이되 이력 표현이 없을 때만. 이력 표현이 있으면 아래 FQ-06이 받음
    ("FQ-05", lambda text: "연체" in text and not _any(*_HISTORY_WORDS)(text)),
    ("FQ-06", lambda text: "연체" in text and _any(*_HISTORY_WORDS)(text)),
    ("FQ-07", _any("일별", "날짜별", "90일")),
    ("FQ-08", _any("업종", "어디서")),
    ("FQ-09", _any("가맹점")),
)

_WHITESPACE = re.compile(r"\s+")


def match_keyword_rule(question: str) -> str | None:
    """키워드 규칙으로 정형쿼리ID 1개를 고름.

    반환값: 처음 맞는 정형쿼리ID. 맞는 규칙이 없으면 None을 반환함.
    """
    text = _WHITESPACE.sub("", question)
    for query_id, rule in KEYWORD_RULES:
        if rule(text):
            return query_id
    return None
