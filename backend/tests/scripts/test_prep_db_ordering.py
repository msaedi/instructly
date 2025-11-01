import sys

from scripts import prep_db, seed_data


def test_seed_all_orders_availability_before_reviews(monkeypatch):
    """Ensure seed-all runs migrations → future → backfill → reviews → credits → badges."""
    call_order = []

    def fake_run_migrations(db_url, dry_run, tool_cmd):
        call_order.append("migrate")

    def fake_future(*args, **kwargs):
        call_order.append("future")
        return {"weeks_requested": 4, "weeks_written": 4, "instructor_weeks": 10}

    def fake_backfill(*args, **kwargs):
        call_order.append("backfill")
        return {"days_requested": 56, "instructors_touched": 5, "days_backfilled": 25}

    def fake_seed_system_data(db_url, dry_run, mode, seed_db_url=None):
        call_order.append("system")

    class StubEngine:
        def dispose(self):
            call_order.append("engine_dispose")

    class StubSeeder:
        def __init__(self):
            self.engine = StubEngine()

        def create_sample_platform_credits(self):
            call_order.append("credits")
            return 2

        def print_summary(self):
            call_order.append("summary")

    def fake_seed_mock_phases(**kwargs):
        call_order.append("reviews")
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

    monkeypatch.setenv("STG_DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.delenv("SEED_AVAILABILITY_BITMAP", raising=False)
    monkeypatch.setenv("SEED_AVAILABILITY_BITMAP_WEEKS", "4")
    monkeypatch.setenv("BITMAP_BACKFILL_DAYS", "56")

    monkeypatch.setattr(sys, "argv", ["prep_db.py", "stg", "--migrate", "--seed-all"])

    prep_db.main()

    expected_sequence = ["migrate", "future", "backfill", "system", "reviews", "credits", "badges"]
    assert call_order[: len(expected_sequence)] == expected_sequence, f"Unexpected call order: {call_order}"
