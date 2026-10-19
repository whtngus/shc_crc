"""S-R5 SQL 실행과 S-R6 응답 구성: 정상, 0행, 상한 도달, 오류 종료, 감사 로그(가짜 DB)."""

import pytest

from app.application.models import DatabaseFailure, DatabaseTimeout, RetrieverError, SearchResponse
from app.application.steps import hash_member_id
from conftest import FakeAuditLog, FakeClock, FakeRepository, after_r1, make_steps

VALIDATED = "SELECT card_ref FROM app.customer_cards LIMIT 200"


def r5_state(**overrides):
    return after_r1(validated_sql=VALIDATED, row_limit=200, attempt=1, **overrides)


# ---------------------------------------------------------------- S-R5
def test_r5_passes_session_scope_and_timeout():
    """28장 예 4: 기존 사용 11.3초 → statement_timeout 2,700ms 이하."""
    clock = FakeClock()
    clock.set_elapsed(11.3)
    repository = FakeRepository()
    out = make_steps(repository=repository, clock=clock).step_r5(r5_state())
    _, sql, kwargs = repository.calls[0]
    assert sql == VALIDATED
    assert kwargs["member_id"] == "M-1001"
    assert 2699 <= kwargs["timeout_ms"] <= 2700
    assert kwargs["row_limit"] == 200
    assert out["row_count"] == 1
    assert out["truncated"] is False


def test_r5_zero_rows_is_not_error():
    out = make_steps(repository=FakeRepository(rows=[])).step_r5(r5_state())
    assert out["row_count"] == 0
    assert out["rows"] == []


def test_r5_truncated_at_200():
    rows = [{"card_ref": f"CARD_{i:03d}"} for i in range(250)]
    out = make_steps(repository=FakeRepository(rows=rows)).step_r5(r5_state())
    assert out["row_count"] == 200
    assert out["truncated"] is True


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [(DatabaseTimeout("x"), "DB_TIMEOUT", 504), (DatabaseFailure("x"), "DB_ERROR", 500)],
)
def test_r5_db_errors(error, code, status):
    with pytest.raises(RetrieverError) as caught:
        make_steps(repository=FakeRepository(execute_error=error)).step_r5(r5_state())
    assert caught.value.code == code
    assert caught.value.spec.http_status == status


def test_r5_time_budget_exceeded():
    clock = FakeClock()
    clock.set_elapsed(13.5)
    repository = FakeRepository()
    with pytest.raises(RetrieverError) as caught:
        make_steps(repository=repository, clock=clock).step_r5(r5_state())
    assert caught.value.code == "TIME_BUDGET_EXCEEDED"
    assert repository.calls == []


# ---------------------------------------------------------------- S-R6
def ok_state(**overrides):
    state = r5_state(
        plan_source="LLM", verdict="FIT", sql_source="FIXED", query_id="FQ-02",
        columns=[{"name": "card_ref", "type": "text"}], rows=[{"card_ref": "CARD_001"}],
        row_count=1, truncated=False, db_elapsed_ms=3,
    )
    state.update(overrides)
    return state


def test_r6_ok_response_has_13_fields_and_no_sql():
    clock = FakeClock()
    clock.set_elapsed(1.234)
    audit = FakeAuditLog()
    response = make_steps(audit=audit, clock=clock).step_r6(ok_state())["response"]
    assert set(response) == set(SearchResponse.model_fields)
    assert len(response) == 13
    assert response["status"] == "OK"
    assert response["route"] == "FIXED"
    assert response["message"] == "기준일 2026-08-31 기준 1건"
    assert response["elapsed_ms"] == 1234
    text = repr(response)
    assert "SELECT" not in text and "M-1001" not in text and "app.customer_cards" not in text
    record = audit.records[0]
    assert record.member_hash == hash_member_id("M-1001")
    assert record.masked_question == "보유 카드 목록 보여 주세요"
    assert record.attempt == 1


def test_r6_unanswerable_response():
    state = ok_state(verdict="UNANSWERABLE", unanswerable_reason="데이터 제공 기간 밖", sql_source="NL2SQL", query_id=None)
    for key in ("columns", "rows", "row_count", "truncated", "db_elapsed_ms"):
        state.pop(key)
    response = make_steps().step_r6(state)["response"]
    assert response["status"] == "UNANSWERABLE"
    assert response["rows"] == [] and response["columns"] == []
    assert response["row_count"] == 0 and response["truncated"] is False
    assert response["message"] == "답할 수 없음: 데이터 제공 기간 밖"


def test_r6_runs_even_when_budget_is_gone():
    clock = FakeClock()
    clock.set_elapsed(14.9)
    assert make_steps(clock=clock).step_r6(ok_state())["response"]["status"] == "OK"


def test_r6_audit_failure_does_not_block_response(caplog):
    response = make_steps(audit=FakeAuditLog(fail=True)).step_r6(ok_state())["response"]
    assert response["status"] == "OK"
    assert any("audit log failed" in record.message for record in caplog.records)


def test_r6_build_failure_is_internal_error():
    state = ok_state()
    state.pop("plan_source")
    with pytest.raises(RetrieverError) as caught:
        make_steps().step_r6(state)
    assert caught.value.code == "INTERNAL_ERROR"
    assert caught.value.spec.http_status == 500
