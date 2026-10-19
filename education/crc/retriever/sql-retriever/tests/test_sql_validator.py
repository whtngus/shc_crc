"""SQL 검증 규칙(부록 31장)의 허용 예와 금지 예를 하나씩 넣어 결과가 설계서와 같은지 확인함."""

import sqlglot
import pytest

from app.domain.catalog import ALLOWED_VIEWS
from app.domain.fixed_queries import FIXED_QUERIES
from app.infrastructure.sql_validator import SqlglotValidator

validator = SqlglotValidator()


def _limit(sql: str) -> int:
    tree = sqlglot.parse_one(sql, read="postgres")
    return int(tree.args["limit"].expression.name)


@pytest.mark.parametrize("query_id", sorted(FIXED_QUERIES))
def test_fixed_queries_pass(query_id):
    """정형쿼리도 같은 검사를 거침(이중 안전장치, 14장 비고)."""
    result = validator.validate(FIXED_QUERIES[query_id].sql)
    assert result.ok, result.reason
    assert _limit(result.sql) == 200


# 31장 허용 1 ~ 5번 항목마다 하나 이상
ALLOWED_EXAMPLES = {
    "허용 1 뷰(스키마 이름 붙임)": "SELECT join_date FROM app.customer_profile",
    "허용 2 컬럼": "SELECT card_ref, annual_fee FROM app.customer_cards",
    "허용 3 WITH": "WITH m AS (SELECT month, sum(approved_amount) AS amt FROM app.monthly_usage GROUP BY month) "
    "SELECT m.month, m.amt FROM m ORDER BY m.amt DESC",
    "허용 3 WHERE, GROUP BY, HAVING, ORDER BY": "SELECT category, sum(approved_amount) AS amt FROM app.merchant_usage "
    "WHERE month = '2026-07' GROUP BY category HAVING sum(approved_amount) > 0 ORDER BY amt DESC",
    "허용 3 JOIN": "SELECT c.product_name, u.month FROM app.customer_cards c "
    "JOIN app.monthly_usage u ON u.card_ref = c.card_ref",
    "허용 3 서브쿼리": "SELECT usage_date FROM app.customer_daily_usage "
    "WHERE approved_amount > (SELECT avg(approved_amount) FROM app.customer_daily_usage)",
    "허용 4 함수": "SELECT date_trunc('month', usage_date)::date AS m, to_char(usage_date, 'YYYY-MM'), "
    "extract(year FROM usage_date), coalesce(approved_amount, 0), round(avg(approved_amount), 1), "
    "greatest(1, 2), least(1, 2), abs(-1), count(*), min(usage_date), max(usage_date), "
    "sum(transaction_count), CAST(approved_amount AS text) FROM app.customer_daily_usage GROUP BY 1, 2, 3, 4, 13",
    "허용 5 LIMIT 이하 유지": "SELECT usage_date FROM app.customer_daily_usage LIMIT 3",
}


@pytest.mark.parametrize("label", sorted(ALLOWED_EXAMPLES))
def test_allowed_examples(label):
    result = validator.validate(ALLOWED_EXAMPLES[label])
    assert result.ok, f"{label}: {result.reason}"


def test_limit_added_when_missing():
    assert _limit(validator.validate("SELECT usage_date FROM app.customer_daily_usage").sql) == 200


def test_limit_lowered_when_over_200():
    assert _limit(validator.validate("SELECT usage_date FROM app.customer_daily_usage LIMIT 1000").sql) == 200


def test_limit_kept_when_small():
    assert _limit(validator.validate("SELECT usage_date FROM app.customer_daily_usage LIMIT 3").sql) == 3


