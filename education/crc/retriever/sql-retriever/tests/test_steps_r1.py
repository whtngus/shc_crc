"""S-R1 검색 요청 접수와 검증: 정상 경로와 오류 종료 경로(가짜 DB)."""

from datetime import date

import pytest

from app.application.models import DatabaseFailure, DatabaseTimeout, RetrieverError
from conftest import COVERAGE_START, DATA_BASE_DATE, T0, FakeClock, FakeRepository, make_steps, trigger


def test_normal_output_fields():
    repository = FakeRepository()
    out = make_steps(repository=repository).step_r1(trigger(question="M-1002 회원 010-1234-5678 카드 목록"))
    assert out["masked_question"] == "[가림] 회원 [가림] 카드 목록"
    assert out["masked_count"] == 2
    assert out["base_date"] == DATA_BASE_DATE
    assert out["coverage_start"] == COVERAGE_START
    assert out["started_at"] == T0
    assert out["attempt"] == 0
    assert out["member_id"] == "M-1001"
    # 문장 실행 제한 시간 = 남은 시간 예산 이하: 15 - 0 - 1 - 5 = 9초
    _, _, _, timeout_ms = repository.calls[0]
    assert timeout_ms == 9000


def test_requested_base_date_is_used():
    out = make_steps().step_r1(trigger(base_date="2026-07-31"))
    assert out["base_date"] == date(2026, 7, 31)


@pytest.mark.parametrize(
    "overrides",
    [
        {"request_id": ""},
        {"question": ""},
        {"question": "가" * 501},
        {"member_id": "1001"},
        {"member_id": None},
        {"base_date": "2026/08/31"},
        {"base_date": "2026-09-01"},  # 데이터 기준일보다 뒤
    ],
)
def test_invalid_request(overrides):
    with pytest.raises(RetrieverError) as caught:
        make_steps().step_r1(trigger(**overrides))
    assert caught.value.code == "INVALID_REQUEST"
    assert caught.value.spec.http_status == 400


@pytest.mark.parametrize("join_date", [None, date(2026, 9, 1)])
def test_member_not_found(join_date):
    """회원 없음 또는 기준일에 아직 가입 전 → MEMBER_NOT_FOUND(404)."""
    with pytest.raises(RetrieverError) as caught:
        make_steps(repository=FakeRepository(join_date=join_date)).step_r1(trigger())
    assert caught.value.code == "MEMBER_NOT_FOUND"
    assert caught.value.spec.http_status == 404


@pytest.mark.parametrize("error", [DatabaseFailure("x"), DatabaseTimeout("x")])
def test_db_error(error):
    with pytest.raises(RetrieverError) as caught:
        make_steps(repository=FakeRepository(member_error=error)).step_r1(trigger())
    assert caught.value.code == "DB_ERROR"
    assert caught.value.spec.http_status == 500


def test_invalid_request_does_not_touch_db():
    repository = FakeRepository()
    with pytest.raises(RetrieverError):
        make_steps(repository=repository).step_r1(trigger(member_id="bad"))
    assert repository.calls == []


def test_time_budget_exceeded_before_start(monkeypatch):
    """시작 직후라 실제로는 거의 없지만, 기준 미달이면 TIME_BUDGET_EXCEEDED(504)."""
    from app.domain import time_budget as tb

    monkeypatch.setattr(tb, "TOTAL_BUDGET_SECONDS", 6.5)  # 6.5 - 0 - 1 - 5 = 0.5 < 0.75
    with pytest.raises(RetrieverError) as caught:
        make_steps(clock=FakeClock()).step_r1(trigger())
    assert caught.value.code == "TIME_BUDGET_EXCEEDED"
    assert caught.value.spec.http_status == 504
