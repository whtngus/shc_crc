"""S-R3 계획 적합성 판정: FIT, UNFIT(사유 코드), UNANSWERABLE, 재시도 소진, 예산 착지."""

import pytest

from app.application.models import RetrieverError
from app.domain.fixed_queries import FIXED_QUERIES
from conftest import FakeClock, after_r1, make_plan, make_steps


def judge(plan, attempt=1, clock=None, **state):
    return make_steps(clock=clock).step_r3(after_r1(plan=plan, plan_source="LLM", attempt=attempt, **state))


def test_fixed_plan_uses_registered_sql():
    out = judge(make_plan("FIXED", query_id="FQ-05"))
    assert out["verdict"] == "FIT"
    assert out["candidate_sql"] == FIXED_QUERIES["FQ-05"].sql
    assert out["sql_source"] == "FIXED"
    assert out["query_id"] == "FQ-05"


def test_nl2sql_plan_is_fit():
    out = judge(make_plan("NL2SQL"))
    assert out["verdict"] == "FIT"
    assert out["sql_source"] == "NL2SQL"
    assert out["query_id"] is None


def test_unanswerable_route_keeps_reason():
    out = judge(make_plan("UNANSWERABLE", reason="포인트 정보는 공개 뷰에 없음"))
    assert out["verdict"] == "UNANSWERABLE"
    assert out["unanswerable_reason"] == "포인트 정보는 공개 뷰에 없음"


@pytest.mark.parametrize(
    ("plan", "reason"),
    [
        (make_plan("FIXED", query_id="FQ-99"), "UNKNOWN_QUERY_ID"),
        (make_plan("NL2SQL", target_views=["app_internal.member_basic"]), "VIEW_NOT_ALLOWED"),
        (make_plan("NL2SQL", target_views=[]), "VIEW_NOT_ALLOWED"),
        (make_plan("NL2SQL", sql=""), "EMPTY_SQL"),
        (make_plan("OTHER"), "INVALID_ROUTE"),
        ({"route": "FIXED"}, "PLAN_FIELD_MISSING"),
        (None, "PLAN_FIELD_MISSING"),
        (make_plan("FIXED", requested_period={"from": "7월", "to": None}), "INVALID_PERIOD"),
    ],
)
def test_unfit_with_reason_code_on_first_attempt(plan, reason):
    out = judge(plan, attempt=1)
    assert out["verdict"] == "UNFIT"
    assert out["retry_reason"] == reason


def test_unfit_on_second_attempt_becomes_unanswerable():
    out = judge(make_plan("FIXED", query_id="FQ-99"), attempt=2)
    assert out["verdict"] == "UNANSWERABLE"
    assert out["unanswerable_reason"]


def test_out_of_period_is_unanswerable_without_retry():
    plan = make_plan(
        "NL2SQL", requested_period={"from": "2025-12-01", "to": "2025-12-31"}
    )  # 월 집계 6개월(2026-03 ~ 2026-08) 밖
    out = judge(plan, attempt=1)
    assert out["verdict"] == "UNANSWERABLE"
    assert out["unanswerable_reason"] == "데이터 제공 기간 밖"


def test_period_inside_window_is_fit():
    plan = make_plan("NL2SQL", requested_period={"from": "2026-07-01", "to": "2026-07-31"})
    assert judge(plan)["verdict"] == "FIT"


def test_budget_landing_disables_retry():
    """28장: S-R3 기준 미달 → 재시도를 끄고 차감값 0초로 다시 계산 → 시작."""
    clock = FakeClock()
    clock.set_elapsed(9.0)  # 차감 5초: 15 - 9 - 1 - 5 = 0 < 0.75 / 차감 0초: 5 ≥ 0.75
    out = judge(make_plan("FIXED", query_id="FQ-99"), attempt=1, clock=clock)
    assert out["retry_disabled"] is True
    assert out["verdict"] == "UNANSWERABLE"  # 재시도를 껐으므로 부적합이어도 되돌아가지 않음


def test_budget_exhausted_even_without_deduction():
    clock = FakeClock()
    clock.set_elapsed(13.5)  # 15 - 13.5 - 1 = 0.5 < 0.75
    with pytest.raises(RetrieverError) as caught:
        judge(make_plan(), attempt=1, clock=clock)
    assert caught.value.code == "TIME_BUDGET_EXCEEDED"
