"""SQL 검색기 서비스. 요청 1건을 워크플로우로 실행하고 결과를 HTTP 상태와 본문으로 바꿈."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .models import RetrieverError, ServiceResult, WorkflowState, error_body
from .ports import WorkflowRunnerPort

logger = logging.getLogger("sql_retriever.service")


class SqlRetrieverService:
    """검색 요청을 받아 워크플로우 W-1을 실행함.

    실제 단계 흐름은 생성자로 주입받은 WorkflowRunnerPort에 맡김. 구현체 생성은 하지 않으며,
    조립은 app/bootstrap.py가 담당함.
    """

    def __init__(self, runner: WorkflowRunnerPort):
        self.runner = runner

    def search(self, payload: Mapping[str, Any]) -> ServiceResult:
        """동기 요청 1건을 처리함.

        인자: payload는 요청 본문(request_id, question, member_id, base_date). 형식 검사는 S-R1이 함.
        반환값: 정상과 답할 수 없음은 HTTP 200과 응답 본문, 오류 종료는 설계서 HTTP 상태와 오류 본문.
        """
        raw_request_id = payload.get("request_id")
        request_id = raw_request_id if isinstance(raw_request_id, str) else ""
        initial_state: WorkflowState = {
            "request_id": payload.get("request_id"),  # type: ignore[typeddict-item]
            "question": payload.get("question"),  # type: ignore[typeddict-item]
            "member_id": payload.get("member_id"),  # type: ignore[typeddict-item]
            "base_date": payload.get("base_date"),
        }
        try:
            final_state = self.runner.run(initial_state)
        except RetrieverError as error:
            # detail(내부 사유 코드)은 로그에만 남기고 응답에는 넣지 않음
            logger.warning(
                "workflow error request_id=%s stage=%s code=%s detail=%s",
                request_id, error.stage, error.code, error.detail,
            )
            return ServiceResult(error.spec.http_status, error_body(request_id, error.code))
        except Exception as error:  # 설계서에 없는 예기치 못한 실패도 내부 정보 없이 INTERNAL_ERROR로 돌려줌
            logger.error("unexpected failure request_id=%s error=%s", request_id, type(error).__name__)
            return ServiceResult(500, error_body(request_id, "INTERNAL_ERROR"))
        return ServiceResult(200, final_state["response"])
