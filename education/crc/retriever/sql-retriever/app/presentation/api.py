"""FastAPI 진입점. 시작 트리거(동기 요청)를 받아 응답을 기다려 돌려줌."""

from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..application.models import ErrorResponse, SearchRequest, SearchResponse, error_body
from ..application.services import SqlRetrieverService

SEARCH_PATH = "/v1/sql-retriever/search"  # 사용자 답(2026-10-15)


def create_app(service: SqlRetrieverService | None = None) -> FastAPI:
    """API 앱을 만듦. service를 넘기면 그대로 쓰고, 없을 때만 bootstrap으로 조립함."""
    app = FastAPI(title="SQL Retriever", version="1.0.0")
    cached_service = service

    def get_service() -> SqlRetrieverService:
        """주입된 서비스를 쓰고, 없으면 처음 한 번만 조립함."""
        nonlocal cached_service
        if cached_service is None:
            from ..bootstrap import create_service  # 없을 때만 조립(지연 import)

            cached_service = create_service()
        return cached_service

    @app.exception_handler(RequestValidationError)
    async def invalid_body(request: Request, error: RequestValidationError) -> JSONResponse:
        """요청 본문 형식 오류를 INVALID_REQUEST 응답으로 바꿈."""
        # 필드 누락과 타입 오류도 FastAPI 기본 422가 아니라 INVALID_REQUEST(400)로 돌려줌(사용자 승인 P-06)
        request_id = ""
        try:
            body = await request.json()
            if isinstance(body, dict) and isinstance(body.get("request_id"), str):
                request_id = body["request_id"]
        except ValueError:
            pass
        return JSONResponse(status_code=400, content=error_body(request_id, "INVALID_REQUEST"))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        """본문이 JSON이 아닐 때 FastAPI가 내는 400도 설계서 오류 응답 형식(INVALID_REQUEST)으로 바꿈."""
        if error.status_code == 400:
            return JSONResponse(status_code=400, content=error_body("", "INVALID_REQUEST"))
        # 없는 경로(404), 허용하지 않는 메서드(405) 등은 검색 워크플로우 밖이라 FastAPI 기본 응답을 그대로 씀
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)

    @app.post(
        SEARCH_PATH,
        response_model=SearchResponse,
        responses={code: {"model": ErrorResponse} for code in (400, 404, 422, 500, 503, 504)},
    )
    def search(request: SearchRequest = Body(...)) -> Any:
        """검색 요청 1건을 처리함. 정상과 답할 수 없음은 200, 오류는 설계서 33장의 HTTP 상태로 돌려줌."""
        # 동기 함수라 FastAPI가 작업 스레드에서 실행함. 오류 코드 → HTTP 상태 변환은 서비스 결과를 그대로 씀
        result = get_service().search(request.model_dump())
        return JSONResponse(status_code=result.http_status, content=result.body)

    return app
