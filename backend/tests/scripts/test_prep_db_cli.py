import sys

import pytest
import scripts.prep_db as prep_db


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL_PROD", raising=False)
    monkeypatch.delenv("PROD_DATABASE_URL", raising=False)
    monkeypatch.delenv("PROD_SERVICE_DATABASE_URL", raising=False)
    monkeypatch.delenv("SITE_MODE", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://user:pass@localhost:5432/prod_db")
    monkeypatch.setenv("ADMIN_PASSWORD", "Test1234!")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")


def _execute(monkeypatch, args):
    calls = []

    def record(tag):
        def wrapper(*spawn_args, **kwargs):
            calls.append((tag, spawn_args, kwargs))
        return wrapper

    monkeypatch.setattr(prep_db, "run_migrations", record("migrate"))
    monkeypatch.setattr(prep_db, "seed_system_data", record("seed_system"))
    monkeypatch.setattr(prep_db, "seed_mock_users", record("seed_mock"))
    monkeypatch.setattr(prep_db, "generate_embeddings", record("embeddings"))
    monkeypatch.setattr(prep_db, "calculate_analytics", record("analytics"))
    monkeypatch.setattr(prep_db, "clear_cache", record("cache"))
    monkeypatch.setattr(sys, "argv", ["prep_db.py", *args])
    prep_db.main()
    return calls


def test_prod_seed_all_default_skips_mock(monkeypatch):
    calls = _execute(monkeypatch, ["prod", "--seed-all", "--force", "--yes"])
    tags = [tag for tag, *_ in calls]
    assert "seed_system" in tags
    assert "seed_mock" not in tags


def test_prod_seed_all_prod_invokes_mock(monkeypatch):
    monkeypatch.setenv("PROD_SERVICE_DATABASE_URL", "postgresql://service:pass@localhost:5432/prod_db_service")
    calls = _execute(monkeypatch, ["prod", "--seed-all-prod", "--force", "--yes"])
    tags = [tag for tag, *_ in calls]
    assert "seed_system" in tags
    assert "seed_mock" in tags
    # Ensure service DSN propagated
    seed_mock_call = next(entry for entry in calls if entry[0] == "seed_mock")
    kwargs = seed_mock_call[2]
    assert kwargs.get("seed_db_url") == "postgresql://service:pass@localhost:5432/prod_db_service"
