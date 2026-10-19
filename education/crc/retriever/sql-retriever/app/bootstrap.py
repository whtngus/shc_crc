"""조립 지점. 설정을 읽고 구현체를 만들어 서비스에 끼움. 구현체 생성은 이 파일에서만 함."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from .application.ports import PlannerPort
from .application.services import SqlRetrieverService
from .application.steps import WorkflowSteps
from .infrastructure.audit_log import JsonlAuditLog
from .infrastructure.graph import LangGraphRunner
from .infrastructure.groq_planner import GroqPlanner
from .infrastructure.postgres_repository import PostgresRepository
from .infrastructure.settings import GROQ_BASE_URL, Settings, SettingsError, load_settings
from .infrastructure.sql_validator import SqlglotValidator


def create_planner(settings: Settings) -> PlannerPort:
    """설정의 제공자 이름으로 C-01 구현체를 고름.

    선택 기준: SQL_RETRIEVER_LLM_PROVIDER = groq → GroqPlanner. 다른 제공자는 같은 응답 구조를 지키는
    어댑터를 더한 뒤 여기에 분기를 추가함(23장).
    예외: 지원하지 않는 제공자면 SettingsError를 발생시킴.
    """
    if settings.llm_provider == "groq":
        return GroqPlanner(api_key=settings.groq_api_key, model=settings.llm_model, base_url=GROQ_BASE_URL)
    raise SettingsError("SQL_RETRIEVER_LLM_PROVIDER는 지금 groq만 지원합니다.")


def utc_now() -> datetime:
    """시간대가 붙은 현재 시각. started_at과 남은 시간 계산에 씀."""
    return datetime.now(timezone.utc)


def create_service(env_file: Path | None = None) -> SqlRetrieverService:
    """설정 읽기 → 구현체 생성 → 서비스 조립 순서로 SQL 검색기 서비스를 만듦."""
    settings = load_settings(env_file)
    repository = PostgresRepository(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
    )
    steps = WorkflowSteps(
        member_repository=repository,
        executor=repository,
        planner=create_planner(settings),
        validator=SqlglotValidator(),
        audit_log=JsonlAuditLog(settings.audit_log_path),
        clock=utc_now,
    )
    return SqlRetrieverService(LangGraphRunner(steps))


def configure_logging(level: int = logging.INFO) -> None:
    """서비스 로그를 표준 오류로 내보냄. 로그에는 사유 코드만 남고 SQL, 회원ID, 키는 남지 않음."""
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # HTTP 클라이언트가 요청 주소를 INFO로 찍으므로 경고 이상만 남김(openai SDK는 httpx2를 씀)
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
