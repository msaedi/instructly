import os
import sys
import types

import pytest
import scripts.prep_db as prep_db


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("database_url", raising=False)
    monkeypatch.delenv("DATABASE_URL_PROD", raising=False)
    monkeypatch.delenv("PROD_DATABASE_URL", raising=False)
    monkeypatch.delenv("PRODUCTION_DATABASE_URL", raising=False)
    monkeypatch.delenv("prod_database_url", raising=False)
    monkeypatch.delenv("PREVIEW_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_PREVIEW", raising=False)
    monkeypatch.delenv("preview_database_url", raising=False)
    monkeypatch.delenv("STG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_STG", raising=False)
    monkeypatch.delenv("LOCAL_DATABASE_URL", raising=False)
    monkeypatch.delenv("local_database_url", raising=False)
    monkeypatch.delenv("stg_database_url", raising=False)
    monkeypatch.delenv("DB_CONFIRM_BYPASS", raising=False)
    monkeypatch.delenv("SITE_MODE", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://user:pass@localhost:5432/prod_db")
    monkeypatch.setenv("PREVIEW_DATABASE_URL", "postgresql://user:pass@localhost:5432/preview_db")
    monkeypatch.setenv("STG_DATABASE_URL", "postgresql://user:pass@localhost:5432/stg_db")
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

    class DummyDatabaseConfig:
        def get_database_url(self):
            site_mode = (os.environ.get("SITE_MODE") or "").strip().lower()
            if site_mode == "prod":
                return os.environ.get("PROD_DATABASE_URL", "")
            if site_mode == "preview":
                return os.environ.get("PREVIEW_DATABASE_URL", "")
            if site_mode in {"local", "stg", "stage", "staging"}:
                return os.environ.get("STG_DATABASE_URL") or os.environ.get("LOCAL_DATABASE_URL", "")
            return os.environ.get("TEST_DATABASE_URL", "postgresql://user:pass@localhost:5432/instainstru_test")

    monkeypatch.setattr(prep_db, "DatabaseConfig", DummyDatabaseConfig)

    class DummyResult:
        def fetchall(self):
            return []

        def scalar(self):
            return 0

    class DummyConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            return DummyResult()

    class DummyEngine:
        def connect(self):
            return DummyConnection()

        def dispose(self):
            return None

    monkeypatch.setattr(prep_db, "create_engine", lambda *_args, **_kwargs: DummyEngine())

    class DummyQuery:
        def join(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def count(self):
            return 0

        def all(self):
            return []

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def rollback(self):
            return None

        def commit(self):
            return None

        def query(self, *args, **kwargs):
            return DummyQuery()

    def beta_record(session):
        calls.append(("beta_seed", (session,), {}))
        return 0, 0

    class DummySeeder:
        def __init__(self):
            self.engine = DummyEngine()
            self.loader = types.SimpleNamespace(
                get_students=lambda: [],
                get_instructors=lambda: [],
            )
            self._seed_mock_logged = False

        def reset_database(self):
            calls.append(("reset_database", (), {}))

        def create_instructors(self, seed_tier_maintenance=True):
            calls.append(("create_instructors", (), {"seed_tier_maintenance": seed_tier_maintenance}))
            return 0

        def seed_tier_maintenance_sessions(self, reason=""):
            calls.append(("seed_tier_maintenance", (), {"reason": reason}))
            return 0

        def create_students(self):
            calls.append(("create_students", (), {}))
            return 0

        def create_availability(self):
            calls.append(("create_availability", (), {}))
            return 0

        def create_coverage_areas(self):
            calls.append(("create_coverage_areas", (), {}))
            return 0

        def create_bookings(self):
            calls.append(("create_bookings", (), {}))
            return 0

        def create_reviews(self, strict=False):
            calls.append(("create_reviews", (strict,), {}))
            return 0

        def create_sample_platform_credits(self):
            calls.append(("create_credits", (), {}))
            return 0

        def print_summary(self):
            calls.append(("print_summary", (), {}))

    dummy_db_module = types.SimpleNamespace(SessionLocal=lambda: DummySession())
    dummy_seed_module = types.SimpleNamespace(
        seed_beta_access_for_instructors=beta_record,
        seed_demo_student_badges=lambda engine, verbose=True: 0,
    )
    dummy_reset_seed = types.SimpleNamespace(DatabaseSeeder=DummySeeder)
    monkeypatch.setitem(sys.modules, "app.database", dummy_db_module)
    monkeypatch.setitem(sys.modules, "scripts.seed_data", dummy_seed_module)
    monkeypatch.setitem(sys.modules, "scripts.reset_and_seed_yaml", dummy_reset_seed)
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
    calls = _execute(monkeypatch, ["prod", "--seed-all-prod", "--force", "--yes"])
    tags = [tag for tag, *_ in calls]
    assert "seed_system" in tags
    assert "create_students" in tags
    assert "beta_seed" in tags


def test_ci_guard_blocks_non_int(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(sys, "argv", ["prep_db.py", "prod"])

    with pytest.raises(SystemExit, match="ERROR: Non-INT environment not allowed in CI. Aborting."):
        prep_db.main()


def test_ci_dry_run_allows_non_int(monkeypatch):
    monkeypatch.setenv("CI", "true")

    calls = _execute(monkeypatch, ["preview", "--migrate", "--dry-run"])

    assert [tag for tag, *_ in calls] == ["migrate", "embeddings", "analytics", "cache"]


def test_ci_dry_run_allows_prod_with_hosted_url(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv(
        "PROD_DATABASE_URL",
        "postgresql://user:pass@db.project.supabase.com:5432/postgres",
    )

    calls = _execute(monkeypatch, ["prod", "--migrate", "--dry-run"])

    assert [tag for tag, *_ in calls] == ["migrate", "embeddings", "analytics", "cache"]


def test_database_url_prod_alias_is_promoted_for_database_config(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_PROD", "postgresql://user:pass@localhost:5432/prod_alias_db")
    monkeypatch.delenv("PROD_DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_CONFIRM_BYPASS", "1")

    captured = {}

    class DummyDatabaseConfig:
        def get_database_url(self):
            captured["site_mode"] = os.environ.get("SITE_MODE")
            captured["prod_database_url"] = os.environ.get("PROD_DATABASE_URL")
            captured["db_confirm_bypass"] = os.environ.get("DB_CONFIRM_BYPASS")
            return os.environ["PROD_DATABASE_URL"]

    monkeypatch.setattr(prep_db, "DatabaseConfig", DummyDatabaseConfig)

    assert prep_db.get_database_url_for_mode("prod") == "postgresql://user:pass@localhost:5432/prod_alias_db"
    assert captured == {
        "site_mode": "prod",
        "prod_database_url": "postgresql://user:pass@localhost:5432/prod_alias_db",
        "db_confirm_bypass": None,
    }


def test_preview_requires_explicit_database_url(monkeypatch):
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
        prep_db.get_database_url_for_mode("preview")

    assert os.environ.get("DATABASE_URL") is None


def test_preview_resolution_clears_generic_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/wrong_db")
    captured = {}

    class DummyDatabaseConfig:
        def get_database_url(self):
            captured["database_url"] = os.environ.get("DATABASE_URL")
            captured["preview_database_url"] = os.environ.get("PREVIEW_DATABASE_URL")
            return os.environ["PREVIEW_DATABASE_URL"]

    monkeypatch.setattr(prep_db, "DatabaseConfig", DummyDatabaseConfig)

    assert prep_db.get_database_url_for_mode("preview") == "postgresql://user:pass@localhost:5432/preview_db"
    assert captured == {
        "database_url": None,
        "preview_database_url": "postgresql://user:pass@localhost:5432/preview_db",
    }


def test_database_url_prod_ci_dry_run_grants_temporary_bypass(monkeypatch):
    monkeypatch.setenv("PROD_DATABASE_URL", "postgresql://user:pass@localhost:5432/prod_db")
    monkeypatch.delenv("DB_CONFIRM_BYPASS", raising=False)

    captured = {}

    class DummyDatabaseConfig:
        def get_database_url(self):
            captured["db_confirm_bypass"] = os.environ.get("DB_CONFIRM_BYPASS")
            return os.environ["PROD_DATABASE_URL"]

    monkeypatch.setattr(prep_db, "DatabaseConfig", DummyDatabaseConfig)

    assert (
        prep_db.get_database_url_for_mode("prod", allow_prod_bypass=True)
        == "postgresql://user:pass@localhost:5432/prod_db"
    )
    assert captured["db_confirm_bypass"] == "1"
    assert os.environ.get("DB_CONFIRM_BYPASS") is None


def test_beta_access_not_seeded_without_flag(monkeypatch):
    calls = _execute(monkeypatch, ["prod", "--seed-system-only", "--force", "--yes"])
    tags = [tag for tag, *_ in calls]
    assert "beta_seed" not in tags
