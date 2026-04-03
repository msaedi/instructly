import builtins
from unittest.mock import patch

import pytest

from app.utils import database_safety


def test_int_hosted_database_aborts() -> None:
    with pytest.raises(SystemExit, match="Target is 'int' but resolved URL points to a hosted database"):
        database_safety.check_hosted_database(
            "int",
            "postgresql://user:pass@db.project.supabase.com:5432/postgres",
        )


def test_stg_hosted_database_warns(monkeypatch) -> None:
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(database_safety, "log_warn", lambda env, message: warnings.append((env, message)))

    database_safety.check_hosted_database(
        "stg",
        "postgresql://user:pass@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
    )

    assert warnings == [("stg", "Hosted database target detected: aws-0-us-east-1.pooler.supabase.com")]


def test_prod_hosted_database_requires_tty(monkeypatch) -> None:
    monkeypatch.setattr(database_safety.sys.stdin, "isatty", lambda: False)

    with pytest.raises(SystemExit, match="stdin is not a TTY"):
        database_safety.check_hosted_database(
            "prod",
            "postgresql://user:pass@db.project.supabase.com:5432/postgres",
        )


def test_prod_hosted_database_requires_exact_hostname(monkeypatch) -> None:
    monkeypatch.setattr(database_safety.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        builtins,
        "input",
        lambda *_args, **_kwargs: "db.project.supabase.com",
    )

    database_safety.check_hosted_database(
        "prod",
        "postgresql://user:pass@db.project.supabase.com:5432/postgres",
    )


def test_prod_hosted_database_rejects_bad_hostname(monkeypatch) -> None:
    monkeypatch.setattr(database_safety.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda *_args, **_kwargs: "wrong-host")

    with pytest.raises(SystemExit, match="Hostname confirmation failed"):
        database_safety.check_hosted_database(
            "prod",
            "postgresql://user:pass@db.project.supabase.com:5432/postgres",
        )


def test_default_database_selection_is_int(monkeypatch) -> None:
    monkeypatch.delenv("SITE_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.core.database_config import DatabaseConfig

    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
        assert "instainstru_test" in DatabaseConfig().get_database_url()


def test_local_site_mode_uses_staging_database(monkeypatch) -> None:
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setenv("STG_DATABASE_URL", "postgresql://user:pass@localhost:5432/instainstru_stg")

    from app.core.database_config import DatabaseConfig

    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
        assert DatabaseConfig().get_database_url().endswith("/instainstru_stg")


def test_db_confirm_bypass_allows_prod_access(monkeypatch) -> None:
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setenv("DB_CONFIRM_BYPASS", "1")
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/instainstru_prod")
    from app.core.database_config import DatabaseConfig

    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
        assert DatabaseConfig().get_database_url().endswith("/instainstru_prod")


def test_prod_requires_confirmation_without_bypass(monkeypatch) -> None:
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/instainstru_prod")
    monkeypatch.delenv("DB_CONFIRM_BYPASS", raising=False)
    from app.core.database_config import DatabaseConfig

    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
        with pytest.raises(RuntimeError, match="non-interactive mode"):
            DatabaseConfig().get_database_url()


def test_ci_uses_provided_test_database(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/ci_test_db")

    from app.core.database_config import DatabaseConfig

    assert DatabaseConfig().get_database_url().endswith("/ci_test_db")


def test_ci_without_database_url_uses_int_database(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    for var in [
        "DATABASE_URL",
        "database_url",
        "STG_DATABASE_URL",
        "STAGING_DATABASE_URL",
        "stg_database_url",
        "LOCAL_DATABASE_URL",
        "local_database_url",
        "PREVIEW_DATABASE_URL",
        "preview_database_url",
        "PROD_DATABASE_URL",
        "PRODUCTION_DATABASE_URL",
        "prod_database_url",
        "test_database_url",
        "SITE_MODE",
        "FRONTEND_URL",
        "ENVIRONMENT",
    ]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/instainstru_test",
    )

    from app.core.database_config import DatabaseConfig

    assert "instainstru_test" in DatabaseConfig().get_database_url()
