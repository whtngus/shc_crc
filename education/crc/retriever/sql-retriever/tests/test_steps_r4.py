"""S-R4 SQL 검증: 통과, L-1 되돌림, 재시도 소진, 정형쿼리 실패, 오류 문구에 SQL 없음."""

import logging

import pytest

from app.application.models import ERROR_CATALOG, RetrieverError
from conftest import FakeClock, after_r1, make_steps

BAD_SQL = "SELECT member_id FROM app_internal.member_basic"


def validate(candidate_sql, sql_source="NL2SQL", attempt=1, clock=None, **state):
    return make_steps(clock=clock).step_r4(
        after_r1(candidate_sql=candidate_sql, sql_source=sql_source, attempt=attempt, query_id=None, **state)
    )


def test_pass_sets_limit():
    out = validate("SELECT month FROM app.monthly_usage")
    assert out["validated_sql"].endswith("LIMIT 200")
    assert out["row_limit"] == 200
    assert out["retry_reason"] is None


def test_failure_on_first_attempt_returns_to_r2():
    out = validate(BAD_SQL, attempt=1)
    assert out["validated_sql"] is None
    assert out["retry_reason"] == "SCHEMA_NOT_ALLOWED"
    assert out["previous_sql"] == BAD_SQL


def test_failure_on_second_attempt_is_error():
    with pytest.raises(RetrieverError) as caught:
        validate(BAD_SQL, attempt=2)
    assert caught.value.code == "SQL_VALIDATION_FAILED"
    assert caught.value.spec.http_status == 422


def test_fixed_query_failure_is_error_with_ops_alert(caplog):
    with caplog.at_level(logging.WARNING, logger="sql_retriever.ops"):
        with pytest.raises(RetrieverError) as caught:
            validate(BAD_SQL, sql_source="FIXED", attempt=1)
    assert caught.value.code == "SQL_VALIDATION_FAILED"
    assert any("fixed query failed" in record.message for record in caplog.records)


def test_error_message_has_no_sql_or_names():
    message = ERROR_CATALOG["SQL_VALIDATION_FAILED"].message
    assert message == "질문을 처리할 데이터 조회 문장을 만들지 못했습니다. 질문을 바꿔 다시 요청해 주세요."
    for leaked in ("SELECT", "app.", "member_id", "app_internal"):
        assert leaked not in message


def test_budget_landing_turns_retry_into_error():
    """재시도를 끈 상태(예산 착지)에서 검증 실패면 되돌아가지 않고 오류 종료."""
    clock = FakeClock()
    clock.set_elapsed(9.0)
    with pytest.raises(RetrieverError) as caught:
        validate(BAD_SQL, attempt=1, clock=clock)
    assert caught.value.code == "SQL_VALIDATION_FAILED"
