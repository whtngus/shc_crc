"""S-R2 정형쿼리 또는 NL2SQL 판단: LLM 정상, 대체 경로, 거절, 오류 종료(가짜 LLM)."""

import pytest

from app.application.models import PlanOutcome, PlannerFailure, RetrieverError
from conftest import FakeClock, FakePlanner, after_r1, make_plan, make_steps


def test_llm_plan_and_attempt_increment():
    planner = FakePlanner(PlanOutcome(plan=make_plan("NL2SQL")))
    out = make_steps(planner=planner).step_r2(after_r1())
    assert out["plan_source"] == "LLM"
    assert out["plan"]["route"] == "NL2SQL"
    assert out["attempt"] == 1


def test_user_prompt_inputs_have_no_member_id():
    planner = FakePlanner(PlanOutcome(plan=make_plan()))
    make_steps(planner=planner).step_r2(after_r1(retry_reason="VIEW_NOT_ALLOWED", previous_sql="SELECT 1", attempt=1))
    request = planner.calls[0]
    assert request.attempt == 2
    assert request.retry_reason == "VIEW_NOT_ALLOWED"
    assert request.previous_sql == "SELECT 1"
    assert "M-1001" not in repr(request)


@pytest.mark.parametrize("kind", ["TIMEOUT", "CONNECTION", "RATE_LIMIT", "SERVER_ERROR", "BAD_REQUEST", "OTHER"])
def test_llm_failure_falls_back_to_keyword_rule(kind):
    planner = FakePlanner(PlannerFailure(kind, retry_after="3" if kind == "RATE_LIMIT" else None))
    out = make_steps(planner=planner).step_r2(after_r1(masked_question="연체 이력 보여 줘"))
    assert out["plan_source"] == "KEYWORD_RULE"
    assert out["plan"]["route"] == "FIXED"
    assert out["plan"]["query_id"] == "FQ-06"
    assert out["attempt"] == 1


def test_llm_failure_without_keyword_match_is_llm_unavailable():
    planner = FakePlanner(PlannerFailure("TIMEOUT"))
    with pytest.raises(RetrieverError) as caught:
        make_steps(planner=planner).step_r2(after_r1(masked_question="포인트 잔액 알려 줘"))
    assert caught.value.code == "LLM_UNAVAILABLE"
    assert caught.value.spec.http_status == 503


def test_refusal_becomes_unanswerable_plan():
    planner = FakePlanner(PlanOutcome(refusal="I can't help with that"))
    out = make_steps(planner=planner).step_r2(after_r1())
    assert out["plan"]["route"] == "UNANSWERABLE"
    assert out["plan_source"] == "LLM"


def test_budget_shortage_skips_llm_and_uses_keyword_rule():
    """28장 예 3: 기존 사용 9.6초 → 남은 시간 예산 -0.6초 → LLM을 부르지 않고 키워드 규칙."""
    clock = FakeClock()
    clock.set_elapsed(9.6)
    planner = FakePlanner()
    out = make_steps(planner=planner, clock=clock).step_r2(after_r1(attempt=1, masked_question="보유 카드"))
    assert planner.calls == []
    assert out["plan_source"] == "KEYWORD_RULE"
    assert out["attempt"] == 2


def test_budget_shortage_without_keyword_match_is_time_budget_exceeded():
    """사용자 결정(2026-10-15): 예산 부족 + 키워드 규칙 없음 → TIME_BUDGET_EXCEEDED(504)."""
    clock = FakeClock()
    clock.set_elapsed(9.6)
    with pytest.raises(RetrieverError) as caught:
        make_steps(planner=FakePlanner(), clock=clock).step_r2(after_r1(masked_question="포인트 잔액"))
    assert caught.value.code == "TIME_BUDGET_EXCEEDED"


def test_budget_example_2_still_calls_llm():
    """28장 예 2: 기존 사용 6.2초 → 남은 시간 예산 2.8초 → 시작."""
    clock = FakeClock()
    clock.set_elapsed(6.2)
    planner = FakePlanner(PlanOutcome(plan=make_plan()))
    make_steps(planner=planner, clock=clock).step_r2(after_r1(attempt=1))
    assert len(planner.calls) == 1
