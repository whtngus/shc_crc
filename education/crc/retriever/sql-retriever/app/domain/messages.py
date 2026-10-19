"""S-R6 상담사 안내 문장 틀(19장 작업 3, 사용자 승인 P-08, P-09)."""

from __future__ import annotations

import re
from datetime import date

# 응답에 내부 뷰 이름을 넣지 않으려고 LLM 사유에서 지울 이름 모양(예: app.monthly_usage)
_INTERNAL_NAME = re.compile(r"\b(?:app_internal|app|public|pg_catalog|information_schema)\.[A-Za-z_][A-Za-z0-9_]*")
_SPACES = re.compile(r"\s{2,}")


def result_message(base_date: date, row_count: int, truncated: bool) -> str:
    """조회 결과 안내 문장을 만듦.

    예시: "기준일 2026-08-31 기준 3건", 200건이면 "기준일 2026-08-31 기준 200건, 앞 200건만 보여 줌",
          0건이면 "기준일 2026-08-31 기준 해당 데이터 없음"
    """
    if row_count == 0:
        return f"기준일 {base_date.isoformat()} 기준 해당 데이터 없음"
    message = f"기준일 {base_date.isoformat()} 기준 {row_count}건"
    if truncated:
        message += f", 앞 {row_count}건만 보여 줌"
    return message


def unanswerable_message(reason: str | None) -> str:
    """답할 수 없음 안내 문장을 만듦. 사유 속 내부 뷰 이름은 지움."""
    cleaned = _SPACES.sub(" ", _INTERNAL_NAME.sub("", reason or "")).strip()
    return f"답할 수 없음: {cleaned}" if cleaned else "답할 수 없음"
