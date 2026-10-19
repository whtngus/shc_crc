-- VIP 고객 이탈 방지(3조 고객군) 전용 논리 읽기 모델 5개를 추가함.
-- 기존 뷰(04 ~ 06)는 고치지 않고, 이탈 신호를 한 번에 볼 수 있는 뷰만 더함.
-- 신규 DB 초기화 때 06_history_daily_usage.sql 다음에 실행하며, 기존 DB에도 재실행 가능함(CREATE OR REPLACE).
--
-- 지킨 규칙(04 ~ 06과 같음)
--   - 회원 격리는 RLS가 맡음. 이 파일의 뷰는 회원 조건을 쓰지 않음.
--   - 세션 변수(app.member_id, app.base_date, app.coverage_start)를 지정하지 않으면 0행(기본 거부).
--   - 뷰 소유자는 app_reader이고, 서비스 계정 sql_retriever_user는 뷰 조회 권한만 받음.
--   - 개별 거래 행, 원본 카드ID, 가맹점ID는 노출하지 않음(card_ref, 가맹점명, 업종만 노출).
--
-- 이탈 신호의 기준(설계 가정, 개발 후 상담 현장 기준으로 확인할 값)
--   - 월 사용액 추이: 최근 6개월 월별 승인 사용액의 전월 대비 증감. 기준일이 속한 달은 월말 전이면 "부분 월"로 표시함.
--   - 연회비 부담: 월평균 사용액을 12개월로 늘린 값을 연회비로 나눈 배수. 1배 미만이면 연회비보다 적게 쓰는 카드임.
--   - 최근 활동: 마지막 승인일과 최근 30일, 그 이전 30일의 승인 건수와 금액 비교.
--   - 주 사용 업종: 최근 6개월 업종별 사용액 비중과 순위.
--   - 종합 신호: 최근 3개월 월평균 사용액을 그 이전 달들의 월평균과 비교(부분 월은 제외).

-- ---------------------------------------------------------------------------
-- 1. 월 사용액 추이 — 모든 카드를 합친 월별 사용액과 전월 대비 증감
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW app.vip_monthly_trend WITH (security_barrier = true) AS
WITH monthly AS (
    SELECT
        mu.month,
        sum(mu.approved_amount)::bigint    AS approved_amount,
        sum(mu.transaction_count)::integer AS transaction_count
    FROM app.monthly_usage AS mu
    GROUP BY mu.month
),
with_prev AS (
    SELECT
        monthly.month,
        monthly.approved_amount,
        monthly.transaction_count,
        lag(monthly.approved_amount) OVER (ORDER BY monthly.month) AS prev_month_amount
    FROM monthly
)
SELECT
    w.month,
    w.approved_amount,
    w.transaction_count,
    w.prev_month_amount,
    (w.approved_amount - w.prev_month_amount)::bigint AS change_amount,
    CASE
        WHEN w.prev_month_amount > 0
        THEN round(100.0 * (w.approved_amount - w.prev_month_amount) / w.prev_month_amount, 1)
    END AS change_rate_pct,
    (
        w.month = to_char(scope.base_date, 'YYYY-MM')
        AND scope.base_date < (date_trunc('month', scope.base_date) + INTERVAL '1 month - 1 day')::date
    ) AS is_partial_month
FROM with_prev AS w
CROSS JOIN app_internal.request_scope AS scope;

ALTER VIEW app.vip_monthly_trend OWNER TO app_reader;
COMMENT ON VIEW app.vip_monthly_trend IS
    '최근 6개월 월별 승인 사용액(모든 카드 합계)과 전월 대비 증감. 기준일이 속한 달이 월말 전이면 is_partial_month가 true임.';
GRANT SELECT ON app.vip_monthly_trend TO sql_retriever_user;

