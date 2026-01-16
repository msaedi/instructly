from __future__ import annotations

import json
from pathlib import Path

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
