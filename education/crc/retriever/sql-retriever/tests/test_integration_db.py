"""통합 시험(실제 DB): NL2SQL 계정, 읽기 전용 트랜잭션, 정형쿼리 14개 1회씩, 회원 범위, 실행 제한 시간."""

from __future__ import annotations

import time
from datetime import date

import pytest

from app.application.models import DatabaseTimeout
from app.domain.catalog import ROW_LIMIT
from app.domain.fixed_queries import FIXED_QUERIES
from app.infrastructure.sql_validator import SqlglotValidator
from integration_support import make_repository, record

pytestmark = pytest.mark.integration

MEMBER = "M-5001"  # 합성 회원(다중 카드 4장, rdb/README.md)
BUDGET_MS = 9000


@pytest.fixture(scope="module")
def repository():
    repo = make_repository()
    yield repo
    repo.close()


@pytest.fixture(scope="module")
def context(repository):
    return repository.load_member_context(MEMBER, None, BUDGET_MS)


def test_connection_is_nl2sql_account_and_read_only(repository):
    """접속 계정이 sql_retriever_user(관리자 아님)이고 트랜잭션이 읽기 전용인지 확인함."""
    with repository._read_only(BUDGET_MS) as cursor:
        cursor.execute(
            "SELECT current_user, current_setting('transaction_read_only'), current_setting('statement_timeout'),"
            " (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
        )
        user, read_only, timeout, superuser = cursor.fetchone()
    assert user == "sql_retriever_user"
    assert read_only == "on"
    assert timeout == "9s"
    assert superuser is False
    record("db_session", user=user, read_only=read_only, statement_timeout=timeout, rolsuper=superuser)


def test_member_context(repository):
    started = time.perf_counter()
    ctx = repository.load_member_context(MEMBER, None, BUDGET_MS)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    assert ctx.data_base_date == date(2026, 8, 31)
    assert ctx.base_date == date(2026, 8, 31)
    assert ctx.coverage_start == date(2025, 8, 1)
    assert ctx.join_date is not None and ctx.join_date <= ctx.base_date
    record("member_check", member="M-5001(합성)", elapsed_ms=elapsed_ms)


def test_unknown_member_has_no_join_date(repository):
    assert repository.load_member_context("M-9999", None, BUDGET_MS).join_date is None


def test_requested_base_date_is_kept(repository):
    assert repository.load_member_context(MEMBER, date(2026, 7, 31), BUDGET_MS).base_date == date(2026, 7, 31)


@pytest.mark.parametrize("query_id", sorted(FIXED_QUERIES))
def test_every_fixed_query_runs_once(repository, context, query_id):
    """정형쿼리 14개를 모두 실제 DB에서 1회씩 실행함(검증 통과 SQL만 실행). FQ-10 ~ FQ-14는 3조 추가분임."""
    validation = SqlglotValidator().validate(FIXED_QUERIES[query_id].sql)
    assert validation.ok
    started = time.perf_counter()
    result = repository.execute(
        validation.sql, member_id=MEMBER, base_date=context.base_date, coverage_start=context.coverage_start,
        timeout_ms=BUDGET_MS, row_limit=ROW_LIMIT,
    )
    total_ms = int((time.perf_counter() - started) * 1000)
    assert len(result.rows) <= ROW_LIMIT
    assert result.columns
    record("fixed_query", query_id=query_id, rows=len(result.rows), db_elapsed_ms=result.db_elapsed_ms,
           total_ms=total_ms)


def test_rls_scopes_rows_to_session_member(repository, context):
    """세션 변수 app.member_id에 따라 다른 회원의 카드만 보임(행 수준 보안)."""
    sql = SqlglotValidator().validate(FIXED_QUERIES["FQ-02"].sql).sql
    counts = {}
    for member in ("M-1001", "M-5001"):
        counts[member] = len(repository.execute(
            sql, member_id=member, base_date=context.base_date, coverage_start=context.coverage_start,
            timeout_ms=BUDGET_MS, row_limit=ROW_LIMIT,
        ).rows)
    assert counts == {"M-1001": 1, "M-5001": 4}  # rdb/README.md 합성 회원 보유카드 수


def test_statement_timeout_raises_database_timeout(repository, context):
    """실행 제한 시간을 1ms로 두면 FQ-07(실행 비용 큼)이 시간 초과로 끊김 → DatabaseTimeout(→ DB_TIMEOUT)."""
    sql = SqlglotValidator().validate(FIXED_QUERIES["FQ-07"].sql).sql
    with pytest.raises(DatabaseTimeout):
        repository.execute(
            sql, member_id=MEMBER, base_date=context.base_date, coverage_start=context.coverage_start,
            timeout_ms=1, row_limit=ROW_LIMIT,
        )
    # 시간 초과 뒤에도 풀의 접속이 정상으로 돌아오는지 확인함
    assert repository.load_member_context(MEMBER, None, BUDGET_MS).join_date is not None


def test_forbidden_sql_from_planner_never_reaches_db(repository, tmp_path):
    """LLM 자리에 금지 SQL을 두 번 내는 가짜를 넣고 실제 DB로 흐름 전체를 돌림.

    S-R4가 두 번 모두 막아 SQL_VALIDATION_FAILED(422)로 끝나고, DB에는 그 SQL이 한 번도 가지 않아야 함.
    """
    from app.application.models import PlanOutcome
    from app.application.services import SqlRetrieverService
    from app.application.steps import WorkflowSteps
    from app.bootstrap import utc_now
    from app.infrastructure.audit_log import JsonlAuditLog
    from app.infrastructure.graph import LangGraphRunner

    forbidden = {
        "route": "NL2SQL", "query_id": None, "sql": "SELECT member_id, join_date FROM app_internal.member_basic",
        "target_views": ["app.customer_profile"], "requested_period": {"from": None, "to": None}, "reason": "시험",
    }

    class ForbiddenPlanner:
        def __init__(self):
            self.calls = 0

        def plan(self, request):
            self.calls += 1
            return PlanOutcome(plan=forbidden)

    class SpyExecutor:
        def __init__(self, inner):
            self.inner, self.sqls = inner, []

        def execute(self, validated_sql, **kwargs):
            self.sqls.append(validated_sql)
            return self.inner.execute(validated_sql, **kwargs)

    planner, executor = ForbiddenPlanner(), SpyExecutor(repository)
    steps = WorkflowSteps(
        member_repository=repository, executor=executor, planner=planner, validator=SqlglotValidator(),
        audit_log=JsonlAuditLog(tmp_path / "audit.jsonl"), clock=utc_now,
    )
    result = SqlRetrieverService(LangGraphRunner(steps)).search(
        {"request_id": "it-forbidden-fake", "question": "회원 목록", "member_id": MEMBER}
    )
    assert result.http_status == 422
    assert result.body["error_code"] == "SQL_VALIDATION_FAILED"
    assert planner.calls == 2  # 첫 계획 + L-1 재시도 1회
    assert executor.sqls == []
    record("workflow", label="forbidden-sql-fake-planner", http_status=result.http_status,
           error_code=result.body["error_code"], llm_calls=planner.calls, executed=len(executor.sqls))
