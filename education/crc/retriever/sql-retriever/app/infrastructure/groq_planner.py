"""C-01 SQL 계획 생성 LLM 커넥터(설계서 23 ~ 26장). LangChain ChatOpenAI로 Groq OpenAI 호환 주소를 부름."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import openai
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from ..application.models import PlanOutcome, PlannerFailure, PlanRequest
from ..application.ports import PlannerPort

logger = logging.getLogger("sql_retriever.llm")

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT_FILE = PROMPT_DIR / "c01_system_prompt.md"  # 사용자 승인 전문(2026-10-15). 뷰 5개와 FQ-01 ~ FQ-14는 3조가 2026-10-19에 반영
USER_PROMPT_FILE = PROMPT_DIR / "c01_user_prompt.md"
NONE_TEXT = "없음"  # 첫 회 retry_reason, previous_sql 값(26장)

# 하이퍼파라미터(24장). 값을 바꾸려면 설계서를 먼저 고쳐야 함
TEMPERATURE = 0.2  # 설계 가정 A-1
REASONING_EFFORT = "low"  # 설계 가정 A-1
MAX_COMPLETION_TOKENS = 4096  # 사용자 결정
SEED = 42  # 결정적 샘플링은 최선 노력이며 보장되지 않음
TIMEOUT_SECONDS = 5.0  # 설계 가정 A-1. SDK 기본 60초를 반드시 바꿈
MAX_RETRIES = 0  # SDK 기본 2회를 끔. 재시도 역할은 반복 구간 L-1이 맡음(20장)
# top_p는 기본값 1을 바꾸지 않으므로 보내지 않음. logprobs, logit_bias, messages[].name은 Groq가 400을 내므로 쓰지 않음

# 응답 데이터 구조(26장). strict 모드라 모든 필드를 required로 두고 선택 값은 null 허용 타입으로 둠
PLAN_JSON_SCHEMA: dict[str, Any] = {
    "name": "sql_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "route": {"type": "string", "enum": ["FIXED", "NL2SQL", "UNANSWERABLE"]},
            "query_id": {"type": ["string", "null"]},
            "sql": {"type": ["string", "null"]},
            "target_views": {"type": "array", "items": {"type": "string"}},
            "requested_period": {
                "type": "object",
                "properties": {
                    "from": {"type": ["string", "null"]},
                    "to": {"type": ["string", "null"]},
                },
                "required": ["from", "to"],
                "additionalProperties": False,
            },
            "reason": {"type": "string"},
        },
        "required": ["route", "query_id", "sql", "target_views", "requested_period", "reason"],
        "additionalProperties": False,
    },
}


class GroqPlanner(PlannerPort):
    """PlannerPort의 Groq 구현체. 시스템 프롬프트는 파일 전문을 그대로 씀.

    model_factory로 ChatOpenAI 대신 가짜 모델을 넣어 외부 호출 없이 시험할 수 있음.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        model_factory: Callable[..., Any] = ChatOpenAI,
    ):
        system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
        user_prompt = USER_PROMPT_FILE.read_text(encoding="utf-8")
        # 시스템 프롬프트는 JSON 예시의 중괄호가 있어 틀 변수로 해석되지 않게 메시지 객체로 고정함
        self._prompt = ChatPromptTemplate.from_messages(
            [SystemMessage(content=system_prompt), ("human", user_prompt)]
        )
        self._model = model_factory(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=TEMPERATURE,
            reasoning_effort=REASONING_EFFORT,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            seed=SEED,
            timeout=TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
            # Groq 전용 인자는 extra_body로 보냄. 추론 문장을 응답에서 뺌(24장 include_reasoning false)
            extra_body={"include_reasoning": False},
            # Responses API로 자동 전환되지 않게 Chat Completions(POST /chat/completions)로 고정함
            use_responses_api=False,
        )
        self._chain = self._prompt | self._model.with_structured_output(
            PLAN_JSON_SCHEMA, method="json_schema", strict=True, include_raw=True
        )

    def build_messages(self, request: PlanRequest) -> list[Any]:
        """유저 프롬프트를 조립한 메시지 목록을 반환함. 시험에서 조립 결과를 확인할 때도 씀."""
        return self._prompt.format_messages(**_prompt_variables(request))

    def plan(self, request: PlanRequest) -> PlanOutcome:
        """C-01을 1번 호출해 계획을 받음. 실패는 종류를 나눠 PlannerFailure로 알림."""
        try:
            result = self._chain.invoke(_prompt_variables(request))
        except openai.APITimeoutError as error:  # APIConnectionError의 하위 종류라 먼저 잡음
            raise PlannerFailure("TIMEOUT") from error
        except openai.APIConnectionError as error:
            raise PlannerFailure("CONNECTION") from error
        except openai.RateLimitError as error:
            # retry-after는 기록만 하고 기다리지 않음(11장, 시간 예산 보호)
            raise PlannerFailure(
                "RATE_LIMIT", status_code=429, retry_after=error.response.headers.get("retry-after")
            ) from error
        except openai.BadRequestError as error:
            raise PlannerFailure("BAD_REQUEST", status_code=400) from error
        except openai.APIStatusError as error:
            kind = "SERVER_ERROR" if error.status_code >= 500 else "OTHER"  # 401 등은 사용자 승인 P-04
            raise PlannerFailure(kind, status_code=error.status_code) from error
        except Exception as error:  # 예상 밖 SDK 오류도 키워드 규칙 대체 경로로 보냄(P-04)
            raise PlannerFailure("OTHER") from error

        raw = result.get("raw")
        refusal = getattr(raw, "additional_kwargs", {}).get("refusal") if raw is not None else None
        if refusal:
            return PlanOutcome(refusal=str(refusal))
        if result.get("parsing_error") is not None or not isinstance(result.get("parsed"), dict):
            # 응답 JSON을 읽지 못함. 구조화 출력이라 드물며, 대체 경로로 보냄(P-04)
            raise PlannerFailure("OTHER")
        usage = getattr(raw, "usage_metadata", None) or {}
        logger.info(
            "planner ok attempt=%s input_tokens=%s output_tokens=%s",
            request.attempt, usage.get("input_tokens"), usage.get("output_tokens"),
        )
        return PlanOutcome(plan=result["parsed"])


def _prompt_variables(request: PlanRequest) -> dict[str, str]:
    """유저 프롬프트 변수 6개(26장). 회원ID는 넣지 않음."""
    return {
        "question": _escape(request.question),
        "base_date": request.base_date.isoformat(),
        "coverage_start": request.coverage_start.isoformat(),
        "attempt": str(request.attempt),
        # 사유 코드와 직전 SQL은 사람이 쓴 값이 아니라 그대로 넘김. SQL의 < 연산자가 바뀌면 LLM이 헷갈림
        "retry_reason": request.retry_reason or NONE_TEXT,
        "previous_sql": request.previous_sql or NONE_TEXT,
    }


def _escape(text: str) -> str:
    """값 속 꺾쇠를 바꿔 XML 태그 경계가 깨지지 않게 함(질문에 </question>을 넣어 지시를 끼우는 것을 막음)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
