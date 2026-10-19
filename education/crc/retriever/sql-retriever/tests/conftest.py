"""시험 공용 가짜 객체. 포트 모양만 맞춘 가짜(덕 타이핑)로 DB와 LLM 없이 업무 규칙을 확인함."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from app.application.models import (
    ExecutionResult,
    MemberContext,
    PlanOutcome,
    PlanRequest,
    WorkflowState,
)
from app.application.steps import WorkflowSteps
from app.infrastructure.sql_validator import SqlglotValidator

T0 = datetime(2026, 10, 15, 9, 0, 0, tzinfo=timezone.utc)
DATA_BASE_DATE = date(2026, 8, 31)
COVERAGE_START = date(2025, 8, 1)


class FakeClock:
    """정해 둔 시각을 돌려주는 시계. advance로 흐른 시간을 마음대로 늘림."""

    def __init__(self, start: datetime = T0):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def set_elapsed(self, seconds: float) -> None:
        self.now = T0 + timedelta(seconds=seconds)


class FakePlanner:
    """PlannerPort 모양의 가짜. outcomes에 넣은 순서대로 계획이나 예외를 돌려줌."""

    def __init__(self, *outcomes: Any, clock: FakeClock | None = None, delay: float = 0.0):
        self.outcomes = list(outcomes)
        self.calls: list[PlanRequest] = []
        self.clock, self.delay = clock, delay

    def plan(self, request: PlanRequest) -> PlanOutcome:
        self.calls.append(request)
        if self.clock is not None:
            self.clock.advance(self.delay)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeRepository:
    """MemberRepositoryPort와 SqlExecutorPort 모양의 가짜. 호출 기록(calls)을 남김."""

    def __init__(
        self,
        *,
        join_date: date | None = date(2025, 1, 1),
        member_error: Exception | None = None,
        execute_error: Exception | None = None,
        rows: list[dict[str, Any]] | None = None,
    ):
        self.join_date = join_date
        self.member_error = member_error
        self.execute_error = execute_error
        self.rows = rows if rows is not None else [{"card_ref": "CARD_001"}]
        self.calls: list[tuple[Any, ...]] = []

    def load_member_context(self, member_id: str, requested_base_date: date | None, timeout_ms: int) -> MemberContext:
        self.calls.append(("load_member_context", member_id, requested_base_date, timeout_ms))
        if self.member_error:
            raise self.member_error
        return MemberContext(
            data_base_date=DATA_BASE_DATE,
            base_date=requested_base_date or DATA_BASE_DATE,
            coverage_start=COVERAGE_START,
            join_date=self.join_date,
        )

    def execute(self, validated_sql: str, **kwargs: Any) -> ExecutionResult:
        self.calls.append(("execute", validated_sql, kwargs))
        if self.execute_error:
            raise self.execute_error
        return ExecutionResult(
            columns=[{"name": "card_ref", "type": "text"}], rows=self.rows[: kwargs["row_limit"]], db_elapsed_ms=3
        )


class FakeAuditLog:
    """AuditLogPort 모양의 가짜. fail이면 기록 실패를 흉내 냄."""

    def __init__(self, fail: bool = False):
        self.records: list[Any] = []
        self.fail = fail

    def write(self, record: Any) -> None:
        if self.fail:
            raise OSError("disk full")
        self.records.append(record)


def make_plan(route: str = "FIXED", **overrides: Any) -> dict[str, Any]:
    """C-01 응답 데이터 구조 모양의 계획."""
    plan: dict[str, Any] = {
        "route": route,
        "query_id": "FQ-02" if route == "FIXED" else None,
        "sql": None,
        "target_views": ["app.customer_cards"] if route == "FIXED" else [],
        "requested_period": {"from": None, "to": None},
        "reason": "시험용 계획",
    }
    if route == "NL2SQL":
        plan.update(sql="SELECT month, approved_amount FROM app.monthly_usage", target_views=["app.monthly_usage"])
    plan.update(overrides)
    return plan


def make_steps(
    planner: FakePlanner | None = None,
    repository: FakeRepository | None = None,
    audit: FakeAuditLog | None = None,
    clock: FakeClock | None = None,
) -> WorkflowSteps:
    """가짜 포트를 끼운 단계 묶음. SQL 검사기는 외부 연동이 없어 실제 구현을 씀."""
    repository = repository or FakeRepository()
    return WorkflowSteps(
        member_repository=repository,
        executor=repository,
        planner=planner or FakePlanner(PlanOutcome(plan=make_plan())),
        validator=SqlglotValidator(),
        audit_log=audit or FakeAuditLog(),
        clock=clock or FakeClock(),
    )


def after_r1(**overrides: Any) -> WorkflowState:
    """S-R1을 마친 상태."""
    state: WorkflowState = {
        "request_id": "req-1",
        "question": "보유 카드 목록 보여 주세요",
        "member_id": "M-1001",
        "masked_question": "보유 카드 목록 보여 주세요",
        "masked_count": 0,
        "base_date": DATA_BASE_DATE,
        "coverage_start": COVERAGE_START,
        "started_at": T0,
        "attempt": 0,
        "retry_disabled": False,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def trigger(**overrides: Any) -> dict[str, Any]:
    """트리거 입력(요청 본문)."""
    body: dict[str, Any] = {
        "request_id": "req-1",
        "question": "보유 카드 목록 보여 주세요",
        "member_id": "M-1001",
        "base_date": None,
    }
    body.update(overrides)
    return body
