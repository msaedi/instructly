from __future__ import annotations

import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import database_config


def _make_config(monkeypatch) -> database_config.DatabaseConfig:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://user:pass@localhost/test_db")
    monkeypatch.setenv("STG_DATABASE_URL", "postgresql://user:pass@localhost/stg_db")
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://user:pass@localhost/prod_db")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", "postgresql://user:pass@localhost/preview_db")
    monkeypatch.setenv("SUPPRESS_DB_MESSAGES", "1")
    monkeypatch.delenv("SITE_MODE", raising=False)
    return database_config.DatabaseConfig()


def test_getenv_prefers_upper_lower(monkeypatch) -> None:
    monkeypatch.setenv("FOO", "upper")
    monkeypatch.setenv("foo", "lower")

    assert database_config._getenv("FOO") == "upper"

    monkeypatch.delenv("FOO")
    assert database_config._getenv("FOO") == "lower"


def test_getenv_default(monkeypatch) -> None:
    monkeypatch.delenv("BAR", raising=False)

    assert database_config._getenv("BAR", default="fallback") == "fallback"


def test_coerce_safe_ci_db_url() -> None:
    url = "postgresql://user:pass@host/original"
    coerced = database_config.DatabaseConfig._coerce_safe_ci_db_url(url, safe_db="safe_db")

    assert coerced.endswith("/safe_db")


def test_is_test_db_name() -> None:
    assert database_config.DatabaseConfig._is_test_db_name("my_test_db") is True
    assert database_config.DatabaseConfig._is_test_db_name("prod") is False
    assert database_config.DatabaseConfig._is_test_db_name(None) is False


