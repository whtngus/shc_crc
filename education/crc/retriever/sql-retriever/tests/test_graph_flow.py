"""LangGraph 흐름 전체: 반복 구간 L-1 되돌림, 재시도 소진, 답할 수 없음 합류, 오류 종료, 서비스 변환."""

from app.application.models import PlanOutcome, PlannerFailure
from app.application.services import SqlRetrieverService
from app.application.steps import WorkflowSteps
from app.infrastructure.graph import LangGraphRunner
from app.infrastructure.sql_validator import SqlglotValidator
from conftest import FakeAuditLog, FakeClock, FakePlanner, FakeRepository, make_plan, make_steps, trigger

BAD_NL2SQL = make_plan("NL2SQL", sql="SELECT member_id FROM app_internal.member_basic")
GOOD_NL2SQL = make_plan("NL2SQL")


def service(planner, repository=None, clock=None, audit=None):
    steps = make_steps(planner=planner, repository=repository, clock=clock, audit=audit)
    return SqlRetrieverService(LangGraphRunner(steps))


def test_fixed_route_end_to_end():
    planner = FakePlanner(PlanOutcome(plan=make_plan("FIXED", query_id="FQ-02")))
    result = service(planner).search(trigger())
    assert result.http_status == 200
    assert result.body["status"] == "OK"
    assert result.body["route"] == "FIXED"
    assert result.body["query_id"] == "FQ-02"
    assert result.body["plan_source"] == "LLM"


def test_validation_failure_retries_once_through_r2():
    """S-R4 실패 → S-R2(사유와 직전 SQL 전달) → S-R3 → S-R4 통과 → S-R5 → S-R6."""
    planner = FakePlanner(PlanOutcome(plan=BAD_NL2SQL), PlanOutcome(plan=GOOD_NL2SQL))
    repository = FakeRepository()
    audit = FakeAuditLog()
    result = service(planner, repository, audit=audit).search(trigger())
    assert result.http_status == 200
    assert len(planner.calls) == 2
    assert planner.calls[1].attempt == 2
    assert planner.calls[1].retry_reason == "SCHEMA_NOT_ALLOWED"
    assert planner.calls[1].previous_sql == BAD_NL2SQL["sql"]
    executed = [call for call in repository.calls if call[0] == "execute"]
    assert len(executed) == 1  # 검증을 통과한 SQL만 실행함
    assert "app_internal" not in executed[0][1]
    assert audit.records[0].attempt == 2


def test_validation_failure_twice_is_sql_validation_failed():
    planner = FakePlanner(PlanOutcome(plan=BAD_NL2SQL), PlanOutcome(plan=BAD_NL2SQL))
    repository = FakeRepository()
    result = service(planner, repository).search(trigger())
    assert result.http_status == 422
    assert result.body == {
        "request_id": "req-1",
        "status": "ERROR",
        "error_code": "SQL_VALIDATION_FAILED",
        "message": "질문을 처리할 데이터 조회 문장을 만들지 못했습니다. 질문을 바꿔 다시 요청해 주세요.",
        "retryable": False,
    }
    assert [call for call in repository.calls if call[0] == "execute"] == []  # 검증 실패 SQL은 실행 안 함


def test_unfit_twice_ends_as_unanswerable():
    unfit = make_plan("FIXED", query_id="FQ-99")
    planner = FakePlanner(PlanOutcome(plan=unfit), PlanOutcome(plan=unfit))
    result = service(planner).search(trigger())
    assert result.http_status == 200
    assert result.body["status"] == "UNANSWERABLE"
    assert len(planner.calls) == 2


def test_unanswerable_skips_r4_r5():
    planner = FakePlanner(PlanOutcome(plan=make_plan("UNANSWERABLE", reason="포인트는 공개 뷰에 없음")))
    repository = FakeRepository()
    result = service(planner, repository).search(trigger())
    assert result.body["status"] == "UNANSWERABLE"
    assert result.body["message"] == "답할 수 없음: 포인트는 공개 뷰에 없음"
    assert [call for call in repository.calls if call[0] == "execute"] == []


def test_llm_failure_keyword_fallback_end_to_end():
    planner = FakePlanner(PlannerFailure("TIMEOUT"))
    result = service(planner).search(trigger(question="최근 연체 있나요"))
    assert result.http_status == 200
    assert result.body["plan_source"] == "KEYWORD_RULE"
    assert result.body["query_id"] == "FQ-05"


def test_llm_unavailable_maps_to_503():
    result = service(FakePlanner(PlannerFailure("SERVER_ERROR"))).search(trigger(question="포인트 잔액"))
    assert result.http_status == 503
    assert result.body["error_code"] == "LLM_UNAVAILABLE"
    assert result.body["retryable"] is True


class SlowValidator:
    """SqlValidatorPort 모양의 가짜. 실제 검사기를 쓰되 검사마다 시계를 늘림."""

    def __init__(self, clock, seconds):
        self.inner, self.clock, self.seconds = SqlglotValidator(), clock, seconds

    def validate(self, sql):
        self.clock.advance(self.seconds)
        return self.inner.validate(sql)


def test_slow_request_lands_on_keyword_rule_at_r2_retry():
    """S-R2 재시도 시작 전 예산 부족(기존 사용 8.5초 → 남은 시간 예산 0.5초) → LLM 대신 키워드 규칙(28장 착지)."""
    clock = FakeClock()
    planner = FakePlanner(PlanOutcome(plan=BAD_NL2SQL), clock=clock, delay=8.0)
    repository = FakeRepository()
    steps = WorkflowSteps(
        member_repository=repository, executor=repository, planner=planner,
        validator=SlowValidator(clock, 0.5), audit_log=FakeAuditLog(), clock=clock,
    )
    result = SqlRetrieverService(LangGraphRunner(steps)).search(trigger())
    assert len(planner.calls) == 1  # 재시도에서는 LLM을 부르지 않음
    assert result.http_status == 200
    assert result.body["plan_source"] == "KEYWORD_RULE"
    assert result.body["query_id"] == "FQ-02"


def test_slow_llm_disables_retry_at_r3():
    """1차 LLM이 9.6초 걸림 → S-R3 기준 미달 → 재시도를 끄고 계속 → S-R4 실패는 되돌아가지 않고 오류 종료."""
    clock = FakeClock()
    planner = FakePlanner(PlanOutcome(plan=BAD_NL2SQL), clock=clock, delay=9.6)
    result = service(planner, clock=clock).search(trigger())
    assert len(planner.calls) == 1
    assert result.http_status == 422
    assert result.body["error_code"] == "SQL_VALIDATION_FAILED"


def test_invalid_request_maps_to_400_with_empty_request_id():
    result = service(FakePlanner()).search(trigger(request_id=None))
    assert result.http_status == 400
    assert result.body["request_id"] == ""
    assert result.body["error_code"] == "INVALID_REQUEST"


def test_graph_shape_matches_design():
    """컴파일된 그래프의 노드와 간선이 7장 Mermaid 도식과 같은지 확인함."""
    mermaid = LangGraphRunner(make_steps()).mermaid()
    for edge in ("S-R1 --> S-R2", "S-R2 --> S-R3", "S-R5 --> S-R6"):
        assert edge.replace("S-R", "S_R") in mermaid.replace("S-R", "S_R")
    for node in ("S-R1", "S-R2", "S-R3", "S-R4", "S-R5", "S-R6"):
        assert node in mermaid
