"""C-01 커넥터: 하이퍼파라미터, 프롬프트 조립, 실패 분류. 가짜 모델을 주입해 외부 호출 없이 확인함."""

from datetime import date

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.application.models import PlannerFailure, PlanRequest
from app.infrastructure import groq_planner as gp
from app.infrastructure.settings import GROQ_BASE_URL

REQUEST = PlanRequest(question="보유 카드 목록 <b>", base_date=date(2026, 8, 31), coverage_start=date(2025, 8, 1), attempt=1)


class FakeChatModel:
    """ChatOpenAI 자리에 넣는 가짜. 받은 생성 인자와 with_structured_output 인자를 기록함."""

    def __init__(self, result=None, error=None, **kwargs):
        self.kwargs, self.result, self.error = kwargs, result, error
        self.structured_kwargs = None

    def with_structured_output(self, schema, **kwargs):
        self.structured_kwargs = {"schema": schema, **kwargs}

        def run(_messages):
            if self.error is not None:
                raise self.error
            return self.result

        return RunnableLambda(run)


def planner_with(result=None, error=None):
    holder = {}

    def factory(**kwargs):
        holder["model"] = FakeChatModel(result=result, error=error, **kwargs)
        return holder["model"]

    planner = gp.GroqPlanner(api_key="test-key", model="openai/gpt-oss-120b", base_url=GROQ_BASE_URL,
                             model_factory=factory)
    return planner, holder["model"]


def test_hyperparameters_match_design():
    _, model = planner_with()
    assert model.kwargs == {
        "model": "openai/gpt-oss-120b",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": "test-key",
        "temperature": 0.2,
        "reasoning_effort": "low",
        "max_completion_tokens": 4096,
        "seed": 42,
        "timeout": 5.0,
        "max_retries": 0,
        "extra_body": {"include_reasoning": False},
        "use_responses_api": False,
    }
    for banned in ("logprobs", "logit_bias", "top_p"):
        assert banned not in model.kwargs
    assert model.structured_kwargs["method"] == "json_schema"
    assert model.structured_kwargs["strict"] is True


def test_response_schema_is_strict_six_fields():
    schema = gp.PLAN_JSON_SCHEMA["schema"]
    assert schema["required"] == ["route", "query_id", "sql", "target_views", "requested_period", "reason"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["route"]["enum"] == ["FIXED", "NL2SQL", "UNANSWERABLE"]


def test_system_prompt_has_eight_sections_in_order():
    text = gp.SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    sections = ["[목표]", "[역할]", "[맥락]", "[입력]", "[처리]", "[출력]", "[제약조건]", "[예시]"]
    positions = [text.index(section) for section in sections]
    assert positions == sorted(positions)


def test_user_prompt_is_xml_tagged_and_has_no_member_id():
    planner, _ = planner_with()
    system, human = planner.build_messages(REQUEST)
    assert system.content == gp.SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    assert "<question>보유 카드 목록 &lt;b&gt;</question>" in human.content
    assert "<base_date>2026-08-31</base_date>" in human.content
    assert "<coverage_start>2025-08-01</coverage_start>" in human.content
    assert "<attempt>1</attempt>" in human.content
    assert "<retry_reason>없음</retry_reason>" in human.content
    assert "<previous_sql>없음</previous_sql>" in human.content
    assert "M-" not in human.content


def test_parsed_plan_is_returned():
    plan = {"route": "FIXED", "query_id": "FQ-02", "sql": None, "target_views": ["app.customer_cards"],
            "requested_period": {"from": None, "to": None}, "reason": "보유 카드"}
    planner, _ = planner_with(result={"raw": AIMessage(content=""), "parsed": plan, "parsing_error": None})
    assert planner.plan(REQUEST).plan == plan


def test_refusal_is_returned_as_refusal():
    raw = AIMessage(content="", additional_kwargs={"refusal": "거절"})
    planner, _ = planner_with(result={"raw": raw, "parsed": None, "parsing_error": ValueError("x")})
    outcome = planner.plan(REQUEST)
    assert outcome.refusal == "거절" and outcome.plan is None


def test_parse_failure_is_planner_failure():
    planner, _ = planner_with(result={"raw": AIMessage(content="not json"), "parsed": None, "parsing_error": ValueError()})
    with pytest.raises(PlannerFailure) as caught:
        planner.plan(REQUEST)
    assert caught.value.kind == "OTHER"


def _status_error(cls, status, headers=None):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request, headers=headers or {})
    return cls("error", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "kind", "status"),
    [
        (openai.APITimeoutError(request=httpx.Request("POST", "https://x")), "TIMEOUT", None),
        (openai.APIConnectionError(request=httpx.Request("POST", "https://x")), "CONNECTION", None),
        (_status_error(openai.RateLimitError, 429, {"retry-after": "7"}), "RATE_LIMIT", 429),
        (_status_error(openai.InternalServerError, 503), "SERVER_ERROR", 503),
        (_status_error(openai.BadRequestError, 400), "BAD_REQUEST", 400),
        (_status_error(openai.AuthenticationError, 401), "OTHER", 401),
    ],
)
def test_failure_classification(error, kind, status):
    planner, _ = planner_with(error=error)
    with pytest.raises(PlannerFailure) as caught:
        planner.plan(REQUEST)
    assert caught.value.kind == kind
    assert caught.value.status_code == status
    if kind == "RATE_LIMIT":
        assert caught.value.retry_after == "7"  # 기록만 하고 기다리지 않음