def test_mask_url(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    masked = cfg._mask_url("postgresql://user:pass@host/db")

    assert masked.startswith("postgresql://***:***@")

    assert cfg._mask_url("sqlite:///local.db") == "sqlite:///local.db"


def test_audit_log_operation_writes(monkeypatch, tmp_path: Path) -> None:
    cfg = _make_config(monkeypatch)
    cfg.audit_log_path = tmp_path / "audit.jsonl"

    cfg._audit_log_operation("unit_test", {"k": "v"})

    content = cfg.audit_log_path.read_text().strip()
    payload = json.loads(content)

    assert payload["operation"] == "unit_test"
    assert payload["details"] == {"k": "v"}


def test_get_safety_score(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    score = cfg.get_safety_score()

    assert "metrics" in score
    assert score["implemented_features"] > 0
    assert score["total_features"] >= score["implemented_features"]


def test_get_preview_url_errors_when_missing(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.preview_url = None

    with pytest.raises(ValueError):
        cfg._get_preview_url()


def test_get_production_url_in_production_mode(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.prod_url = "postgresql://user:pass@host/prod"
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: True)

    assert cfg._get_production_url() == cfg.prod_url


def test_is_ci_environment(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("CI", "true")

    assert cfg._is_ci_environment() is True


def test_get_database_url_site_mode_preview(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("SITE_MODE", "preview")

    assert cfg.get_database_url() == cfg.preview_url


def test_get_database_url_ci_coerces_non_test(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/prod")

    called = {}

    def _coerce(url: str) -> str:
        called["coerce"] = url
        return "postgresql://user:pass@host/instainstru_test"

    def _ensure(url: str) -> None:
        called["ensure"] = url

    monkeypatch.setattr(cfg, "_coerce_safe_ci_db_url", _coerce)
    monkeypatch.setattr(cfg, "_ensure_ci_database_exists", _ensure)

    assert cfg.get_database_url().endswith("/instainstru_test")
    assert called["coerce"].endswith("/prod")
    assert called["ensure"].endswith("/instainstru_test")


def test_validate_configuration_prod_missing(monkeypatch) -> None:
    dummy_settings = SimpleNamespace(
        int_database_url_raw="postgresql://user:pass@host/int",
        stg_database_url_raw="postgresql://user:pass@host/stg",
        prod_database_url_raw="",
        preview_database_url_raw="postgresql://user:pass@host/preview",
    )
    monkeypatch.setattr(database_config, "settings", dummy_settings)
    monkeypatch.setenv("SITE_MODE", "prod")
    for name in (
        "PROD_DATABASE_URL",
        "PRODUCTION_DATABASE_URL",
        "DATABASE_URL",
        "prod_database_url",
        "production_database_url",
        "database_url",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError):
        database_config.DatabaseConfig()


def test_validate_configuration_local_fallback(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.stg_url = None
    cfg.prod_url = "postgresql://user:pass@host/prod"
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(cfg, "_is_ci_environment", lambda: False)

    cfg.validate_configuration()


def test_get_production_url_non_interactive(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.prod_url = "postgresql://user:pass@host/prod"
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: False)
    monkeypatch.setattr(cfg, "_audit_log_operation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "_pre_production_checks", lambda: None)
    monkeypatch.setattr(cfg, "_post_production_approval", lambda: None)
    monkeypatch.setattr(cfg, "_mask_url", lambda value: value)
    monkeypatch.setattr(cfg, "_is_ci_environment", lambda: False)
    monkeypatch.setattr(database_config.sys.stdin, "isatty", lambda: False)

    with pytest.raises(RuntimeError):
        cfg._get_production_url()


def test_get_production_url_confirmation_yes(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.prod_url = "postgresql://user:pass@host/prod"
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: False)
    monkeypatch.setattr(cfg, "_audit_log_operation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "_pre_production_checks", lambda: None)
    monkeypatch.setattr(cfg, "_post_production_approval", lambda: None)
    monkeypatch.setattr(cfg, "_mask_url", lambda value: value)
    monkeypatch.setattr(database_config.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda *_args, **_kwargs: "yes")

    assert cfg._get_production_url() == cfg.prod_url


def test_is_local_development_detects_uvicorn(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setattr(database_config.sys, "argv", ["uvicorn", "app.main:app"])

    assert cfg._is_local_development() is True


def test_ensure_ci_database_exists_skips_unsafe_name(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)

    def _boom(*_args, **_kwargs):
        raise AssertionError("should not create engine")

    import sqlalchemy

    monkeypatch.setattr(sqlalchemy, "create_engine", _boom)

    cfg._ensure_ci_database_exists("postgresql://user:pass@host/db", safe_db="bad-name")


def test_ensure_ci_database_exists_creates(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    created = {"called": False}

    class DummyResult:
        def __init__(self, value):
            self._value = value

        def scalar(self):
            return self._value

    class DummyConnection:
        def __init__(self):
            self.statements = []

        def execute(self, statement, params=None):
            self.statements.append(str(statement))
            if "SELECT 1 FROM pg_database" in str(statement):
                return DummyResult(None)
            created["called"] = True
            return DummyResult(1)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class DummyEngine:
        def connect(self):
            return DummyConnection()

        def dispose(self):
            return None

    import sqlalchemy

    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *_args, **_kwargs: DummyEngine())

    cfg._ensure_ci_database_exists("postgresql://user:pass@host/db", safe_db="instainstru_test")
    assert created["called"] is True


def test_get_database_url_ci_uses_test_db(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/test_db")
    monkeypatch.setattr(cfg, "_audit_log_operation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "_mask_url", lambda value: value)

    assert cfg.get_database_url().endswith("/test_db")


def test_get_database_url_site_mode_prod_calls_production(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(cfg, "_get_production_url", lambda: "prod-url")

    assert cfg.get_database_url() == "prod-url"


def test_get_database_url_site_mode_int_calls_int(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("SITE_MODE", "int")
    monkeypatch.setattr(cfg, "_get_int_url", lambda: "int-url")

    assert cfg.get_database_url() == "int-url"


def test_get_database_url_site_mode_stg_calls_staging(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("SITE_MODE", "stg")
    monkeypatch.setattr(cfg, "_get_staging_url", lambda: "stg-url")

    assert cfg.get_database_url() == "stg-url"


def test_detect_environment_local_and_prod(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.delitem(database_config.sys.modules, "pytest", raising=False)
    monkeypatch.setattr(cfg, "_is_ci_environment", lambda: False)

    monkeypatch.setattr(cfg, "_is_local_development", lambda: True)
    assert cfg._detect_environment() == "stg"

    monkeypatch.setattr(cfg, "_is_local_development", lambda: False)
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: True)
    assert cfg._detect_environment() == "prod"


def test_get_int_url_missing(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.int_url = None

    with pytest.raises(ValueError):
        cfg._get_int_url()


def test_get_staging_url_missing(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.stg_url = None

    with pytest.raises(ValueError):
        cfg._get_staging_url()


def test_validate_configuration_preview_missing(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.preview_url = None
    monkeypatch.setenv("SITE_MODE", "preview")

    with pytest.raises(ValueError):
        cfg.validate_configuration()


def test_validate_configuration_fallback_prod_missing(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.prod_url = ""
    monkeypatch.delenv("SITE_MODE", raising=False)
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: True)

    with pytest.raises(ValueError):
        cfg.validate_configuration()


def test_validate_configuration_fallback_int_missing(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.int_url = None
    monkeypatch.delenv("SITE_MODE", raising=False)
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: False)

    with pytest.raises(ValueError):
        cfg.validate_configuration()


def test_coerce_safe_ci_db_url_invalid() -> None:
    url = "not-a-url"
    assert database_config.DatabaseConfig._coerce_safe_ci_db_url(url) == url


def test_ensure_ci_database_exists_handles_exception(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)

    import sqlalchemy

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(sqlalchemy, "create_engine", _boom)
    cfg._ensure_ci_database_exists("postgresql://user:pass@host/db")


def test_get_production_url_user_cancel(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.prod_url = "postgresql://user:pass@host/prod"
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: False)
    monkeypatch.setattr(cfg, "_audit_log_operation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cfg, "_pre_production_checks", lambda: None)
    monkeypatch.setattr(cfg, "_post_production_approval", lambda: None)
    monkeypatch.setattr(cfg, "_mask_url", lambda value: value)
    monkeypatch.setattr(database_config.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda *_args, **_kwargs: "no")

    with pytest.raises(SystemExit):
        cfg._get_production_url()


def test_audit_log_operation_failure(monkeypatch, tmp_path: Path) -> None:
    cfg = _make_config(monkeypatch)
    cfg.audit_log_path = tmp_path

    cfg._audit_log_operation("unit_test", {"k": "v"})


def test_extension_points_defaults(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    assert cfg._pre_production_checks() is None
    assert cfg._post_production_approval() is None
    assert cfg._create_backup_if_needed("op") is None
    assert cfg._validate_schema_version() is False
    assert cfg._check_dry_run_mode() is False
    assert cfg._rate_limit_check("op") is False


def test_get_database_url_unknown_site_mode_uses_detected_staging(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("SITE_MODE", "sandbox")
    monkeypatch.setattr(cfg, "_detect_environment", lambda: "stg")
    monkeypatch.setattr(cfg, "_get_staging_url", lambda: "stg-url")

    assert cfg.get_database_url() == "stg-url"


def test_get_database_url_unknown_site_mode_defaults_to_int(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("SITE_MODE", "sandbox")
    monkeypatch.setattr(cfg, "_detect_environment", lambda: "prod")
    monkeypatch.setattr(cfg, "_get_int_url", lambda: "int-url")

    assert cfg.get_database_url() == "int-url"


def test_get_database_url_ci_without_database_url_falls_back_to_site_mode(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setattr(cfg, "_get_staging_url", lambda: "stg-url")

    assert cfg.get_database_url() == "stg-url"


def test_detect_environment_returns_int_when_pytest_present(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    monkeypatch.setitem(database_config.sys.modules, "pytest", object())
    monkeypatch.setattr(cfg, "_is_ci_environment", lambda: False)
    monkeypatch.setattr(cfg, "_is_local_development", lambda: False)
    monkeypatch.setattr(cfg, "_check_production_mode", lambda: True)

    assert cfg._detect_environment() == "int"


def test_validate_configuration_stg_mode_requires_stg_or_prod(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.stg_url = None
    cfg.prod_url = ""
    monkeypatch.setenv("SITE_MODE", "stg")

    with pytest.raises(ValueError, match="STG database"):
        cfg.validate_configuration()


def test_validate_configuration_int_mode_requires_int_url(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    cfg.int_url = None
    monkeypatch.setenv("SITE_MODE", "int")

    with pytest.raises(ValueError, match="INT database"):
        cfg.validate_configuration()


def test_staging_and_preview_url_emit_banner_and_audit(monkeypatch) -> None:
    cfg = _make_config(monkeypatch)
    logged: list[tuple[str, str]] = []
    audited: list[tuple[str, dict[str, object]]] = []
    database_config._PRINTED_ENV_BANNERS.clear()

    monkeypatch.setattr(
        database_config, "scripts_log_info", lambda env, message: logged.append((env, message))
    )
    monkeypatch.setattr(
        cfg, "_audit_log_operation", lambda operation, details: audited.append((operation, details))
    )

    assert cfg._get_staging_url() == cfg.stg_url
    assert cfg._get_preview_url() == cfg.preview_url

    assert ("stg", "Using Staging/Local Dev database (preserves data)") in logged
    assert ("preview", "Using Preview database") in logged
    assert "stg" in database_config._PRINTED_ENV_BANNERS
    assert "preview" in database_config._PRINTED_ENV_BANNERS
    assert any(item[1]["environment"] == "stg" for item in audited)
    assert any(item[1]["environment"] == "preview" for item in audited)
