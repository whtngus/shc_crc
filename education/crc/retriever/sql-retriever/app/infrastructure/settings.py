"""실행 설정 읽기. 비밀값은 `secrets/.env` 또는 환경변수에서만 읽고 코드에 두지 않음."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # retriever/sql-retriever 폴더
# 비밀값 파일 기본 위치: 저장소 루트의 secrets/.env. SQL_RETRIEVER_ENV_FILE로 바꿀 수 있음
DEFAULT_ENV_FILE = PROJECT_ROOT.parents[1] / "secrets" / ".env"  # retriever/ 한 단계 위가 저장소 루트

# C-01 연결 정보(24장). 접속 주소는 설계서 값이며 실행 설정으로 바꾸지 않음
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class SettingsError(RuntimeError):
    """필수 설정이 없거나 값이 틀림. 메시지에는 설정 이름만 넣고 값은 넣지 않음."""


@dataclass(frozen=True)
class Settings:
    """서비스 실행 설정. bootstrap이 읽어 구현체에 넘김."""

    llm_provider: str  # SQL_RETRIEVER_LLM_PROVIDER(23장). 지금은 groq만 지원
    llm_model: str  # SQL_RETRIEVER_LLM_MODEL(23장)
    groq_api_key: str = field(repr=False)  # GROQ_API_KEY. repr에 나오지 않게 숨김
    db_password: str = field(repr=False)  # RDB_PASSWORD
    db_host: str = "localhost"  # 사용자 답(2026-10-15)
    db_port: int = 5432
    db_name: str = "cardlab"  # 설계서 23장
    # 설계서 2장 NL2SQL 실행 계정. 관리자 계정으로 바꿔 쓰지 못하게 설정 이름을 열어 두지 않음
    db_user: str = "sql_retriever_user"
    audit_log_path: Path = PROJECT_ROOT / "logs" / "audit.jsonl"  # 사용자 승인 P-10


def load_settings(env_file: Path | None = None) -> Settings:
    """`.env` 파일과 환경변수를 합쳐 설정을 만듦. 같은 이름이면 환경변수가 이김.

    예외: 필수 이름(SQL_RETRIEVER_LLM_PROVIDER, SQL_RETRIEVER_LLM_MODEL, GROQ_API_KEY, RDB_PASSWORD)이
          없거나 비어 있으면 SettingsError를 발생시킴.
    부수효과: 없음. os.environ을 바꾸지 않음(dotenv_values는 값만 읽음).
    """
    path = env_file or Path(os.environ.get("SQL_RETRIEVER_ENV_FILE", DEFAULT_ENV_FILE))
    values: dict[str, str] = {
        key: value for key, value in dotenv_values(path).items() if value is not None
    } if path.exists() else {}
    values.update({key: value for key, value in os.environ.items() if value})

    def required(name: str) -> str:
        """비어 있으면 안 되는 설정값을 꺼냄."""
        value = values.get(name, "").strip()
        if not value:
            raise SettingsError(f"필수 설정 {name}이(가) 없습니다. secrets/.env에 등록해 주세요.")
        return value

    try:
        db_port = int(values.get("RDB_PORT", "5432"))
    except ValueError as error:
        raise SettingsError("RDB_PORT는 숫자여야 합니다.") from error

    audit_path = values.get("SQL_RETRIEVER_AUDIT_LOG")
    return Settings(
        llm_provider=required("SQL_RETRIEVER_LLM_PROVIDER").lower(),
        llm_model=required("SQL_RETRIEVER_LLM_MODEL"),
        groq_api_key=required("GROQ_API_KEY"),
        db_password=required("RDB_PASSWORD"),
        db_host=values.get("RDB_HOST", "localhost"),
        db_port=db_port,
        db_name=values.get("RDB_NAME", "cardlab"),
        audit_log_path=Path(audit_path) if audit_path else PROJECT_ROOT / "logs" / "audit.jsonl",
    )
