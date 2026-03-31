import os
import sys

import pytest
import scripts.reset_schema as reset_schema


def test_help_exits_cleanly(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["reset_schema.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        reset_schema.main()

    assert exc.value.code == 0
    assert "Usage: python scripts/reset_schema.py" in capsys.readouterr().out


def test_ci_guard_blocks_non_int(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(sys, "argv", ["reset_schema.py", "prod"])

    with pytest.raises(SystemExit, match="ERROR: Non-INT environment not allowed in CI. Aborting."):
        reset_schema.main()


def test_ci_dry_run_allows_non_int(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://user:pass@db.project.supabase.com:5432/postgres")
    monkeypatch.setattr(sys, "argv", ["reset_schema.py", "prod", "--dry-run"])
    monkeypatch.setattr(
        reset_schema.DatabaseConfig,
        "get_database_url",
        lambda self: "postgresql://user:pass@db.project.supabase.com:5432/postgres",
    )

    with pytest.raises(SystemExit) as exc:
        reset_schema.main()

    assert exc.value.code == 0


def test_preview_requires_explicit_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/wrong_db")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_URL_PREVIEW", "postgresql://user:pass@localhost:5432/preview_alias_db")
    monkeypatch.setenv("preview_database_url", "postgresql://user:pass@localhost:5432/preview_alias_db")

    with pytest.raises(
        SystemExit,
        match=(
            "ERROR: PREVIEW_DATABASE_URL is not set. Cannot target 'preview' without an explicit "
            "database URL. Generic DATABASE_URL fallback is not allowed for non-INT modes."
        ),
    ):
        reset_schema.resolve_db_url("preview")

    assert "DATABASE_URL" not in os.environ


def test_preview_resolution_clears_generic_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/wrong_db")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", "postgresql://user:pass@localhost:5432/preview_db")

    captured = {}

    class DummyDatabaseConfig:
        def get_database_url(self):
            captured["database_url"] = os.environ.get("DATABASE_URL")
            captured["preview_database_url"] = os.environ.get("PREVIEW_DATABASE_URL")
            return os.environ["PREVIEW_DATABASE_URL"]

    monkeypatch.setattr(reset_schema, "DatabaseConfig", DummyDatabaseConfig)

    assert reset_schema.resolve_db_url("preview") == "postgresql://user:pass@localhost:5432/preview_db"
    assert captured == {
        "database_url": None,
        "preview_database_url": "postgresql://user:pass@localhost:5432/preview_db",
    }


def test_int_hosted_database_misconfiguration_aborts(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["reset_schema.py", "int", "--dry-run"])
    monkeypatch.setattr(
        reset_schema.DatabaseConfig,
        "get_database_url",
        lambda self: "postgresql://user:pass@db.project.supabase.com:5432/postgres",
    )

    with pytest.raises(SystemExit, match="Target is 'int' but resolved URL points to a hosted database"):
        reset_schema.main()