# 31장 금지 1 ~ 4번 항목마다 하나 이상, 그리고 허용 목록 밖(기본 거부)
FORBIDDEN_EXAMPLES = {
    "INSERT": ("INSERT INTO app.monthly_usage (month) VALUES ('x')", "WRITE_NOT_ALLOWED"),
    "UPDATE": ("UPDATE app.monthly_usage SET month = 'x'", "WRITE_NOT_ALLOWED"),
    "DELETE": ("DELETE FROM app.monthly_usage", "WRITE_NOT_ALLOWED"),
    "MERGE": ("MERGE INTO app.monthly_usage t USING app.merchant_usage s ON true WHEN MATCHED THEN DELETE",
              "WRITE_NOT_ALLOWED"),
    "CREATE": ("CREATE TABLE app.t (a int)", "WRITE_NOT_ALLOWED"),
    "ALTER": ("ALTER VIEW app.monthly_usage RENAME TO x", "WRITE_NOT_ALLOWED"),
    "DROP": ("DROP VIEW app.monthly_usage", "WRITE_NOT_ALLOWED"),
    "TRUNCATE": ("TRUNCATE app.monthly_usage", "WRITE_NOT_ALLOWED"),
    "GRANT": ("GRANT SELECT ON app.monthly_usage TO someone", "WRITE_NOT_ALLOWED"),
    "REVOKE": ("REVOKE SELECT ON app.monthly_usage FROM someone", "WRITE_NOT_ALLOWED"),
    "COPY": ("COPY app.monthly_usage TO '/tmp/out'", "WRITE_NOT_ALLOWED"),
    "WITH 안의 DELETE": ("WITH d AS (DELETE FROM app.monthly_usage RETURNING *) SELECT * FROM d",
                         "WRITE_NOT_ALLOWED"),
    "여러 문장": ("SELECT month FROM app.monthly_usage; SELECT month FROM app.merchant_usage", "MULTIPLE_STATEMENTS"),
    "끝 세미콜론": ("SELECT month FROM app.monthly_usage;", "MULTIPLE_STATEMENTS"),
    "주석 --": ("SELECT month FROM app.monthly_usage -- 메모", "COMMENT_NOT_ALLOWED"),
    "주석 /* */": ("SELECT /* 메모 */ month FROM app.monthly_usage", "COMMENT_NOT_ALLOWED"),
    "FOR UPDATE": ("SELECT month FROM app.monthly_usage FOR UPDATE", "FOR_UPDATE_NOT_ALLOWED"),
    "FOR SHARE": ("SELECT month FROM app.monthly_usage FOR SHARE", "FOR_UPDATE_NOT_ALLOWED"),
    "SELECT INTO": ("SELECT month INTO new_table FROM app.monthly_usage", "SELECT_INTO_NOT_ALLOWED"),
    "set_config": ("SELECT set_config('app.member_id', 'M-1002', true)", "FORBIDDEN_FUNCTION"),
    "current_setting": ("SELECT current_setting('app.member_id') FROM app.monthly_usage", "FORBIDDEN_FUNCTION"),
    "pg_ 함수": ("SELECT pg_read_file('x') FROM app.monthly_usage", "FORBIDDEN_FUNCTION"),
    "generate_series": ("SELECT generate_series(1, 10)", "FORBIDDEN_FUNCTION"),
    "pg_sleep": ("SELECT pg_sleep(10)", "FORBIDDEN_FUNCTION"),
    "app_internal": ("SELECT member_id FROM app_internal.member_basic", "SCHEMA_NOT_ALLOWED"),
    "public": ("SELECT key FROM public.lab_metadata", "SCHEMA_NOT_ALLOWED"),
    "pg_catalog": ("SELECT relname FROM pg_catalog.pg_class", "SCHEMA_NOT_ALLOWED"),
    "information_schema": ("SELECT table_name FROM information_schema.tables", "SCHEMA_NOT_ALLOWED"),
    "스키마 없는 표": ("SELECT month FROM monthly_usage", "VIEW_NOT_ALLOWED"),
    "없는 app 뷰": ("SELECT a FROM app.secret_view", "VIEW_NOT_ALLOWED"),
    "뷰에 없는 컬럼": ("SELECT card_id FROM app.monthly_usage", "COLUMN_NOT_ALLOWED"),
    "다른 뷰 컬럼": ("SELECT u.category FROM app.monthly_usage u", "COLUMN_NOT_ALLOWED"),
    "허용 밖 함수": ("SELECT lower(category) FROM app.merchant_usage", "FUNCTION_NOT_ALLOWED"),
    "UNION": ("SELECT month FROM app.monthly_usage UNION SELECT month FROM app.merchant_usage", "NOT_SELECT"),
    "창 함수(OVER)": ("SELECT row_number() OVER (ORDER BY month) FROM app.monthly_usage", "SYNTAX_NOT_ALLOWED"),
    "문법 오류": ("SELEC month FROM", "PARSE_ERROR"),
    "빈 SQL": ("   ", "EMPTY_SQL"),
}


@pytest.mark.parametrize("label", sorted(FORBIDDEN_EXAMPLES))
def test_forbidden_examples(label):
    sql, reason = FORBIDDEN_EXAMPLES[label]
    result = validator.validate(sql)
    assert not result.ok, label
    assert result.reason == reason, label
    assert result.sql is None


def test_semicolon_inside_string_literal_is_not_a_statement_separator():
    """문자열 값 안의 ;와 --는 토큰이 아니므로 통과함(문자열 비교가 아니라 문법 트리 검사)."""
    assert validator.validate("SELECT month FROM app.monthly_usage WHERE month = 'a;--b'").ok


def test_catalog_has_twelve_views():
    """기본 7개와 3조 추가 5개."""
    assert len(ALLOWED_VIEWS) == 12
    assert all(name.startswith("app.") for name in ALLOWED_VIEWS)


def test_vip_views_can_be_queried_with_their_own_columns():
    sql = "SELECT month, change_rate_pct FROM app.vip_monthly_trend WHERE is_partial_month = false ORDER BY month"
    assert validator.validate(sql).ok
    join = (
        "SELECT c.category, c.share_pct, s.change_rate_pct FROM app.vip_category_share c "
        "CROSS JOIN app.vip_churn_signal_summary s WHERE c.amount_rank = 1"
    )
    assert validator.validate(join).ok


def test_vip_view_rejects_columns_of_other_views():
    result = validator.validate("SELECT card_ref FROM app.vip_category_share")
    assert not result.ok
    assert result.reason == "COLUMN_NOT_ALLOWED"
