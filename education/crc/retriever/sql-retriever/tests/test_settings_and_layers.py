"""설정 읽기와 레이어드 아키텍처 규칙(가이드 §7 DIP 위반 신호)을 확인함. 값은 모두 가짜임."""

import ast
import inspect
from pathlib import Path

import pytest

from app.application import ports
from app.application.models import ERROR_CATALOG
from app.infrastructure.settings import Settings, SettingsError, load_settings

APP = Path(__file__).resolve().parents[1] / "app"
REQUIRED = {
    "SQL_RETRIEVER_LLM_PROVIDER": "groq",
    "SQL_RETRIEVER_LLM_MODEL": "openai/gpt-oss-120b",
    "GROQ_API_KEY": "fake-key",
    "RDB_PASSWORD": "fake-password",
}


@pytest.fixture
def clean_env(monkeypatch):
    for name in [*REQUIRED, "RDB_HOST", "RDB_PORT", "RDB_NAME", "SQL_RETRIEVER_AUDIT_LOG", "SQL_RETRIEVER_ENV_FILE"]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def write_env(tmp_path, values):
    path = tmp_path / ".env"
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    return path


def test_load_settings_from_env_file(clean_env, tmp_path):
    settings = load_settings(write_env(tmp_path, REQUIRED))
    assert settings.llm_provider == "groq"
    assert settings.llm_model == "openai/gpt-oss-120b"
    assert (settings.db_host, settings.db_port, settings.db_name, settings.db_user) == (
        "localhost", 5432, "cardlab", "sql_retriever_user",
    )


def test_secrets_are_hidden_from_repr(clean_env, tmp_path):
    text = repr(load_settings(write_env(tmp_path, REQUIRED)))
    assert "fake-key" not in text and "fake-password" not in text


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_missing_required_setting(clean_env, tmp_path, missing):
    values = {key: value for key, value in REQUIRED.items() if key != missing}
    with pytest.raises(SettingsError) as caught:
        load_settings(write_env(tmp_path, values))
    assert missing in str(caught.value)


def test_db_user_cannot_be_overridden(clean_env, tmp_path):
    clean_env.setenv("RDB_USER", "cardlab")
    assert load_settings(write_env(tmp_path, REQUIRED)).db_user == "sql_retriever_user"


def test_error_catalog_matches_design_table():
    """33장 오류 응답 표: 코드 8개, HTTP 상태, 다시 시도 여부."""
    expected = {
        "INVALID_REQUEST": (400, False), "MEMBER_NOT_FOUND": (404, False), "LLM_UNAVAILABLE": (503, True),
        "SQL_VALIDATION_FAILED": (422, False), "DB_TIMEOUT": (504, True), "DB_ERROR": (500, True),
        "TIME_BUDGET_EXCEEDED": (504, True), "INTERNAL_ERROR": (500, True),
    }
    assert {code: (spec.http_status, spec.retryable) for code, spec in ERROR_CATALOG.items()} == expected


# ---------------------------------------------------------------- DIP 위반 신호(가이드 §7)
FORBIDDEN_IN_INNER = ("psycopg", "langchain", "langgraph", "httpx", "requests", "openai", "groq", "sqlglot",
                      "fastapi", "dotenv")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(("." * node.level) + (node.module or ""))
    return names


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_inner_layers_import_no_external_technology(layer):
    for path in (APP / layer).glob("*.py"):
        for name in _imports(path):
            assert not name.split(".")[0] in FORBIDDEN_IN_INNER, f"{path.name}: {name}"
            assert "infrastructure" not in name and "presentation" not in name, f"{path.name}: {name}"


def test_domain_imports_only_standard_library():
    for path in (APP / "domain").glob("*.py"):
        for name in _imports(path):
            assert not name.startswith(".."), f"{path.name}: {name}"


def test_presentation_does_not_import_infrastructure():
    for path in (APP / "presentation").glob("*.py"):
        for name in _imports(path):
            assert "infrastructure" not in name, f"{path.name}: {name}"


def test_every_port_method_is_abstract():
    for _, port in inspect.getmembers(ports, inspect.isclass):
        if port.__module__ != ports.__name__:
            continue
        methods = [m for name, m in vars(port).items() if inspect.isfunction(m) and not name.startswith("_")]
        assert methods, port.__name__
        assert all(getattr(m, "__isabstractmethod__", False) for m in methods), port.__name__


def test_settings_is_frozen_dataclass():
    assert Settings.__dataclass_params__.frozen
