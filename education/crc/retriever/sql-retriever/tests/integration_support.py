"""통합 시험 공용 도구. 실제 설정으로 구현체를 만들고 실측값을 work/measurements.jsonl에 남김."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.application.models import PlanOutcome, PlanRequest
from app.application.services import SqlRetrieverService
from app.application.steps import WorkflowSteps
from app.bootstrap import create_planner, utc_now
from app.infrastructure.audit_log import JsonlAuditLog
from app.infrastructure.graph import LangGraphRunner
from app.infrastructure.postgres_repository import PostgresRepository
from app.infrastructure.settings import load_settings
from app.infrastructure.sql_validator import SqlglotValidator

MEASUREMENTS = Path(__file__).resolve().parents[1] / "work" / "measurements.jsonl"
LLM_MIN_INTERVAL_SECONDS = 20.0  # Groq 분당 토큰 한도(위험 R-03)에 걸리지 않게 LLM 호출 사이를 띄움
_last_llm_call = 0.0


def record(kind: str, **data: Any) -> None:
    """실측값 1건을 덧붙임. SQL 문장과 회원ID 원문은 넣지 않음."""
    MEASUREMENTS.parent.mkdir(parents=True, exist_ok=True)
    line = {"measured_at": datetime.now(timezone.utc).isoformat(), "kind": kind, **data}
    with MEASUREMENTS.open("a", encoding="utf-8") as file:
        file.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")


def make_repository() -> PostgresRepository:
    settings = load_settings()
    return PostgresRepository(
        host=settings.db_host, port=settings.db_port, dbname=settings.db_name,
        user=settings.db_user, password=settings.db_password,
    )


def pace_llm_calls() -> None:
    """앞 LLM 호출과 20초 이상 띄움. 요청의 시간 예산에 들어가지 않게 요청을 보내기 전에 부름."""
    wait = LLM_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_llm_call)
    if wait > 0:
        time.sleep(wait)


class _TokenCapture(logging.Handler):
    """C-01 구현체가 남기는 "planner ok" 로그에서 입력과 출력 토큰 수를 받아 둠."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.last: dict[str, Any] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage().startswith("planner ok") and isinstance(record.args, tuple):
            _, input_tokens, output_tokens = record.args
            self.last = {"input_tokens": input_tokens, "output_tokens": output_tokens}


class TimedPlanner:
    """실제 C-01 구현체를 감싸 호출 시간과 토큰 수를 잼."""

    def __init__(self, inner):
        self.inner = inner
        self.calls: list[dict[str, Any]] = []
        self._tokens = _TokenCapture()
        llm_logger = logging.getLogger("sql_retriever.llm")
        llm_logger.setLevel(logging.INFO)
        llm_logger.addHandler(self._tokens)

    def plan(self, request: PlanRequest) -> PlanOutcome:
        global _last_llm_call
        started = time.perf_counter()
        try:
            self._tokens.last = {}
            outcome = self.inner.plan(request)
            self.calls.append({"attempt": request.attempt, "ms": int((time.perf_counter() - started) * 1000),
                               "result": "refusal" if outcome.refusal else "plan", **self._tokens.last})
            return outcome
        except Exception as error:
            self.calls.append({"attempt": request.attempt, "ms": int((time.perf_counter() - started) * 1000),
                               "result": getattr(error, "kind", type(error).__name__)})
            raise
        finally:
            _last_llm_call = time.monotonic()


class TimedClockSteps(WorkflowSteps):
    """단계마다 시작 시각을 기록하는 WorkflowSteps. 실측 보고용이며 동작은 그대로임."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_log: list[tuple[str, float]] = []

    def _mark(self, stage, state):
        started_at = state.get("started_at")
        elapsed = (self.clock() - started_at).total_seconds() if started_at else 0.0
        self.stage_log.append((stage, round(elapsed, 3)))

    def step_r1(self, state):
        self._mark("S-R1", state)
        return super().step_r1(state)

    def step_r2(self, state):
        self._mark("S-R2", state)
        return super().step_r2(state)

    def step_r3(self, state):
        self._mark("S-R3", state)
        return super().step_r3(state)

    def step_r4(self, state):
        self._mark("S-R4", state)
        return super().step_r4(state)

    def step_r5(self, state):
        self._mark("S-R5", state)
        return super().step_r5(state)

    def step_r6(self, state):
        self._mark("S-R6", state)
        return super().step_r6(state)


def make_real_service(tmp_audit: Path) -> tuple[SqlRetrieverService, TimedPlanner, TimedClockSteps]:
    """실제 DB와 실제 Groq로 서비스를 만듦. 감사 로그만 시험용 파일로 돌림."""
    settings = load_settings()
    repository = make_repository()
    planner = TimedPlanner(create_planner(settings))
    steps = TimedClockSteps(
        member_repository=repository, executor=repository, planner=planner,
        validator=SqlglotValidator(), audit_log=JsonlAuditLog(tmp_audit), clock=utc_now,
    )
    return SqlRetrieverService(LangGraphRunner(steps)), planner, steps