-- ---------------------------------------------------------------------------
-- 2. 연회비 부담 — 카드별 연회비와 연 환산 사용액의 비교
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW app.vip_annual_fee_burden WITH (security_barrier = true) AS
SELECT
    cards.card_ref,
    cards.product_name,
    cards.annual_fee,
    coalesce(card_usage.recent_amount, 0)::bigint AS recent_period_amount,
    coalesce(card_usage.month_count, 0)::integer  AS usage_month_count,
    CASE
        WHEN coalesce(card_usage.month_count, 0) > 0
        THEN round(card_usage.recent_amount / card_usage.month_count, 0)::bigint
    END AS avg_monthly_amount,
    CASE
        WHEN coalesce(card_usage.month_count, 0) > 0 AND cards.annual_fee > 0
        THEN round((card_usage.recent_amount / card_usage.month_count) * 12 / cards.annual_fee, 1)
    END AS yearly_usage_to_fee_ratio
FROM app.customer_cards AS cards
LEFT JOIN (
    SELECT
        monthly.card_ref,
        sum(monthly.approved_amount) AS recent_amount,
        count(*)                     AS month_count
    FROM app.monthly_usage AS monthly
    GROUP BY monthly.card_ref
) AS card_usage
  ON card_usage.card_ref = cards.card_ref;

ALTER VIEW app.vip_annual_fee_burden OWNER TO app_reader;
COMMENT ON VIEW app.vip_annual_fee_burden IS
    '카드별 연회비와 최근 6개월 사용액. yearly_usage_to_fee_ratio는 월평균 사용액을 12배 한 값을 연회비로 나눈 배수이며 연회비가 0이면 NULL임.';
GRANT SELECT ON app.vip_annual_fee_burden TO sql_retriever_user;

-- ---------------------------------------------------------------------------
-- 3. 최근 활동 신호 — 마지막 승인일, 최근 30일과 그 이전 30일 비교(고객 1행)
-- ---------------------------------------------------------------------------
-- 거래가 한 건도 없어도 1행이 나오도록 카드와 거래를 LEFT JOIN으로 이음.
-- count(txn.txn_id)로 세므로 거래가 없는 경우 0이 됨(count(*)는 NULL 행을 1로 세므로 쓰지 않음).
CREATE OR REPLACE VIEW app.vip_activity_signal WITH (security_barrier = true) AS
SELECT
    max(txn.txn_date) AS last_approved_date,
    (scope.base_date - max(txn.txn_date))::integer AS days_since_last_approved,
    count(txn.txn_id) FILTER (
        WHERE txn.txn_date > scope.base_date - 30
    )::integer AS approved_count_last_30d,
    count(txn.txn_id) FILTER (
        WHERE txn.txn_date <= scope.base_date - 30 AND txn.txn_date > scope.base_date - 60
    )::integer AS approved_count_prev_30d,
    coalesce(sum(txn.amount) FILTER (
        WHERE txn.txn_date > scope.base_date - 30
    ), 0)::bigint AS approved_amount_last_30d,
    coalesce(sum(txn.amount) FILTER (
        WHERE txn.txn_date <= scope.base_date - 30 AND txn.txn_date > scope.base_date - 60
    ), 0)::bigint AS approved_amount_prev_30d
FROM app_internal.request_scope AS scope
JOIN app_internal.member_basic AS member_scope
  ON member_scope.join_date <= scope.base_date
LEFT JOIN app_internal.customer_cards_full AS cards
  ON true
LEFT JOIN public.card_txn AS txn
  ON txn.card_id = cards.card_id
 AND txn.approval_code = 'APPROVED'
 AND txn.txn_date >= scope.coverage_start
 AND txn.txn_date <= scope.base_date
GROUP BY scope.base_date;

ALTER VIEW app.vip_activity_signal OWNER TO app_reader;
COMMENT ON VIEW app.vip_activity_signal IS
    '마지막 승인일과 경과일, 최근 30일과 그 이전 30일의 승인 건수와 금액(고객 1행). 거래가 없으면 건수와 금액은 0이고 마지막 승인일은 NULL임.';
