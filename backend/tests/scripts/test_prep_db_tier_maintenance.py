import sys
import types

import scripts.prep_db as prep_db


def test_seed_all_seeds_tier_maintenance_after_students(monkeypatch, capsys):
    """Ensure tier maintenance seeding runs after mock students exist."""

    created_seeders: list["TierAwareSeeder"] = []

    class TierAwareSeeder:
        def __init__(self):
            self.engine = types.SimpleNamespace(dispose=lambda: None)
            self.loader = types.SimpleNamespace(
                get_students=lambda: ["student@example.com"],
                get_instructors=lambda: ["inst@example.com"],
            )
            self.students_seeded = 0
            self.tier_logs: list[str] = []
            created_seeders.append(self)

        def reset_database(self):
            return None

        def create_instructors(self, seed_tier_maintenance=True):
            if seed_tier_maintenance:
                self.tier_logs.append("tier-called-before-students")
            return 0

        def create_students(self):
            self.students_seeded += 1
            return 1

        def create_availability(self):
            return 0

        def create_coverage_areas(self):
            return 0

        def create_bookings(self):
            return 0

        def create_reviews(self, strict=False):
            return 0

        def create_sample_platform_credits(self):
            return 0

        def seed_tier_maintenance_sessions(self, reason=""):
            if not self.students_seeded:
                msg = "  ⚠️  Skipping tier maintenance seeding: no seed students available"
                self.tier_logs.append(msg)
                print(msg)
                return 0
            msg = "  🎯 Seeded tier maintenance sessions (stub)"
            self.tier_logs.append(msg)
            print(msg)
            return 2

        def print_summary(self):
            return None

    tier_module = types.SimpleNamespace(DatabaseSeeder=TierAwareSeeder)
    monkeypatch.setitem(sys.modules, "scripts.reset_and_seed_yaml", tier_module)

    seed_data_module = types.ModuleType("scripts.seed_data")
    seed_data_module.seed_demo_student_badges = lambda *args, **kwargs: 0
    monkeypatch.setitem(sys.modules, "scripts.seed_data", seed_data_module)

    monkeypatch.setenv("SEED_AVAILABILITY", "1")
    monkeypatch.setenv("SEED_CHAT_FIXTURE", "0")
    monkeypatch.setenv("INCLUDE_MOCK_USERS", "1")

    student_counts = iter([0, 1])

    monkeypatch.setattr(prep_db, "seed_system_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(prep_db, "count_mock_students", lambda *_args, **_kwargs: next(student_counts))
    monkeypatch.setattr(prep_db, "count_instructors", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(
        prep_db,
        "_run_future_bitmap_seeding",
        lambda *args, **kwargs: {"weeks_requested": 4, "weeks_written": 4, "instructor_weeks": 4},
    )
    monkeypatch.setattr(
        prep_db,
        "_run_bitmap_backfill",
        lambda *args, **kwargs: {"days_requested": 14, "days_backfilled": 14, "instructors_touched": 2},
    )
    monkeypatch.setattr(
        prep_db,
        "probe_bitmap_coverage",
        lambda *args, **kwargs: {
            "total_rows": 5,
            "sample": [],
            "instructor_count": 1,
            "lookback_days": 90,
            "horizon_days": 21,
        },
    )

    stats = prep_db.run_seed_all_pipeline(
        mode="int",
        db_url="postgresql://user:pass@localhost/db",
        seed_db_url="postgresql://user:pass@localhost/db",
        migrate=False,
        dry_run=False,
        env_snapshot=prep_db.build_env_snapshot("int"),
        include_mock_users=True,
    )

    output = capsys.readouterr().out
    assert "Skipping tier maintenance seeding: no seed students available" not in output

    assert created_seeders, "expected stub DatabaseSeeder to be instantiated"
    tier_logs = created_seeders[0].tier_logs
    assert any("Seeded tier maintenance" in entry for entry in tier_logs)
    assert not any("no seed students available" in entry for entry in tier_logs)
    assert stats["students_seeded"] == len(created_seeders[0].loader.get_students())
