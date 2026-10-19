"""계층 사이를 오가는 요청, 응답, 상태, 오류 구조(설계서 8 ~ 19장, 32 ~ 33장)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 오류 코드(33장). HTTP 상태와 다시 시도 여부를 한곳에 둠
# 안내 문구에는 SQL, 뷰 이름, 컬럼 이름, 접속 정보, 키를 넣지 않음(D-1103)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorSpec:
    """오류 코드 1개의 HTTP 상태, 다시 시도 여부, 한국어 안내."""

    http_status: int
    retryable: bool
    message: str


ERROR_CATALOG: dict[str, ErrorSpec] = {
    "INVALID_REQUEST": ErrorSpec(400, False, "요청 형식이 올바르지 않습니다. 질문, 회원ID, 기준일을 확인해 주세요."),
    "MEMBER_NOT_FOUND": ErrorSpec(404, False, "회원을 찾을 수 없거나 기준일에 아직 가입 전인 회원입니다."),
    "LLM_UNAVAILABLE": ErrorSpec(503, True, "지금은 질문을 해석할 수 없습니다. 잠시 후 다시 요청해 주세요."),
    "SQL_VALIDATION_FAILED": ErrorSpec(
        422, False, "질문을 처리할 데이터 조회 문장을 만들지 못했습니다. 질문을 바꿔 다시 요청해 주세요."
    ),
    "DB_TIMEOUT": ErrorSpec(504, True, "데이터 조회 시간이 초과되었습니다. 잠시 후 다시 요청해 주세요."),
    "DB_ERROR": ErrorSpec(500, True, "데이터 조회 중 오류가 발생했습니다. 잠시 후 다시 요청해 주세요."),
    "TIME_BUDGET_EXCEEDED": ErrorSpec(504, True, "처리 시간이 부족해 요청을 끝내지 못했습니다. 다시 요청해 주세요."),
    "INTERNAL_ERROR": ErrorSpec(500, True, "응답을 만드는 중 오류가 발생했습니다. 다시 요청해 주세요."),
}


class RetrieverError(Exception):
    """워크플로우 오류 종료. 오류 코드로 HTTP 상태와 안내 문구가 정해짐.

    detail은 로그에만 남기는 내부 사유 코드임. 응답에는 넣지 않음.
    """

    def __init__(self, code: str, *, stage: str, detail: str | None = None):
        if code not in ERROR_CATALOG:
            raise ValueError(f"설계서에 없는 오류 코드: {code}")
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.detail = detail

    @property
    def spec(self) -> ErrorSpec:
        """이 오류 코드의 HTTP 상태와 안내 문구."""
        return ERROR_CATALOG[self.code]


# ---------------------------------------------------------------------------
# 포트가 던지는 예외. 단계 함수가 받아 설계서 오류 코드로 바꿈
# ---------------------------------------------------------------------------


class DatabaseTimeout(Exception):
    """DB 문장 실행 제한 시간(statement_timeout) 초과."""


class DatabaseFailure(Exception):
    """DB 접속 또는 조회 실패. 사유는 로그용 문자열만 담고 SQL이나 접속 정보는 담지 않음."""


class PlannerFailure(Exception):
    """LLM 호출 실패. kind로 실패 종류(TIMEOUT, CONNECTION, RATE_LIMIT, SERVER_ERROR, BAD_REQUEST, OTHER)를 알림."""

    def __init__(self, kind: str, *, status_code: int | None = None, retry_after: str | None = None):
        super().__init__(kind)
        self.kind = kind
        self.status_code = status_code
        self.retry_after = retry_after  # 429 응답의 retry-after 값. 기록만 하고 기다리지 않음(11장)


# ---------------------------------------------------------------------------
# 포트 입출력 구조
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberContext:
    """S-R1 DB 확인 결과."""

    data_base_date: date  # lab_metadata의 데이터 기준일
    base_date: date  # 확정 기준일(요청 값 또는 데이터 기준일)
    coverage_start: date  # 거래 제공 시작일
    join_date: date | None  # 회원 가입일. 회원이 없으면 None


@dataclass(frozen=True)
class PlanRequest:
    """C-01 유저 프롬프트 변수 6개(26장). member_id는 일부러 두지 않음."""

    question: str  # 가린 질문(masked_question)
    base_date: date
    coverage_start: date
    attempt: int  # 1 또는 2
    retry_reason: str | None = None
    previous_sql: str | None = None


@dataclass(frozen=True)
class PlanOutcome:
    """C-01 응답. plan 또는 refusal 둘 중 하나만 값이 있음."""

    plan: dict[str, Any] | None = None  # 응답 데이터 구조 6개 필드(26장)
    refusal: str | None = None  # LLM이 답을 거절한 문장


@dataclass(frozen=True)
class ValidationResult:
    """S-R4 SQL 검사 결과. 통과하면 sql에 LIMIT을 맞춘 문장이, 실패하면 reason에 사유 코드가 담김."""

    ok: bool
    sql: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    """S-R5 SQL 실행 결과."""

    columns: list[dict[str, str]]  # [{"name": 컬럼 이름, "type": 타입 이름}]
    rows: list[dict[str, Any]]  # JSON으로 바로 바꿀 수 있는 값만 담음(날짜는 문자열)
    db_elapsed_ms: int


@dataclass(frozen=True)
class AuditRecord:
    """S-R6 감사 로그 1건(19장 작업 5). 질문은 가린 문장만, 회원ID는 해시값만 담음."""

    request_id: str
    route: str | None
    query_id: str | None
    plan_source: str | None
    attempt: int
    elapsed_ms: int
    row_count: int
    masked_question: str
    member_hash: str
    status: str


# ---------------------------------------------------------------------------
# 워크플로우 상태. 단계 사이에 오가는 필드(부록 32장 필드 영문명)를 그대로 씀
# ---------------------------------------------------------------------------


class WorkflowState(TypedDict, total=False):
    """S-R1 ~ S-R6가 주고받는 필드. 이름과 뜻은 설계서 32장과 같음."""

    # 트리거 입력
    request_id: str
    question: str
    member_id: str  # 세션 변수 전용. LLM과 응답에 넣지 않음
    # 트리거에서는 요청 원문 문자열(선택), S-R1 뒤에는 확정 기준일(date)로 바뀜
    base_date: date | str | None
    # S-R1
    masked_question: str
    masked_count: int
    coverage_start: date
    started_at: datetime
    attempt: int
    # S-R2
    plan: dict[str, Any] | None
    plan_source: str
    # S-R3
    verdict: str
    candidate_sql: str | None
    sql_source: str | None
    query_id: str | None
    retry_reason: str | None
    unanswerable_reason: str | None
    # S-R4
    validated_sql: str | None
    row_limit: int
    previous_sql: str | None
    # S-R5
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    db_elapsed_ms: int
    # S-R6
    response: dict[str, Any]
    # 내부 표시(사용자 승인 P-03): 예산 착지로 재시도를 껐는지. 응답에는 나가지 않음
    retry_disabled: bool


# ---------------------------------------------------------------------------
# 진입 API 계약(pydantic). OpenAPI 문서에 설명이 그대로 나감
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """동기 검색 요청(S-R1 입력 데이터). 형식 검사는 S-R1이 설계서 규칙대로 다시 함."""

    request_id: str = Field(description="호출 추적 ID")
    question: str = Field(description="상담사 질문 원문. 1 ~ 500자")
    member_id: str = Field(description="상담 중인 회원ID. 형식 M- + 숫자 4자리")
    base_date: str | None = Field(default=None, description="조회 기준일(YYYY-MM-DD). 없으면 데이터 기준일")


class SearchResponse(BaseModel):
    """호출자 응답(18장 출력 데이터 13개 필드). SQL 문장과 회원ID는 넣지 않음."""

    request_id: str = Field(description="요청 추적 ID")
    status: str = Field(description="OK 또는 UNANSWERABLE")
    route: str | None = Field(default=None, description="FIXED 또는 NL2SQL")
    query_id: str | None = Field(default=None, description="정형쿼리ID")
    plan_source: str = Field(description="LLM 또는 KEYWORD_RULE")
    columns: list[dict[str, str]] = Field(description="컬럼 이름과 타입 목록")
    rows: list[dict[str, Any]] = Field(description="결과 행")
    row_count: int = Field(description="결과 행 수")
    truncated: bool = Field(description="행 상한 도달 여부")
    base_date: date = Field(description="조회 기준일")
    coverage_start: date = Field(description="거래 제공 시작일")
    message: str = Field(description="상담사에게 보여 줄 한 줄 안내")
    elapsed_ms: int = Field(description="전체 처리 시간(밀리초)")


class ErrorResponse(BaseModel):
    """오류 응답(33장). 다시 시도해도 되는지만 알려 줌."""

    request_id: str = Field(description="요청 추적 ID. 요청에서 읽지 못하면 빈 문자열")
    status: str = Field(default="ERROR", description='항상 "ERROR"')
    error_code: str = Field(description="오류 코드")
    message: str = Field(description="한국어 안내")
    retryable: bool = Field(description="다시 시도해도 되는지")


@dataclass(frozen=True)
class ServiceResult:
    """서비스 실행 결과. 표현 계층은 http_status와 body만 보고 응답을 만듦."""

    http_status: int
    body: dict[str, Any]


def error_body(request_id: str, code: str) -> dict[str, Any]:
    """오류 코드로 오류 응답 본문을 만듦."""
    spec = ERROR_CATALOG[code]
    return ErrorResponse(
        request_id=request_id, error_code=code, message=spec.message, retryable=spec.retryable
    ).model_dump()
