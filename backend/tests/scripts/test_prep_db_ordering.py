import sys
import types

from scripts import prep_db, seed_data


def test_seed_all_orders_availability_before_reviews(monkeypatch):
    """Ensure seed-all runs migrations → future → backfill → reviews → credits → badges."""
    call_order = []
    system_logged = False
    future_logged = False
    backfill_logged = False

    def fake_run_migrations(db_url, dry_run, tool_cmd):
        call_order.append("migrate")

    def fake_future(*args, **kwargs):
        nonlocal future_logged
        if not future_logged:
            call_order.append("future")
            future_logged = True
        return {"weeks_requested": 4, "weeks_written": 4, "instructor_weeks": 10}

    def fake_backfill(*args, **kwargs):
        nonlocal backfill_logged, system_logged
        if not backfill_logged:
            call_order.append("backfill")
            backfill_logged = True
        if system_logged:
            call_order.append("system")
            system_logged = False
        return {"days_requested": 56, "instructors_touched": 5, "days_backfilled": 25}

    def fake_seed_system_data(db_url, dry_run, mode, seed_db_url=None):
        nonlocal system_logged
        system_logged = True

    class StubSeeder:
        def __init__(self):
            self.engine = types.SimpleNamespace(dispose=lambda: None)
            self.loader = types.SimpleNamespace(get_students=lambda: ["student"], get_instructors=lambda: ["instructor"])
            self._reviews_logged = False

        def reset_database(self):
            return None

        def create_instructors(self, seed_tier_maintenance=True):
            return 0

        def seed_tier_maintenance_sessions(self, reason=""):
            return 0

        def create_students(self):
            return 0

        def create_availability(self):
            return 0

        def create_coverage_areas(self):
            return 0

        def create_bookings(self):
            return 0

        def create_reviews(self, strict=False):
            if not self._reviews_logged:
                call_order.append("reviews")
                self._reviews_logged = True
            return 0

        def create_sample_platform_credits(self):
            call_order.append("credits")
            return 2

        def print_summary(self):
            call_order.append("summary")

    def fake_seed_mock_phases(**kwargs):
        return StubSeeder(), {
            "students_seeded": 20,
            "instructors_seeded": 10,
            "bookings_created": 12,
            "reviews_created": 8,
            "reviews_skipped": False,
            "credits_created": 0,
            "badges_awarded": 0,
        }

    def fake_seed_demo_badges(engine, verbose=True):
        call_order.append("badges")
        return 5

    def fake_probe(db_url, lookback, horizon):
        return {
            "total_rows": 10,
            "sample": [{"instructor_id": "ABCDEF", "rows": 3}],
            "lookback_days": lookback,
            "horizon_days": horizon,
            "instructor_count": 1,
        }

    def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(prep_db, "run_migrations", fake_run_migrations)
    monkeypatch.setattr(prep_db, "_run_future_bitmap_seeding", fake_future)
    monkeypatch.setattr(prep_db, "_run_bitmap_backfill", fake_backfill)
    monkeypatch.setattr(prep_db, "seed_system_data", fake_seed_system_data)
    monkeypatch.setattr(prep_db, "probe_bitmap_coverage", fake_probe)
    monkeypatch.setattr(seed_data, "seed_mock_data_phases", fake_seed_mock_phases)
    monkeypatch.setattr(seed_data, "seed_demo_student_badges", fake_seed_demo_badges)
    monkeypatch.setattr(prep_db, "generate_embeddings", noop)
    monkeypatch.setattr(prep_db, "calculate_analytics", noop)
    monkeypatch.setattr(prep_db, "clear_cache", noop)
    monkeypatch.setitem(sys.modules, "scripts.reset_and_seed_yaml", types.SimpleNamespace(DatabaseSeeder=StubSeeder))

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

    monkeypatch.setenv("STG_DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.delenv("SEED_AVAILABILITY", raising=False)
    monkeypatch.setenv("SEED_AVAILABILITY_WEEKS", "4")
    monkeypatch.setenv("BITMAP_BACKFILL_DAYS", "56")

    monkeypatch.setattr(sys, "argv", ["prep_db.py", "stg", "--migrate", "--seed-all"])

    prep_db.main()

    expected_sequence = ["migrate", "future", "backfill", "system", "reviews", "credits", "badges"]
    assert call_order[: len(expected_sequence)] == expected_sequence, f"Unexpected call order: {call_order}"


def test_seed_all_uses_student_counts(monkeypatch):
    logs = []
    monkeypatch.setattr(prep_db, "info", lambda tag, msg: logs.append(msg))

    student_counts = iter([1, 4])

    def fake_run_migrations(db_url, dry_run, tool_cmd):
        return None

    monkeypatch.setattr(prep_db, "run_migrations", fake_run_migrations)
    monkeypatch.setattr(
        prep_db,
        "_run_future_bitmap_seeding",
        lambda *args, **kwargs: {"weeks_requested": 4, "weeks_written": 4, "instructor_weeks": 5},
    )
    monkeypatch.setattr(
        prep_db,
        "_run_bitmap_backfill",
        lambda *args, **kwargs: {"days_requested": 10, "instructors_touched": 2, "days_backfilled": 10},
    )
    monkeypatch.setattr(prep_db, "seed_system_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        prep_db,
        "probe_bitmap_coverage",
        lambda *args, **kwargs: {
            "total_rows": 3,
            "sample": [],
            "lookback_days": 90,
            "horizon_days": 21,
            "instructor_count": 1,
        },
    )
    monkeypatch.setattr(prep_db, "count_instructors", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(prep_db, "count_mock_students", lambda *_args, **_kwargs: next(student_counts))
    monkeypatch.setattr(prep_db, "seed_chat_fixture_booking", lambda **_kwargs: "skipped-existing")

    class StudentSeeder:
        def __init__(self):
            self.engine = types.SimpleNamespace(dispose=lambda: None)
            self.loader = types.SimpleNamespace(
                get_students=lambda: ["s1", "s2", "s3"],
                get_instructors=lambda: ["i1"],
            )

        def reset_database(self):
            return None

        def create_instructors(self, seed_tier_maintenance=False):
            return None

        def create_students(self):
            return None

        def create_availability(self):
            return None

        def create_coverage_areas(self):
            return None

        def create_bookings(self):
            return 0

        def create_reviews(self, strict=False):
            return 0

        def seed_tier_maintenance_sessions(self, reason=""):
            return 0

        def create_sample_platform_credits(self):
            return 0

        def print_summary(self):
            return None

    monkeypatch.setitem(
        sys.modules,
        "scripts.reset_and_seed_yaml",
        types.SimpleNamespace(DatabaseSeeder=StudentSeeder),
    )
    monkeypatch.setitem(sys.modules, "scripts.seed_data", types.SimpleNamespace(seed_demo_student_badges=lambda *args, **kwargs: 0))
    monkeypatch.setattr(prep_db, "generate_embeddings", lambda *args, **kwargs: None)
    monkeypatch.setattr(prep_db, "calculate_analytics", lambda *args, **kwargs: None)
    monkeypatch.setattr(prep_db, "clear_cache", lambda *args, **kwargs: None)

    stats = prep_db.run_seed_all_pipeline(
        mode="stg",
        db_url="postgresql://user:pass@localhost/db",
        seed_db_url="postgresql://user:pass@localhost/db",
        migrate=True,
        dry_run=False,
        env_snapshot=prep_db.build_env_snapshot("stg"),
        include_mock_users=True,
    )

    assert stats["students_seeded"] == 4
    student_log = next(msg for msg in logs if "Mock students defined=" in msg)
    assert "defined=3" in student_log
    assert "total_now=4" in student_log
