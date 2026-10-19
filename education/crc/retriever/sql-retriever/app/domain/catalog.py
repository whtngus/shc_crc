"""NL2SQL에 허용한 뷰와 컬럼, 함수, 금지 목록(부록 29장, 31장, db_catalog.json)."""

from __future__ import annotations

ALLOWED_SCHEMA = "app"
ROW_LIMIT = 200  # 결과 행 상한(31장)

# 뷰 이름 → 컬럼 이름 목록. 출처: design/sql-retriever/work/db_catalog.json(2026-10-15 실측 7개, 3조 추가 5개는 2026-10-19 SQL에서 옮김)
ALLOWED_VIEWS: dict[str, tuple[str, ...]] = {
    "app.customer_profile": ("join_date", "age_band"),
    "app.customer_cards": (
        "card_ref",
        "product_id",
        "product_name",
        "brand",
        "issue_date",
        "current_status",
        "product_effective_date",
        "is_product_effective_on_base_date",
        "annual_fee",
    ),
    "app.monthly_usage": (
        "card_ref",
        "month",
        "period_start",
        "period_end",
        "approved_amount",
        "transaction_count",
    ),
    "app.merchant_usage": (
        "card_ref",
        "month",
        "period_start",
        "period_end",
        "merchant_name",
        "category",
        "first_approved_date",
        "last_approved_date",
        "approved_amount",
        "transaction_count",
    ),
    "app.customer_delinquency": (
        "base_month",
        "as_of_date",
        "overdue_amount",
        "overdue_days",
        "overdue_count_12m",
    ),
    "app.customer_delinquency_history": (
        "base_month",
        "as_of_date",
        "overdue_amount",
        "overdue_days",
        "overdue_count_12m",
    ),
    "app.customer_daily_usage": ("usage_date", "approved_amount", "transaction_count"),
    # ---- 3조 추가 뷰(VIP 이탈 방지, rdb/init/07_vip_churn_views.sql). DB 미실행이라 SQL에서 옮긴 컬럼임 ----
    "app.vip_monthly_trend": (
        "month",
        "approved_amount",
        "transaction_count",
        "prev_month_amount",
        "change_amount",
        "change_rate_pct",
        "is_partial_month",
    ),
    "app.vip_annual_fee_burden": (
        "card_ref",
        "product_name",
        "annual_fee",
        "recent_period_amount",
        "usage_month_count",
        "avg_monthly_amount",
        "yearly_usage_to_fee_ratio",
    ),
    "app.vip_activity_signal": (
        "last_approved_date",
        "days_since_last_approved",
        "approved_count_last_30d",
        "approved_count_prev_30d",
        "approved_amount_last_30d",
        "approved_amount_prev_30d",
    ),
    "app.vip_category_share": ("category", "approved_amount", "transaction_count", "share_pct", "amount_rank"),
    "app.vip_churn_signal_summary": (
        "recent_3m_avg_amount",
        "prev_avg_amount",
        "recent_month_count",
        "prev_month_count",
        "change_rate_pct",
        "days_since_last_approved",
        "approved_count_last_30d",
        "approved_count_prev_30d",
    ),
}

# 허용 함수(31장 허용 4번). 형변환은 별도 구문(CAST, ::)으로 검사기에서 따로 허용함
ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
    {
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "date_trunc",
        "to_char",
        "extract",
        "coalesce",
        "round",
        "greatest",
        "least",
        "abs",
    }
)

# 금지 함수(31장 금지 3번). 허용 목록 밖이면 어차피 막히지만, 사유 코드를 따로 남기려고 둠
FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {"set_config", "current_setting", "generate_series", "pg_sleep"}
)
FORBIDDEN_FUNCTION_PREFIX = "pg_"

# 금지 스키마(31장 금지 4번)
FORBIDDEN_SCHEMAS: frozenset[str] = frozenset(
    {"app_internal", "public", "pg_catalog", "information_schema"}
)


def is_allowed_view(name: str) -> bool:
    """스키마 이름을 붙인 뷰 이름이 허용 뷰 12개 중 하나인지 확인함."""
    return name in ALLOWED_VIEWS
