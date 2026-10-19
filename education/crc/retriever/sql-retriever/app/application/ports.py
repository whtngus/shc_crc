"""응용 계층이 바깥 기술에 요구하는 약속(포트). 구현체는 바깥 기반 계층에 둠."""

from __future__ import annotations

from abc import abstractmethod
from datetime import date
from typing import Protocol

from .models import (
    AuditRecord,
    ExecutionResult,
    MemberContext,
    PlanOutcome,
    PlanRequest,
    ValidationResult,
    WorkflowState,
)


class PlannerPort(Protocol):
    """C-01 SQL 계획 생성 LLM 계약. 제공자를 더하면 이 포트를 지키는 어댑터를 하나 더 만듦(23장)."""

    @abstractmethod
    def plan(self, request: PlanRequest) -> PlanOutcome:
        """질문을 정형쿼리 선택 또는 NL2SQL 계획으로 바꿈.

        인자: request에는 가린 질문만 담김. 회원ID는 받지 않음.
        반환값: 계획 dict(route, query_id, sql, target_views, requested_period, reason) 또는 거절 문장.
        예외: 타임아웃, 연결 오류, 429, 5xx, 400 등 호출 실패는 PlannerFailure를 발생시킴. 재시도는 하지 않음.
        부수효과: 외부 LLM API를 1번 호출함.
        """


class MemberRepositoryPort(Protocol):
    """S-R1 회원 확인 계약."""

    @abstractmethod
    def load_member_context(
        self, member_id: str, requested_base_date: date | None, timeout_ms: int
    ) -> MemberContext:
        """데이터 기준일, 거래 제공 시작일, 회원 가입일을 읽기 전용 트랜잭션 하나에서 읽음.

        인자: requested_base_date가 None이면 데이터 기준일로 세션 변수를 지정함.
              timeout_ms는 문장 실행 제한 시간이며 그 시점 남은 시간 예산 이하로 줌.
        반환값: MemberContext. 회원이 없으면 join_date가 None임.
        예외: 접속 또는 조회 실패(시간 초과 포함)는 DatabaseFailure를 발생시킴.
        부수효과: 없음(읽기 전용, 트랜잭션은 ROLLBACK으로 끝남).
        """


class SqlExecutorPort(Protocol):
    """S-R5 검증된 SQL 실행 계약."""

    @abstractmethod
    def execute(
        self,
        validated_sql: str,
        *,
        member_id: str,
        base_date: date,
        coverage_start: date,
        timeout_ms: int,
        row_limit: int,
    ) -> ExecutionResult:
        """검증된 SQL을 회원 세션 변수를 건 읽기 전용 트랜잭션에서 실행함.

        인자: validated_sql은 SqlValidatorPort를 통과한 문장만 넘김. timeout_ms는 남은 시간 예산 이하임.
        반환값: 최대 row_limit행. 결과가 없으면 rows가 빈 목록임(오류 아님).
        예외: 실행 제한 시간 초과는 DatabaseTimeout, 그 밖의 DB 오류는 DatabaseFailure를 발생시킴.
        부수효과: 없음(읽기 전용, ROLLBACK으로 세션 변수까지 지움).
        """


class SqlValidatorPort(Protocol):
    """S-R4 SQL 검증 규칙(31장) 계약."""

    @abstractmethod
    def validate(self, sql: str) -> ValidationResult:
        """SQL을 문법 트리로 검사하고 행 상한을 맞춤.

        반환값: 통과하면 ok True와 LIMIT 200 이하로 맞춘 SQL. 실패하면 ok False와 사유 코드.
        예외: 없음. 파싱 실패도 사유 코드 PARSE_ERROR로 돌려줌.
        부수효과: 없음.
        """


class AuditLogPort(Protocol):
    """S-R6 감사 로그 기록 계약."""

    @abstractmethod
    def write(self, record: AuditRecord) -> None:
        """감사 로그 1건을 남김.

        예외: 기록 실패 시 OSError 등을 발생시킴. 호출자는 응답을 막지 않고 실패만 알림.
        부수효과: 로그 저장소(파일 등)에 1건을 덧붙임.
        """


class WorkflowRunnerPort(Protocol):
    """S-R1 ~ S-R6 단계 흐름 실행 계약."""

    @abstractmethod
    def run(self, initial_state: WorkflowState) -> WorkflowState:
        """트리거 입력으로 워크플로우를 끝까지 실행함.

        반환값: S-R6까지 마친 최종 상태. response 필드에 호출자 응답이 담김.
        예외: 오류 종료는 RetrieverError를 그대로 발생시킴.
        부수효과: 단계가 쓰는 포트(LLM, DB, 감사 로그)의 부수효과를 그대로 가짐.
        """
