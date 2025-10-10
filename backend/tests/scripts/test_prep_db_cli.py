import sys
import types

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

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def beta_record(session):
        calls.append(("beta_seed", (session,), {}))
        return 0, 0

    dummy_db_module = types.SimpleNamespace(SessionLocal=lambda: DummySession())
    dummy_seed_module = types.SimpleNamespace(seed_beta_access_for_instructors=beta_record)
    monkeypatch.setitem(sys.modules, "app.database", dummy_db_module)
    monkeypatch.setitem(sys.modules, "scripts.seed_data", dummy_seed_module)
    monkeypatch.setattr(sys, "argv", ["prep_db.py", *args])
    prep_db.main()
    return calls


def test_prod_seed_all_default_skips_mock(monkeypatch):
    calls = _execute(monkeypatch, ["prod", "--seed-all", "--force", "--yes"])
    tags = [tag for tag, *_ in calls]
    assert "seed_system" in tags
    assert "seed_mock" not in tags
    assert "beta_seed" not in tags


def test_prod_seed_all_prod_invokes_mock(monkeypatch):
    monkeypatch.setenv("PROD_SERVICE_DATABASE_URL", "postgresql://service:pass@localhost:5432/prod_db_service")
    calls = _execute(monkeypatch, ["prod", "--seed-all-prod", "--force", "--yes"])
    tags = [tag for tag, *_ in calls]
    assert "seed_system" in tags
    assert "seed_mock" in tags
    assert "beta_seed" in tags
    # Ensure service DSN propagated
    seed_mock_call = next(entry for entry in calls if entry[0] == "seed_mock")
    kwargs = seed_mock_call[2]
    assert kwargs.get("seed_db_url") == "postgresql://service:pass@localhost:5432/prod_db_service"


def test_beta_access_not_seeded_without_flag(monkeypatch):
    calls = _execute(monkeypatch, ["prod", "--seed-system-only", "--force", "--yes"])
    tags = [tag for tag, *_ in calls]
    assert "beta_seed" not in tags
