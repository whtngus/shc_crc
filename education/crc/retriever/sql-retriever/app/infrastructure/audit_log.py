"""감사 로그 구현체. 한 줄에 JSON 1건씩 파일에 덧붙임(사용자 승인 P-10)."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..application.models import AuditRecord
from ..application.ports import AuditLogPort


class JsonlAuditLog(AuditLogPort):
    """AuditLogPort 구현체. 여러 요청이 동시에 써도 줄이 섞이지 않게 잠금을 씀."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()

    def write(self, record: AuditRecord) -> None:
        """감사 로그 1건을 덧붙임. 회원ID 원문과 SQL은 AuditRecord에 없으므로 남지 않음."""
        line = json.dumps(
            {"logged_at": datetime.now(timezone.utc).isoformat(), **asdict(record)}, ensure_ascii=False
        )
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
