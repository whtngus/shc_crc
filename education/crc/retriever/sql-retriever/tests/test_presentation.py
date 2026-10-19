"""표현 계층: API의 HTTP 상태 변환과 응답 구조, CLI 출력(가짜 서비스 주입)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.application.models import ERROR_CATALOG, ServiceResult, error_body
from app.presentation import cli
from app.presentation.api import SEARCH_PATH, create_app

OK_BODY = {
    "request_id": "req-1", "status": "OK", "route": "FIXED", "query_id": "FQ-02", "plan_source": "LLM",
    "columns": [{"name": "card_ref", "type": "text"}], "rows": [{"card_ref": "CARD_001"}], "row_count": 1,
    "truncated": False, "base_date": "2026-08-31", "coverage_start": "2025-08-01",
    "message": "기준일 2026-08-31 기준 1건", "elapsed_ms": 10,
}
VALID_BODY = {"request_id": "req-1", "question": "보유 카드 목록", "member_id": "M-1001"}


class FakeService:
    """SqlRetrieverService 모양의 가짜. 받은 요청을 기록하고 정해 둔 결과를 돌려줌."""

    def __init__(self, result: ServiceResult):
        self.result = result
        self.calls = []

    def search(self, payload):
        self.calls.append(payload)
        return self.result


def client(result=ServiceResult(200, OK_BODY)):
    service = FakeService(result)
    return TestClient(create_app(service)), service


def test_api_ok_passes_body_to_service():
    http, service = client()
    response = http.post(SEARCH_PATH, json=VALID_BODY)
    assert response.status_code == 200
    assert response.json() == OK_BODY
    assert service.calls == [{**VALID_BODY, "base_date": None}]


@pytest.mark.parametrize("code", sorted(ERROR_CATALOG))
def test_api_error_status_follows_design(code):
    http, _ = client(ServiceResult(ERROR_CATALOG[code].http_status, error_body("req-1", code)))
    response = http.post(SEARCH_PATH, json=VALID_BODY)
    assert response.status_code == ERROR_CATALOG[code].http_status
    assert set(response.json()) == {"request_id", "status", "error_code", "message", "retryable"}
    assert response.json()["status"] == "ERROR"


@pytest.mark.parametrize(
    "body",
    [
        {"question": "질문", "member_id": "M-1001"},  # request_id 누락
        {"request_id": "req-9", "member_id": "M-1001"},  # question 누락
        {"request_id": "req-9", "question": "질문", "member_id": 1001},  # 타입 오류
    ],
)
def test_api_body_errors_are_invalid_request_400(body):
    http, service = client()
    response = http.post(SEARCH_PATH, json=body)
    assert response.status_code == 400
    assert response.json()["error_code"] == "INVALID_REQUEST"
    assert response.json()["request_id"] == body.get("request_id", "")
    assert service.calls == []


@pytest.mark.parametrize("raw", [b"not json", "{\"question\": \"카드\"}".encode("cp949")])
def test_api_broken_body_is_invalid_request_in_design_format(raw):
    """JSON이 아니거나 UTF-8이 아닌 본문도 33장 오류 응답 형식으로 돌려줌(실제 API 요청에서 찾은 결함)."""
    http, service = client()
    response = http.post(SEARCH_PATH, content=raw, headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert response.json() == error_body("", "INVALID_REQUEST")
    assert service.calls == []


def test_api_unknown_path_keeps_default_404():
    http, _ = client()
    assert http.post("/v1/unknown", json=VALID_BODY).status_code == 404


def test_cli_prints_response_and_exit_code(capsys):
    service = FakeService(ServiceResult(200, OK_BODY))
    code = cli.main(["--member-id", "M-1001", "--question", "보유 카드 목록", "--request-id", "req-1"], service)
    assert code == 0
    assert json.loads(capsys.readouterr().out) == OK_BODY
    assert service.calls[0] == {"request_id": "req-1", "question": "보유 카드 목록", "member_id": "M-1001",
                                "base_date": None}


def test_cli_error_exit_code(capsys):
    service = FakeService(ServiceResult(404, error_body("req-1", "MEMBER_NOT_FOUND")))
    assert cli.main(["--member-id", "M-9999", "--question", "카드"], service) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "MEMBER_NOT_FOUND"
