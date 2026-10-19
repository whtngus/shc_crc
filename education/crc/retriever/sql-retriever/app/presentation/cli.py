"""CLI 진입점. 질문 하나를 넣으면 설계서 응답 데이터 구조(JSON)를 출력함."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence

from ..application.services import SqlRetrieverService


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 정의(사용자 승인 P-15)."""
    parser = argparse.ArgumentParser(description="SQL 검색기: 상담사 질문 1건을 정형 DB에서 조회함")
    parser.add_argument("--member-id", required=True, help="상담 중인 회원ID(예: M-1001)")
    parser.add_argument("--question", required=True, help="상담사 질문(1 ~ 500자)")
    parser.add_argument("--base-date", default=None, help="조회 기준일 YYYY-MM-DD(없으면 데이터 기준일)")
    parser.add_argument("--request-id", default=None, help="호출 추적 ID(없으면 자동 생성)")
    return parser


def main(argv: Sequence[str] | None = None, service: SqlRetrieverService | None = None) -> int:
    """질문 1건을 실행하고 응답 JSON을 표준 출력에 씀.

    반환값: HTTP 200에 해당하면 0, 오류 응답이면 1(종료 코드).
    """
    args = build_parser().parse_args(argv)
    if service is None:
        from ..bootstrap import configure_logging, create_service  # 없을 때만 조립(지연 import)

        configure_logging()
        service = create_service()
    payload = {
        "request_id": args.request_id or f"cli-{uuid.uuid4().hex[:12]}",
        "question": args.question,
        "member_id": args.member_id,
        "base_date": args.base_date,
    }
    result = service.search(payload)
    # Windows 콘솔 기본 인코딩(cp949)에서도 한글이 깨지지 않게 UTF-8로 씀
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(json.dumps(result.body, ensure_ascii=False, indent=2))
    return 0 if result.http_status == 200 else 1