GRANT SELECT ON app.vip_activity_signal TO sql_retriever_user;

-- ---------------------------------------------------------------------------
-- 4. 주 사용 업종 — 업종별 사용액 비중과 순위
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW app.vip_category_share WITH (security_barrier = true) AS
WITH by_category AS (
    SELECT
        merchant.category,
        sum(merchant.approved_amount)::bigint    AS approved_amount,
        sum(merchant.transaction_count)::integer AS transaction_count
    FROM app.merchant_usage AS merchant
    GROUP BY merchant.category
)
SELECT
    by_category.category,
    by_category.approved_amount,
    by_category.transaction_count,
    round(100.0 * by_category.approved_amount / nullif(sum(by_category.approved_amount) OVER (), 0), 1) AS share_pct,
    (rank() OVER (ORDER BY by_category.approved_amount DESC))::integer AS amount_rank
FROM by_category;

ALTER VIEW app.vip_category_share OWNER TO app_reader;
COMMENT ON VIEW app.vip_category_share IS
    '최근 6개월 업종별 승인 사용액과 건수, 전체 대비 비중(%)과 사용액 순위. 순위 1이 주 사용 업종임.';
GRANT SELECT ON app.vip_category_share TO sql_retriever_user;

-- ---------------------------------------------------------------------------
-- 5. 이탈 신호 종합 — 최근 3개월 사용액 변화와 최근 활동을 고객 1행으로 요약
-- ---------------------------------------------------------------------------
-- 기준일이 속한 달이 부분 월이면 비교에서 뺌. 그래서 비교 가능한 이전 달 수(prev_month_count)가 1 ~ 3으로 달라지며,
-- 0이면 change_rate_pct는 NULL임. 이 값은 "6개월 안에서 가능한 비교"이므로 장기 추세로 읽지 않음.
CREATE OR REPLACE VIEW app.vip_churn_signal_summary WITH (security_barrier = true) AS
WITH full_months AS (
    SELECT
        trend.month,
        trend.approved_amount,
        row_number() OVER (ORDER BY trend.month DESC) AS recency_rank
    FROM app.vip_monthly_trend AS trend
    WHERE NOT trend.is_partial_month
),
agg AS (
    SELECT
        avg(full_months.approved_amount) FILTER (WHERE full_months.recency_rank <= 3)                AS recent_avg,
        count(full_months.month)         FILTER (WHERE full_months.recency_rank <= 3)                AS recent_month_count,
        avg(full_months.approved_amount) FILTER (WHERE full_months.recency_rank BETWEEN 4 AND 6)     AS prev_avg,
        count(full_months.month)         FILTER (WHERE full_months.recency_rank BETWEEN 4 AND 6)     AS prev_month_count
    FROM full_months
)
SELECT
    round(agg.recent_avg, 0)::bigint  AS recent_3m_avg_amount,
    round(agg.prev_avg, 0)::bigint    AS prev_avg_amount,
    agg.recent_month_count::integer   AS recent_month_count,
    agg.prev_month_count::integer     AS prev_month_count,
    CASE
        WHEN agg.prev_avg > 0 AND agg.prev_month_count > 0
        THEN round(100.0 * (agg.recent_avg - agg.prev_avg) / agg.prev_avg, 1)
    END AS change_rate_pct,
    activity.days_since_last_approved,
    activity.approved_count_last_30d,
    activity.approved_count_prev_30d
FROM agg
CROSS JOIN app.vip_activity_signal AS activity;

ALTER VIEW app.vip_churn_signal_summary OWNER TO app_reader;
COMMENT ON VIEW app.vip_churn_signal_summary IS
    '이탈 신호 종합(고객 1행). 최근 3개월 월평균 사용액과 그 이전 달들의 월평균 비교(부분 월 제외), 마지막 승인 경과일, 최근 30일과 이전 30일 승인 건수.';
GRANT SELECT ON app.vip_churn_signal_summary TO sql_retriever_user;
