"""S-R1 ~ S-R6 단계 함수와 분기 판정(설계서 ② 단계별 명세, ⑥ 남은 시간 예산 정책).

각 단계는 상태(WorkflowState)를 받아 그 단계의 출력 필드만 돌려줌. 오류 종료는 RetrieverError를 던짐.
단계를 잇는 흐름 자체는 WorkflowRunnerPort 구현체가 맡음.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from ..domain import time_budget as tb
from ..domain.catalog import ROW_LIMIT, is_allowed_view
from ..domain.fixed_queries import FIXED_QUERIES, match_keyword_rule
from ..domain.masking import mask_identifiers
from ..domain.messages import result_message, unanswerable_message
from ..domain.periods import is_period_answerable
from ..domain.request_rules import (
    is_valid_member_id,
    is_valid_question,
    is_valid_request_id,
    parse_date,
)
from .models import (
    AuditRecord,
    DatabaseFailure,
    DatabaseTimeout,
    PlannerFailure,
    PlanRequest,
    RetrieverError,
    SearchResponse,
    WorkflowState,
)
from .ports import (
    AuditLogPort,
    MemberRepositoryPort,
    PlannerPort,
    SqlExecutorPort,
    SqlValidatorPort,
)

logger = logging.getLogger("sql_retriever.workflow")
ops_logger = logging.getLogger("sql_retriever.ops")  # 운영 알림(사용자 승인 P-10)

ROUTE_FIXED = "FIXED"
ROUTE_NL2SQL = "NL2SQL"
ROUTE_UNANSWERABLE = "UNANSWERABLE"
PLAN_SOURCE_LLM = "LLM"
PLAN_SOURCE_KEYWORD = "KEYWORD_RULE"
VERDICT_FIT = "FIT"
VERDICT_UNFIT = "UNFIT"
VERDICT_UNANSWERABLE = "UNANSWERABLE"
MAX_ATTEMPTS = 2  # 첫 계획 1회 + 반복 구간 L-1 재시도 1회

PLAN_FIELDS = ("route", "query_id", "sql", "target_views", "requested_period", "reason")
REASON_REFUSED = "LLM이 답을 거절함"
REASON_KEYWORD = "LLM을 쓸 수 없어 키워드 규칙으로 정형쿼리를 고름"
REASON_OUT_OF_PERIOD = "데이터 제공 기간 밖"
REASON_RETRY_EXHAUSTED = "다시 계획해도 실행할 수 있는 계획을 만들지 못함"


class WorkflowSteps:
    """S-R1 ~ S-R6 업무 흐름.

    LLM, DB, SQL 검사, 감사 로그, 시계를 생성자로 주입받음. 구현체를 직접 만들지 않으며
    조립은 app/bootstrap.py가 담당함.
    """

    def __init__(
        self,
        *,
        member_repository: MemberRepositoryPort,
        executor: SqlExecutorPort,
        planner: PlannerPort,
        validator: SqlValidatorPort,
        audit_log: AuditLogPort,
        clock: Callable[[], datetime],
    ):
        self.member_repository = member_repository
        self.executor = executor
        self.planner = planner
        self.validator = validator
        self.audit_log = audit_log
        self.clock = clock  # 시간대가 있는 현재 시각을 돌려주는 함수. 시험에서는 가짜 시계를 넣음

    # ------------------------------------------------------------------
    # 시간 예산
    # ------------------------------------------------------------------

    def _elapsed(self, state: WorkflowState) -> float:
        return (self.clock() - state["started_at"]).total_seconds()

    def _measure(self, state: WorkflowState, stage: str, deduction: float) -> tb.BudgetCheck:
        check = tb.check_budget(self._elapsed(state), deduction)
        logger.debug(
            "budget request_id=%s stage=%s elapsed=%.3f remaining_budget=%.3f",
            state.get("request_id"), stage, check.elapsed, check.remaining_budget,
        )
        return check

    def _check_loop_budget(self, state: WorkflowState, stage: str) -> bool:
        """S-R3, S-R4 시작 전 예산을 재고, 재시도를 꺼야 하는지 돌려줌.

        방법: 기준 미달이면 재시도를 끄고 차감값 0초로 다시 계산함(28장 착지 표).
        반환값: 재시도를 끈 상태면 True.
        예외: 차감값 0초로도 미달이면 RetrieverError(TIME_BUDGET_EXCEEDED).
        """
        disabled = bool(state.get("retry_disabled", False))
        deduction = tb.deduction_for(stage, state["attempt"], retry_disabled=disabled)
        if self._measure(state, stage, deduction).can_start:
            return disabled
        if deduction > 0 and self._measure(state, stage, 0.0).can_start:
            logger.info("retry disabled by budget request_id=%s stage=%s", state.get("request_id"), stage)
            return True
        raise RetrieverError("TIME_BUDGET_EXCEEDED", stage=stage)

    # ------------------------------------------------------------------
    # S-R1 검색 요청 접수와 검증
    # ------------------------------------------------------------------

    def step_r1(self, state: WorkflowState) -> dict[str, Any]:
        """요청 형식을 검사하고 식별자를 가린 뒤 회원을 확인함.

        예외: INVALID_REQUEST, MEMBER_NOT_FOUND, DB_ERROR, TIME_BUDGET_EXCEEDED(9장 예외 처리).
        """
        stage = tb.STAGE_R1
        started_at = self.clock()
        timed = {**state, "started_at": started_at}
        if not self._measure(timed, stage, tb.deduction_for(stage)).can_start:
            raise RetrieverError("TIME_BUDGET_EXCEEDED", stage=stage)

        if not is_valid_request_id(state.get("request_id")):
            raise RetrieverError("INVALID_REQUEST", stage=stage, detail="request_id")
        if not is_valid_question(state.get("question")):
            raise RetrieverError("INVALID_REQUEST", stage=stage, detail="question")
        if not is_valid_member_id(state.get("member_id")):
            raise RetrieverError("INVALID_REQUEST", stage=stage, detail="member_id")
        raw_base_date = state.get("base_date")
        requested_base_date: date | None = None
        if raw_base_date is not None:
            requested_base_date = parse_date(raw_base_date)
            if requested_base_date is None:
                raise RetrieverError("INVALID_REQUEST", stage=stage, detail="base_date")

        masked_question, masked_count = mask_identifiers(state["question"])

        # 문장 실행 제한 시간은 DB를 부르기 직전의 남은 시간 예산 이하로 둠
        timeout_ms = self._measure(timed, stage, tb.deduction_for(stage)).remaining_budget_ms
        try:
            context = self.member_repository.load_member_context(
                state["member_id"], requested_base_date, timeout_ms
            )
        except (DatabaseFailure, DatabaseTimeout) as error:
            # 33장 표에서 S-R1의 DB 오류는 시간 초과까지 모두 DB_ERROR임(사용자 승인 P-13)
            raise RetrieverError("DB_ERROR", stage=stage, detail=type(error).__name__) from error

        if requested_base_date is not None and requested_base_date > context.data_base_date:
            raise RetrieverError("INVALID_REQUEST", stage=stage, detail="base_date_after_data_date")
        if context.join_date is None or context.join_date > context.base_date:
            raise RetrieverError("MEMBER_NOT_FOUND", stage=stage)

        return {
            "request_id": state["request_id"],
            "masked_question": masked_question,
            "masked_count": masked_count,
            "member_id": state["member_id"],
            "base_date": context.base_date,
            "coverage_start": context.coverage_start,
            "started_at": started_at,
            "attempt": 0,
            "retry_disabled": False,
        }

    # ------------------------------------------------------------------
    # S-R2 정형쿼리 또는 NL2SQL 판단
    # ------------------------------------------------------------------

    def step_r2(self, state: WorkflowState) -> dict[str, Any]:
        """LLM으로 계획을 만들고, LLM을 못 쓰면 키워드 규칙으로 정형쿼리를 고름.

        방법: 예산이 모자라면 LLM을 부르지 않고 바로 키워드 규칙으로 감(28장 착지).
              LLM 호출 실패는 재시도 없이 키워드 규칙으로 감(11장 예외 처리).
        예외: 키워드 규칙에도 맞는 정형쿼리가 없으면 예산 부족은 TIME_BUDGET_EXCEEDED(사용자 결정),
              LLM 실패는 LLM_UNAVAILABLE.
        """
        stage = tb.STAGE_R2
        attempt = state["attempt"] + 1
        if not self._measure(state, stage, tb.deduction_for(stage)).can_start:
            return self._keyword_plan(state, attempt, missing_code="TIME_BUDGET_EXCEEDED")

        request = PlanRequest(
            question=state["masked_question"],
            base_date=state["base_date"],
            coverage_start=state["coverage_start"],
            attempt=attempt,
            retry_reason=state.get("retry_reason"),
            previous_sql=state.get("previous_sql"),
        )
        try:
            outcome = self.planner.plan(request)
        except PlannerFailure as failure:
            logger.warning(
                "planner failed request_id=%s kind=%s status=%s retry_after=%s",
                state.get("request_id"), failure.kind, failure.status_code, failure.retry_after,
            )
            return self._keyword_plan(state, attempt, missing_code="LLM_UNAVAILABLE")

        if outcome.refusal is not None or outcome.plan is None:
            plan = _plan(ROUTE_UNANSWERABLE, reason=REASON_REFUSED)
        else:
            plan = outcome.plan
        return {"plan": plan, "plan_source": PLAN_SOURCE_LLM, "attempt": attempt}

    def _keyword_plan(self, state: WorkflowState, attempt: int, *, missing_code: str) -> dict[str, Any]:
        query_id = match_keyword_rule(state["masked_question"])
        if query_id is None:
            raise RetrieverError(missing_code, stage=tb.STAGE_R2, detail="no_keyword_match")
        plan = _plan(
            ROUTE_FIXED,
            query_id=query_id,
            target_views=[FIXED_QUERIES[query_id].view],
            reason=REASON_KEYWORD,
        )
        return {"plan": plan, "plan_source": PLAN_SOURCE_KEYWORD, "attempt": attempt}

    # ------------------------------------------------------------------
    # S-R3 계획 적합성 판정
    # ------------------------------------------------------------------

    def step_r3(self, state: WorkflowState) -> dict[str, Any]:
        """계획이 실행 가능하고 데이터 제공 기간 안인지 판정함.

        반환값: verdict FIT, UNFIT, UNANSWERABLE과 관련 필드. 오류 종료는 없음(사용자 결정 D-08).
        """
        retry_disabled = self._check_loop_budget(state, tb.STAGE_R3)
        result = self._judge(state.get("plan"), state["base_date"], state["coverage_start"])

        if result["verdict"] == VERDICT_UNFIT:
            logger.info("plan unfit request_id=%s reason=%s", state.get("request_id"), result["retry_reason"])
            if state["attempt"] >= MAX_ATTEMPTS or retry_disabled:
                # 재시도를 다 썼으면 오류가 아니라 "답할 수 없음" 정상 응답으로 끝냄
                result = {**result, "verdict": VERDICT_UNANSWERABLE, "unanswerable_reason": REASON_RETRY_EXHAUSTED}
        return {**result, "retry_disabled": retry_disabled}

    def _judge(self, plan: Any, base_date: date, coverage_start: date) -> dict[str, Any]:
        def unfit(code: str) -> dict[str, Any]:
            """부적합 판정과 재계획 사유 코드."""
            return _verdict(VERDICT_UNFIT, retry_reason=code)

        if not isinstance(plan, dict) or any(name not in plan for name in PLAN_FIELDS):
            return unfit("PLAN_FIELD_MISSING")

        route = plan["route"]
        if route == ROUTE_UNANSWERABLE:
            return _verdict(VERDICT_UNANSWERABLE, unanswerable_reason=plan.get("reason"))

        if route == ROUTE_FIXED:
            fixed = FIXED_QUERIES.get(plan["query_id"]) if isinstance(plan["query_id"], str) else None
            if fixed is None:
                return unfit("UNKNOWN_QUERY_ID")
            sql, sql_source, query_id, views = fixed.sql, ROUTE_FIXED, fixed.query_id, [fixed.view]
        elif route == ROUTE_NL2SQL:
            sql = plan["sql"]
            if not isinstance(sql, str) or sql.strip() == "":
                return unfit("EMPTY_SQL")
            views = plan["target_views"]
            if not isinstance(views, list) or not views or not all(
                isinstance(view, str) and is_allowed_view(view) for view in views
            ):
                return unfit("VIEW_NOT_ALLOWED")
            sql_source, query_id = ROUTE_NL2SQL, None
        else:
            return unfit("INVALID_ROUTE")

        period = plan["requested_period"]
        period_from = period_to = None
        if period is not None:
            if not isinstance(period, dict):
                return unfit("INVALID_PERIOD")
            raw_from, raw_to = period.get("from"), period.get("to")
            period_from = parse_date(raw_from) if raw_from is not None else None
            period_to = parse_date(raw_to) if raw_to is not None else None
            if (raw_from is not None and period_from is None) or (raw_to is not None and period_to is None):
                return unfit("INVALID_PERIOD")
        if not is_period_answerable(views, period_from, period_to, base_date, coverage_start):
            # 제공 기간 밖은 다시 계획해도 바뀌지 않으므로 재시도하지 않음(12장 비고)
            return _verdict(
                VERDICT_UNANSWERABLE, sql_source=sql_source, query_id=query_id,
                unanswerable_reason=REASON_OUT_OF_PERIOD,
            )
        return _verdict(VERDICT_FIT, candidate_sql=sql, sql_source=sql_source, query_id=query_id)

    # ------------------------------------------------------------------
    # S-R4 SQL 검증
    # ------------------------------------------------------------------

    def step_r4(self, state: WorkflowState) -> dict[str, Any]:
        """SQL 검증 규칙을 통과한 SQL만 다음 단계로 넘김.

        예외: 정형쿼리 검증 실패 또는 재시도를 다 쓴 NL2SQL 실패는 SQL_VALIDATION_FAILED(15장).
        """
        stage = tb.STAGE_R4
        retry_disabled = self._check_loop_budget(state, stage)
        candidate_sql = state["candidate_sql"]
        result = self.validator.validate(candidate_sql)
        if result.ok:
            return {
                "validated_sql": result.sql,
                "row_limit": ROW_LIMIT,
                "retry_reason": None,
                "previous_sql": None,
                "retry_disabled": retry_disabled,
            }

        # 사유 코드는 로그에만 남김. 응답 문구에는 SQL, 뷰 이름, 컬럼 이름을 넣지 않음
        logger.info("sql rejected request_id=%s reason=%s", state.get("request_id"), result.reason)
        if state["sql_source"] == ROUTE_FIXED:
            ops_logger.warning(
                "fixed query failed validation query_id=%s reason=%s", state.get("query_id"), result.reason
            )
            raise RetrieverError("SQL_VALIDATION_FAILED", stage=stage, detail=result.reason)
        if state["attempt"] >= MAX_ATTEMPTS or retry_disabled:
            raise RetrieverError("SQL_VALIDATION_FAILED", stage=stage, detail=result.reason)
        return {
            "validated_sql": None,
            "row_limit": ROW_LIMIT,
            "retry_reason": result.reason,
            "previous_sql": candidate_sql,
            "retry_disabled": retry_disabled,
        }

    # ------------------------------------------------------------------
    # S-R5 SQL 실행
    # ------------------------------------------------------------------

    def step_r5(self, state: WorkflowState) -> dict[str, Any]:
        """검증된 SQL을 회원 범위 안에서 남은 시간 예산 안에 실행함.

        예외: 예산 부족 TIME_BUDGET_EXCEEDED, 실행 제한 시간 초과 DB_TIMEOUT, 그 밖의 DB 오류 DB_ERROR.
        """
        stage = tb.STAGE_R5
        check = self._measure(state, stage, tb.deduction_for(stage))
        if not check.can_start:
            raise RetrieverError("TIME_BUDGET_EXCEEDED", stage=stage)
        row_limit = state.get("row_limit", ROW_LIMIT)
        try:
            result = self.executor.execute(
                state["validated_sql"],
                member_id=state["member_id"],
                base_date=state["base_date"],
                coverage_start=state["coverage_start"],
                timeout_ms=check.remaining_budget_ms,  # 28장 예 4: 남은 시간 예산 2.7초 → 2,700ms 이하
                row_limit=row_limit,
            )
        except DatabaseTimeout as error:
            raise RetrieverError("DB_TIMEOUT", stage=stage) from error
        except DatabaseFailure as error:
            raise RetrieverError("DB_ERROR", stage=stage, detail=str(error)) from error

        row_count = len(result.rows)
        if row_count == 0:
            # 0행은 오류가 아님. 다만 잦으면 세션 변수 지정 누락을 먼저 의심함(17장)
            logger.info("zero rows request_id=%s", state.get("request_id"))
        return {
            "columns": result.columns,
            "rows": result.rows,
            "row_count": row_count,
            "truncated": row_count >= row_limit,
            "db_elapsed_ms": result.db_elapsed_ms,
        }

    # ------------------------------------------------------------------
    # S-R6 응답 구성과 반환
    # ------------------------------------------------------------------

    def step_r6(self, state: WorkflowState) -> dict[str, Any]:
        """결과 또는 "답할 수 없음"을 같은 응답 형식으로 만들고 감사 로그를 남김.

        방법: 종료 처리 시간 1초를 미리 떼어 두었으므로 예산과 상관없이 항상 실행함.
        예외: 응답 구성 실패는 INTERNAL_ERROR. 감사 로그 실패는 응답을 막지 않고 운영 알림만 남김.
        """
        stage = tb.STAGE_R6
        try:
            elapsed_ms = int(self._elapsed(state) * 1000)
            unanswerable = state.get("verdict") == VERDICT_UNANSWERABLE
            base_date: date = state["base_date"]
            if unanswerable:
                columns: list[dict[str, str]] = []
                rows: list[dict[str, Any]] = []
                row_count, truncated = 0, False
                message = unanswerable_message(state.get("unanswerable_reason"))
            else:
                columns, rows = state["columns"], state["rows"]
                row_count, truncated = state["row_count"], state["truncated"]
                message = result_message(base_date, row_count, truncated)
            response = SearchResponse(
                request_id=state["request_id"],
                status=VERDICT_UNANSWERABLE if unanswerable else "OK",
                route=state.get("sql_source"),
                query_id=state.get("query_id"),
                plan_source=state["plan_source"],
                columns=columns,
                rows=rows,
                row_count=row_count,
                truncated=truncated,
                base_date=base_date,
                coverage_start=state["coverage_start"],
                message=message,
                elapsed_ms=elapsed_ms,
            ).model_dump(mode="json")
        except Exception as error:
            raise RetrieverError("INTERNAL_ERROR", stage=stage, detail=type(error).__name__) from error

        try:
            self.audit_log.write(
                AuditRecord(
                    request_id=response["request_id"],
                    route=response["route"],
                    query_id=response["query_id"],
                    plan_source=response["plan_source"],
                    attempt=state["attempt"],
                    elapsed_ms=elapsed_ms,
                    row_count=row_count,
                    masked_question=state["masked_question"],
                    member_hash=hash_member_id(state["member_id"]),
                    status=response["status"],
                )
            )
        except Exception as error:
            ops_logger.warning("audit log failed request_id=%s error=%s", response["request_id"], type(error).__name__)
        return {"response": response}


# ----------------------------------------------------------------------
# 분기 판정. 흐름 구현체가 조건 간선에서 부름
# ----------------------------------------------------------------------


def next_after_r3(state: WorkflowState) -> str:
    """S-R3 다음 단계: FIT → S-R4, UNFIT → S-R2(L-1 재계획), UNANSWERABLE → S-R6."""
    verdict = state["verdict"]
    if verdict == VERDICT_FIT:
        return tb.STAGE_R4
    if verdict == VERDICT_UNFIT:
        return tb.STAGE_R2
    return tb.STAGE_R6


def next_after_r4(state: WorkflowState) -> str:
    """S-R4 다음 단계: 통과 → S-R5, 재생성 → S-R2. 오류 종료는 step_r4가 예외로 처리함."""
    return tb.STAGE_R5 if state.get("validated_sql") else tb.STAGE_R2


def hash_member_id(member_id: str) -> str:
    """감사 로그용 회원ID 해시(SHA-256). 원래 회원ID는 로그에 남기지 않음."""
    return hashlib.sha256(member_id.encode("utf-8")).hexdigest()


def _plan(
    route: str,
    *,
    query_id: str | None = None,
    sql: str | None = None,
    target_views: list[str] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """C-01 응답 데이터 구조(26장)와 같은 모양의 계획을 만듦."""
    return {
        "route": route,
        "query_id": query_id,
        "sql": sql,
        "target_views": target_views or [],
        "requested_period": {"from": None, "to": None},
        "reason": reason,
    }


def _verdict(
    verdict: str,
    *,
    candidate_sql: str | None = None,
    sql_source: str | None = None,
    query_id: str | None = None,
    retry_reason: str | None = None,
    unanswerable_reason: str | None = None,
) -> dict[str, Any]:
    """S-R3 출력 데이터 6개 필드를 빠짐없이 채움."""
    return {
        "verdict": verdict,
        "candidate_sql": candidate_sql,
        "sql_source": sql_source,
        "query_id": query_id,
        "retry_reason": retry_reason,
        "unanswerable_reason": unanswerable_reason,
    }
