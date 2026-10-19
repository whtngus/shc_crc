"""키워드 규칙(30장), 뷰 제공 기간(04 ~ 07 뷰 정의), 안내 문장 틀(19장)을 확인함."""

from datetime import date

import pytest

from app.domain.catalog import ALLOWED_VIEWS
from app.domain.fixed_queries import FIXED_QUERIES, match_keyword_rule
from app.domain.messages import result_message, unanswerable_message
from app.domain.periods import is_period_answerable, provision_window

BASE = date(2026, 8, 31)
COVERAGE = date(2025, 8, 1)


# ---------------------------------------------------------------- 키워드 규칙
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("가입일이 언제인가요", "FQ-01"),
        ("연령대 알려 주세요", "FQ-01"),
        ("보유 카드 보여 주세요", "FQ-02"),
        ("보유카드 몇 장", "FQ-02"),
        ("연회비 얼마예요", "FQ-02"),
        ("카드별 월 사용액", "FQ-03"),
        ("카드별 사용 내역", "FQ-03"),
        ("월별 합계", "FQ-04"),
        ("지난달 얼마 썼나요", "FQ-04"),
        ("이번 달 사용액", "FQ-04"),
        ("업종별로 보여 줘", "FQ-08"),
        ("어디서 많이 썼나요", "FQ-08"),
        ("연체 있나요", "FQ-05"),
        ("연체 이력 보여 줘", "FQ-06"),
        ("최근 12개월 연체", "FQ-06"),
        ("일별 사용액", "FQ-07"),
        ("최근 90일 사용", "FQ-07"),
        ("가맹점 상위 보여 줘", "FQ-09"),
        # 3조 추가(VIP 이탈 방지)
        ("전월 대비 사용액", "FQ-10"),
        ("월 사용액 추이", "FQ-10"),
        ("연회비 대비 얼마나 썼나요", "FQ-11"),
        ("연회비가 부담돼요", "FQ-11"),
        ("마지막으로 쓴 날이 언제예요", "FQ-12"),
        ("최근 활동 있나요", "FQ-12"),
        ("업종 비중 알려 줘", "FQ-13"),
        ("주로 쓰는 업종", "FQ-13"),
        ("이탈 징후 있나요", "FQ-14"),
        ("이탈 위험 신호", "FQ-14"),
        ("포인트 잔액", None),
    ],
)
def test_keyword_rule(question, expected):
    assert match_keyword_rule(question) == expected


def test_keyword_rule_uses_first_match():
    """위에서부터 차례로 맞춰 처음 맞는 1개를 씀: "보유 카드"(FQ-02)가 "카드별"(FQ-03)보다 먼저임."""
    assert match_keyword_rule("보유 카드별 월 사용") == "FQ-02"


def test_vip_rules_come_before_base_rules():
    """3조 규칙은 "연회비", "업종"처럼 기본 규칙과 겹치는 낱말을 쓰므로 기본 규칙보다 앞에 둠."""
    assert match_keyword_rule("연회비 얼마예요") == "FQ-02"
    assert match_keyword_rule("연회비 대비 사용액") == "FQ-11"
    assert match_keyword_rule("업종별로 보여 줘") == "FQ-08"
    assert match_keyword_rule("업종별 비중") == "FQ-13"


def test_fourteen_fixed_queries():
    """FQ-01 ~ FQ-09는 기본 예제, FQ-10 ~ FQ-14는 3조가 더함. 모두 허용 뷰만 읽어야 함."""
    assert sorted(FIXED_QUERIES) == [f"FQ-{i:02d}" for i in range(1, 15)]
    assert all(query.view in ALLOWED_VIEWS for query in FIXED_QUERIES.values())
    assert all(query.view in query.sql for query in FIXED_QUERIES.values())


# ---------------------------------------------------------------- 제공 기간
def test_windows_from_view_definitions():
    assert provision_window("app.monthly_usage", BASE, COVERAGE) == (date(2026, 3, 1), BASE)
    assert provision_window("app.merchant_usage", BASE, COVERAGE) == (date(2026, 3, 1), BASE)
    assert provision_window("app.customer_daily_usage", BASE, COVERAGE) == (date(2026, 6, 3), BASE)
    assert provision_window("app.customer_delinquency_history", BASE, COVERAGE) == (date(2025, 9, 1), BASE)
    assert provision_window("app.customer_profile", BASE, COVERAGE) is None


def test_vip_view_windows_follow_their_source_views():
    """3조 추가 뷰의 기간은 원천 뷰와 같거나(월 집계, 업종), 거래 제공 시작일부터 기준일까지임."""
    monthly = provision_window("app.monthly_usage", BASE, COVERAGE)
    for view in ("app.vip_monthly_trend", "app.vip_annual_fee_burden", "app.vip_churn_signal_summary"):
        assert provision_window(view, BASE, COVERAGE) == monthly, view
    assert provision_window("app.vip_category_share", BASE, COVERAGE) == provision_window(
        "app.merchant_usage", BASE, COVERAGE
    )
    assert provision_window("app.vip_activity_signal", BASE, COVERAGE) == (COVERAGE, BASE)


def test_delinquency_history_uses_previous_month_when_not_month_end():
    assert provision_window("app.customer_delinquency_history", date(2026, 8, 15), COVERAGE) == (
        date(2025, 8, 1),
        date(2026, 7, 31),
    )


def test_coverage_start_limits_monthly_window():
    assert provision_window("app.monthly_usage", BASE, date(2026, 5, 10)) == (date(2026, 5, 1), BASE)


@pytest.mark.parametrize(
    ("views", "period_from", "period_to", "expected"),
    [
        (["app.monthly_usage"], date(2026, 7, 1), date(2026, 7, 31), True),
        (["app.monthly_usage"], date(2025, 12, 1), date(2025, 12, 31), False),  # 6개월 밖
        (["app.customer_daily_usage"], date(2026, 5, 1), None, False),  # 90일 밖
        (["app.customer_daily_usage"], date(2026, 8, 1), None, True),
        (["app.customer_profile"], None, date(2026, 9, 30), False),  # 기준일 이후
        (["app.vip_monthly_trend"], date(2025, 12, 1), date(2025, 12, 31), False),  # 6개월 밖(3조 뷰)
        (["app.vip_activity_signal"], date(2026, 8, 1), None, True),  # 3조 뷰, 제공 시작일 이후
        (["app.customer_cards"], date(2020, 1, 1), None, True),  # 기간 제한 없는 뷰
        (["app.monthly_usage"], None, None, True),
    ],
)
def test_period_answerable(views, period_from, period_to, expected):
    assert is_period_answerable(views, period_from, period_to, BASE, COVERAGE) is expected


# ---------------------------------------------------------------- 안내 문장
def test_result_messages():
    assert result_message(BASE, 3, False) == "기준일 2026-08-31 기준 3건"
    assert result_message(BASE, 200, True) == "기준일 2026-08-31 기준 200건, 앞 200건만 보여 줌"
    assert result_message(BASE, 0, False) == "기준일 2026-08-31 기준 해당 데이터 없음"


def test_unanswerable_message_removes_internal_view_names():
    assert unanswerable_message("데이터 제공 기간 밖") == "답할 수 없음: 데이터 제공 기간 밖"
    assert unanswerable_message("포인트는 app.customer_cards 에 없음") == "답할 수 없음: 포인트는 에 없음"
    assert unanswerable_message(None) == "답할 수 없음"
