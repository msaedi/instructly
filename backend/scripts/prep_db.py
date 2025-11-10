#!/usr/bin/env python3
"""
prep_db.py — environment-aware database prep for Instainstru.

Supports SITE_MODE resolution via positional arg, env var, or legacy flags.
Modes: prod | preview | stg | int
"""

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import random
import shlex
import subprocess
import sys
import textwrap
from typing import Any, Callable, List, Optional, Tuple
import urllib.request

import click
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Load backend/.env so lowercase keys are available when running directly
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(BACKEND_DIR / ".env.render", override=False)
except Exception:
    pass

# Pre-set SITE_MODE before importing settings so banner selection matches target.
if len(sys.argv) > 1:
    candidate_mode = sys.argv[1].strip().lower()
    if candidate_mode in {"int", "stg", "preview", "prod"}:
        mapped_mode = {
            "int": "int",
            "stg": "stg",
            "preview": "preview",
            "prod": "prod",
        }[candidate_mode]
        os.environ.setdefault("SITE_MODE", "local" if mapped_mode == "stg" else mapped_mode)

# Import settings after dotenv so local overrides take effect
from scripts.seed_chat_fixture import seed_chat_fixture_booking

from app.core.config import settings
from app.database import SessionLocal
from app.utils.env_logging import (
    log_info as color_log_info,
    log_warn as color_log_warn,
)

# ---------- tiny log helpers ----------


_ENV_TAGS = {"INT", "STG", "PREVIEW", "PROD"}


def warn(msg: str):
    click.echo(f"{click.style('[WARN]', fg='yellow')} {msg}", err=True)


def info(tag: str, msg: str):
    upper = tag.upper()
    if upper in _ENV_TAGS:
        color_log_info(upper.lower(), msg)
    else:
        click.echo(f"[{upper}] {msg}")


def fail(msg: str, code: int = 1):
    click.echo(f"{click.style('[ERROR]', fg='red')} {msg}", err=True)
    sys.exit(code)


# ---------- env resolution ----------

ALIASES = {
    "prod": {"prod", "production", "live"},
    "preview": {"preview", "pre"},
    "stg": {"stg", "stage", "staging", "local"},
    "int": {"int", "test", "ci"},
}

ENV_SNAPSHOT_KEYS = [
    "SEED_AVAILABILITY",
    "SEED_AVAILABILITY_WEEKS",
    "BITMAP_BACKFILL_DAYS",
    "SEED_REVIEW_LOOKBACK_DAYS",
    "SEED_REVIEW_HORIZON_DAYS",
    "SEED_REVIEW_DURATIONS",
    "SEED_REVIEW_STUDENT_EMAIL",
    "INCLUDE_MOCK_USERS",
    "SITE_MODE",
    "SEED_TRACE",
]


def build_env_snapshot(mode: str) -> dict[str, str]:
    snapshot: dict[str, str] = {"target": mode}
    for key in ENV_SNAPSHOT_KEYS:
        snapshot[key] = os.getenv(key, "")
    return snapshot


def snapshot_to_json(snapshot: dict[str, str]) -> str:
    return json.dumps(snapshot, separators=(",", ":"))


def is_trace_enabled() -> bool:
    return os.getenv("SEED_TRACE", "0").lower() in {"1", "true", "yes"}


def trace_message(label: str, env_json: str) -> None:
    if not is_trace_enabled():
        return
    pid = os.getpid()
    click.echo(f'{"[trace]"} phase="{label}" pid={pid} env={env_json}')


def _norm_mode(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip().lower()
    for canon, names in ALIASES.items():
        if s in names:
            return canon
    return None


def detect_site_mode(positional: Optional[str], explicit: Optional[str]) -> Tuple[str, bool]:
    """Return (mode, legacy_used). Priority: --env > positional > SITE_MODE > legacy > default(int)."""
    flag_mode = _norm_mode(explicit)
    if explicit:
        if not flag_mode:
            fail(f"Unknown env alias from --env: {explicit}")
        return flag_mode, False

    # positional
    m = _norm_mode(positional)
    if m:
        return m, False

    # env
    env_mode = _norm_mode(os.getenv("SITE_MODE"))
    if env_mode:
        return env_mode, False

    # legacy
    # default
    return "int", False


ENV_URL_VARS = {
    "int": ("DATABASE_URL_INT", "TEST_DATABASE_URL", "test_database_url"),
    "stg": ("DATABASE_URL_STG", "STG_DATABASE_URL", "LOCAL_DATABASE_URL", "local_database_url", "stg_database_url"),
    "preview": ("DATABASE_URL_PREVIEW", "PREVIEW_DATABASE_URL", "preview_database_url"),
    "prod": ("DATABASE_URL_PROD", "PROD_DATABASE_URL", "PRODUCTION_DATABASE_URL", "prod_database_url"),
}

SERVICE_ENV_URL_VARS = {
    "preview": ("PREVIEW_SERVICE_DATABASE_URL", "preview_service_database_url"),
    "prod": ("PROD_SERVICE_DATABASE_URL", "prod_service_database_url"),
}


def resolve_db_url(mode: str) -> str:
    """Resolve DB URL using env overrides first, then settings fields."""
    for key in ENV_URL_VARS.get(mode, ()):  # try lowercase/uppercase variants
        value = os.getenv(key)
        if value:
            return value
        value = os.getenv(key.upper())
        if value:
            return value

    if mode == "prod":
        return settings.prod_database_url_raw or ""
    if mode == "preview":
        return settings.preview_database_url_raw or ""
    if mode == "stg":
        return settings.stg_database_url or settings.prod_database_url_raw or ""
    # int/default
    return settings.test_database_url


def resolve_service_db_url(mode: str) -> str:
    for key in SERVICE_ENV_URL_VARS.get(mode, ()):  # try lowercase/uppercase variants
        value = os.getenv(key)
        if value:
            return value
        value = os.getenv(key.upper())
        if value:
            return value

    if mode == "prod":
        return settings.prod_service_database_url_raw or ""
    if mode == "preview":
        return settings.preview_service_database_url_raw or ""
    return ""


# ---------- ops ----------


def redact(url: str) -> str:
    try:
        if "://" in url and "@" in url:
            scheme, rest = url.split("://", 1)
            creds, host = rest.split("@", 1)
            return f"{scheme}://***:***@{host}"
    except Exception:
        pass
    return url


def run_migrations(db_url: str, dry_run: bool, tool_cmd: Optional[str]):
    if dry_run:
        info("dry", f"(dry-run) Would run migrations on {redact(db_url)}")
        return
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    cmd = tool_cmd or "alembic upgrade head"
    info("sys", f"Running migrations: {cmd}")
    subprocess.check_call(shlex.split(cmd), cwd=str(BACKEND_DIR), env=env)


def _mode_env(mode: str) -> dict:
    # Only SITE_MODE is authoritative now
    site_mode = "local" if mode == "stg" else mode
    return {"SITE_MODE": site_mode}


def seed_system_data(db_url: str, dry_run: bool, mode: str, seed_db_url: Optional[str] = None):
    if dry_run:
        info("dry", f"(dry-run) Would seed SYSTEM data on {redact(db_url)}")
        info(
            "dry",
            "(dry-run) Would upsert 10 badge definitions: "
            "welcome_aboard, foundation_builder, first_steps, dedicated_learner, momentum_starter, "
            "consistent_learner, top_student, explorer, favorite_partnership, year_one_learner",
        )
        return
    info("seed", "Seeding SYSTEM data…")
    # Roles/permissions and catalog + regions
    target = seed_db_url or db_url
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": target}
    subprocess.check_call([sys.executable, "scripts/seed_data.py", "--system-only"], cwd=str(BACKEND_DIR), env=env)


def seed_mock_users(db_url: str, dry_run: bool, mode: str, seed_db_url: Optional[str] = None):
    if dry_run:
        info("dry", f"(dry-run) Would seed MOCK users on {redact(db_url)}")
        return
    info("seed", "Seeding MOCK users/instructors/bookings…")
    target = seed_db_url or db_url
    os.environ["DATABASE_URL"] = target
    env_snapshot_json = snapshot_to_json(build_env_snapshot(mode))
    trace_message("seed_mock_users:start", env_snapshot_json)

    from scripts import seed_data  # noqa: E402

    stats = seed_data.seed_mock_data(verbose=True, return_stats=True) or {}
    trace_message("seed_mock_users:end", env_snapshot_json)
    info(
        "seed",
        "Mock data summary: bookings={bookings_created}, reviews={reviews_created}, "
        "credits={credits_created}, badges={badges_awarded}".format(
            bookings_created=stats.get("bookings_created", 0),
            reviews_created=stats.get("reviews_created", 0),
            credits_created=stats.get("credits_created", 0),
            badges_awarded=stats.get("badges_awarded", 0),
        ),
    )


def _run_future_bitmap_seeding(weeks: int, dry_run: bool, banner_prefix: str) -> dict[str, int]:
    stats = {
        "weeks_requested": weeks,
        "weeks_written": 0,
        "instructor_weeks": 0,
    }
    info(banner_prefix, f"Seeding bitmap availability for the next {weeks} week(s)…")
    if dry_run:
        info(banner_prefix, "(dry-run) Would seed future bitmap weeks.")
        return stats

    from scripts.seed_bitmap_availability import seed_bitmap_availability

    result = seed_bitmap_availability(weeks)
    if result:
        stats["weeks_written"] = len(result)
        stats["instructor_weeks"] = sum(result.values())
        for week_start, count in sorted(result.items()):
            info(banner_prefix, f"  → Week starting {week_start}: wrote {count} instructor(s)")
        info(
            banner_prefix,
            f"✓ Future bitmap seeding complete: {stats['instructor_weeks']} instructor-week writes",
        )
    else:
        info(banner_prefix, "  → Future bitmap seeder had nothing to write.")
        info(banner_prefix, "✓ Future bitmap seeding complete: 0 writes")
    return stats


def _run_bitmap_backfill(backfill_days: int, dry_run: bool, banner_prefix: str) -> dict[str, int]:
    stats = {
        "days_requested": backfill_days,
        "instructors_touched": 0,
        "days_backfilled": 0,
    }
    info(banner_prefix, f"Backfilling bitmap availability for the past {backfill_days} day(s)…")
    if dry_run:
        info(banner_prefix, "(dry-run) Would backfill historical bitmap coverage.")
        return stats

    if backfill_days == 0:
        info(banner_prefix, "Backfill days set to 0; skipping backfill step.")
        return stats

    from scripts.backfill_bitmaps import backfill_bitmaps_range

    from app.database import SessionLocal

    with SessionLocal() as session:
        result = backfill_bitmaps_range(session, backfill_days)
        if result:
            session.commit()
            stats["instructors_touched"] = len(result)
            stats["days_backfilled"] = sum(result.values())
            for instructor_id, days_written in sorted(result.items()):
                info(
                    banner_prefix,
                    f"  → Backfilled {days_written} day(s) of historical bitmap availability for instructor {instructor_id}",
                )
            info(
                banner_prefix,
                f"✓ Bitmap backfill complete: {stats['days_backfilled']} total day writes "
                f"across {stats['instructors_touched']} instructor(s)",
            )
        else:
            session.rollback()
            info(banner_prefix, "  → No instructors required bitmap backfill.")
            info(banner_prefix, "✓ Bitmap backfill complete: 0 day writes")
    return stats


def run_availability_pipeline(mode: str, dry_run: bool, banner_prefix: str = "pipeline") -> None:
    """Seed future bitmap availability (optional) and backfill past days."""

    if mode not in {"int", "stg"}:
        info(
            banner_prefix,
            f"Skipping availability pipeline in mode '{mode}' (supported: int, stg).",
        )
        return

    seed_future_flag = os.getenv("SEED_AVAILABILITY", "0").lower() in {"1", "true", "yes"}
    weeks_env = os.getenv("SEED_AVAILABILITY_WEEKS")
    weeks = 4
    if weeks_env:
        try:
            weeks = max(1, int(weeks_env))
        except ValueError:
            warn(f"Invalid SEED_AVAILABILITY_WEEKS='{weeks_env}', falling back to {weeks}.")

    backfill_days_env = os.getenv("BITMAP_BACKFILL_DAYS", "56")
    try:
        backfill_days = max(0, int(backfill_days_env or "56"))
    except ValueError:
        warn(f"Invalid BITMAP_BACKFILL_DAYS='{backfill_days_env}', defaulting to 56.")
        backfill_days = 56

    phase_num = 1
    total_future_writes = 0
    total_backfill_writes = 0

    if seed_future_flag:
        info(banner_prefix, f"╔═ Phase {phase_num}: Future Bitmap Seeding ═╗")
        future_stats = _run_future_bitmap_seeding(weeks, dry_run, banner_prefix)
        total_future_writes = future_stats["instructor_weeks"]
    else:
        info(banner_prefix, f"╔═ Phase {phase_num}: Future Bitmap Seeding ═╗")
        info(banner_prefix, "SEED_AVAILABILITY not set; skipping future-week seeding.")
    phase_num += 1

    info(banner_prefix, f"╔═ Phase {phase_num}: Bitmap Backfill ═╗")
    backfill_stats = _run_bitmap_backfill(backfill_days, dry_run, banner_prefix)
    total_backfill_writes = backfill_stats["days_backfilled"]

    os.environ.setdefault("BITMAP_PIPELINE_COMPLETED", "1")

    info(banner_prefix, "╔═ Availability Pipeline Summary ═╗")
    info(banner_prefix, f"  Future writes: {total_future_writes} instructor-weeks")
    info(banner_prefix, f"  Backfill writes: {total_backfill_writes} days")
    info(banner_prefix, "✓ Availability pipeline complete")


def probe_bitmap_coverage(
    db_url: str,
    lookback_days: int,
    horizon_days: int,
    sample_size: int = 3,
) -> dict[str, Any]:
    """Collect bitmap coverage statistics for a rolling window."""

    start_date = date.today() - timedelta(days=lookback_days)
    end_date = date.today() + timedelta(days=horizon_days)

    query = text(
        """
        SELECT instructor_id, COUNT(*) AS rows
        FROM availability_days
        WHERE day_date BETWEEN :start AND :end
        GROUP BY instructor_id
        """
    )
    engine = create_engine(db_url)
    with engine.connect() as conn:  # type: ignore[assignment]
        results = conn.execute(query, {"start": start_date, "end": end_date}).fetchall()

    total_rows = sum(row._mapping["rows"] for row in results)
    instructor_count = len(results)

    sample_rows = []
    if results:
        selected = random.sample(results, min(sample_size, len(results)))
        for row in selected:
            mapping = row._mapping
            sample_rows.append(
                {
                    "instructor_id": mapping["instructor_id"],
                    "rows": mapping["rows"],
                }
            )

    return {
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "lookback_days": lookback_days,
        "horizon_days": horizon_days,
        "instructor_count": instructor_count,
        "total_rows": total_rows,
        "sample": sample_rows,
    }


def count_instructors(db_url: str) -> int:
    """Return number of users assigned the instructor role."""

    engine = create_engine(db_url)
    query = text(
        """
        SELECT COUNT(*)
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id
        WHERE r.name = :role_name
        """
    )
    try:
        with engine.connect() as conn:  # type: ignore[assignment]
            result = conn.execute(query, {"role_name": "instructor"}).scalar()
            return int(result or 0)
    finally:
        engine.dispose()


def count_mock_students(db_url: str) -> int:
    """Return number of mock students (example.com) assigned the student role."""

    engine = create_engine(db_url)
    query = text(
        """
        SELECT COUNT(*)
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id
        WHERE r.name = :role_name
          AND u.email LIKE :email_pattern
        """
    )
    try:
        with engine.connect() as conn:  # type: ignore[assignment]
            result = conn.execute(query, {"role_name": "student", "email_pattern": "%@example.com"}).scalar()
            return int(result or 0)
    finally:
        engine.dispose()


def format_probe_sample(sample: list[dict[str, Any]]) -> str:
    if not sample:
        return "none"
    return ", ".join(
        f"{(entry.get('instructor_id') or '')[-6:]}:{entry.get('rows', 0)}"
        for entry in sample[:3]
    )


def run_seed_all_pipeline(
    *,
    mode: str,
    db_url: str,
    seed_db_url: str,
    migrate: bool,
    dry_run: bool,
    env_snapshot: dict[str, str],
    include_mock_users: bool,
) -> dict[str, Any]:
    """Execute the deterministic seed-all pipeline with explicit phases."""

    total_phases = 6
    env_json = snapshot_to_json(env_snapshot)

    def phase_heading(index: int, title: str) -> None:
        info("pipeline", f"Phase {index}/{total_phases}: {title}")
        trace_message(f"Phase {index}: {title}", env_json)

    def log_summary(message: str) -> None:
        info("pipeline", f"  ↪︎ {message}")

    def parse_int_env(key: str, default: int) -> int:
        raw = os.getenv(key)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except ValueError:
            warn(f"Invalid {key}='{raw}', defaulting to {default}.")
            return default

    seed_future_flag = os.getenv("SEED_AVAILABILITY", "0").lower() in {"1", "true", "yes"}
    weeks = parse_int_env("SEED_AVAILABILITY_WEEKS", 4)
    backfill_days = parse_int_env("BITMAP_BACKFILL_DAYS", 56)
    review_lookback = parse_int_env("SEED_REVIEW_LOOKBACK_DAYS", 90)
    review_horizon = parse_int_env("SEED_REVIEW_HORIZON_DAYS", 21)

    pipeline_result: dict[str, Any] = {
        "future_instructor_weeks": 0,
        "backfill_days": 0,
        "students_seeded": 0,
        "instructors_seeded": 0,
        "bookings_created": 0,
        "reviews_created": 0,
        "reviews_skipped": False,
        "credits_created": 0,
        "badges_awarded": 0,
        "skip_reviews": False,
    }
    system_data_seeded = False
    mock_seeder: Optional["DatabaseSeeder"] = None  # type: ignore[name-defined]

    # Phase 1: Migrate
    phase_heading(1, "Migrate")
    if migrate:
        if dry_run:
            log_summary("dry-run: would run migrations")
        else:
            run_migrations(db_url, dry_run, None)
            log_summary("migrations applied")
    else:
        log_summary("skipped (--migrate not provided)")

    # Phase 1b: Ensure mock instructors exist before bitmap seeding
    info("pipeline", "Phase 1b/6: Ensure mock instructors")
    instructors_before = 0
    if not dry_run:
        try:
            instructors_before = count_instructors(db_url)
        except Exception as exc:  # pragma: no cover - defensive logging
            warn(f"Unable to count instructors prior to ensure step: {exc}")
    log_summary(f"existing instructors before ensure={instructors_before}")
    if dry_run:
        log_summary("dry-run: skipped ensure stage")
    elif not include_mock_users:
        log_summary(
            f"ℹ️  Skipping mock users/instructors/bookings "
            f"(include_mock_users=0 target={mode})"
        )
    else:
        from scripts.reset_and_seed_yaml import DatabaseSeeder  # noqa: E402

        mock_seeder = DatabaseSeeder()
        log_summary("resetting mock dataset (idempotent cleanup)")
        mock_seeder.reset_database()
        seed_system_data(db_url, dry_run, mode, seed_db_url=seed_db_url)
        system_data_seeded = True
        log_summary("seeding instructor baseline prior to bitmap pipeline")
        mock_seeder.create_instructors(seed_tier_maintenance=False)
        instructors_after = count_instructors(db_url) if not dry_run else instructors_before
        log_summary(f"instructor count after ensure={instructors_after}")

    # Phase 2: Seed future bitmap availability
    phase_heading(2, "Seed future bitmap availability")
    if not seed_future_flag:
        log_summary("skipped (SEED_AVAILABILITY not enabled)")
    else:
        stats_future = _run_future_bitmap_seeding(weeks, dry_run, "pipeline")
        pipeline_result["future_instructor_weeks"] = stats_future["instructor_weeks"]
        log_summary(
            f"wrote {stats_future['instructor_weeks']} instructor-week rows across {stats_future['weeks_written']} week(s)"
        )

    # Phase 3: Backfill bitmap availability
    phase_heading(3, "Backfill bitmap availability")
    backfill_stats = _run_bitmap_backfill(backfill_days, dry_run, "pipeline")
    pipeline_result["backfill_days"] = backfill_stats["days_backfilled"]
    log_summary(
        f"backfilled {backfill_stats['days_backfilled']} day(s) across {backfill_stats['instructors_touched']} instructor(s)"
    )

    os.environ.setdefault("BITMAP_PIPELINE_COMPLETED", "1")

    # Probe coverage after availability work
    if dry_run:
        info("pipeline", "Probe: skipped (dry-run mode)")
        probe_result = {
            "lookback_days": review_lookback,
            "horizon_days": review_horizon,
            "total_rows": 0,
            "sample": [],
        }
        skip_reviews = False
    else:
        probe_result = probe_bitmap_coverage(db_url, review_lookback, review_horizon)
        total_rows = probe_result["total_rows"]
        info(
            "pipeline",
            f"Probe: bitmap rows in [today-{review_lookback}, today+{review_horizon}] = {total_rows}",
        )
        sample_summary = format_probe_sample(probe_result.get("sample", []))
        if sample_summary != "none":
            info("pipeline", f"  ↪︎ sample (last 3 ids): {sample_summary}")
        skip_reviews = total_rows == 0
        if skip_reviews:
            info("pipeline", "  ⚠️  No bitmap rows detected; reviews will be skipped.")
    os.environ["BITMAP_PROBE_RESULT"] = json.dumps(probe_result)

    # Ensure system data seeded before mock stages
    if not dry_run and not system_data_seeded:
        seed_system_data(db_url, dry_run, mode, seed_db_url=seed_db_url)
        system_data_seeded = True

    # Phase 4: Mock users + bookings + reviews
    phase_heading(4, "Mock users + bookings + reviews")
    if dry_run:
        log_summary("dry-run: would seed mock users, bookings, and reviews")
    elif not include_mock_users:
        log_summary("skipped (mock user seeding disabled)")
    else:
        if mock_seeder is None:
            from scripts.reset_and_seed_yaml import DatabaseSeeder  # noqa: E402

            mock_seeder = DatabaseSeeder()
            log_summary("fallback seeder instantiated (no pre-run baseline detected)")
        students_defined = len(mock_seeder.loader.get_students())
        instructors_defined = len(mock_seeder.loader.get_instructors())
        if students_defined == 0:
            log_summary("no mock students defined in loader; nothing to seed")
        students_before = 0
        students_after = students_defined if dry_run else 0
        if not dry_run:
            try:
                students_before = count_mock_students(db_url)
            except Exception as exc:  # pragma: no cover - defensive logging
                warn(f"Unable to count mock students prior to seeding: {exc}")
                students_before = 0
        mock_seeder.create_students()
        if not dry_run:
            try:
                students_after = count_mock_students(db_url)
            except Exception as exc:  # pragma: no cover - defensive logging
                warn(f"Unable to count mock students after seeding: {exc}")
                students_after = students_before
        mock_seeder.create_availability()
        mock_seeder.create_coverage_areas()
        bookings_created = mock_seeder.create_bookings() or 0
        students_created = max(students_after - students_before, 0)
        students_skipped = max(students_defined - students_created, 0)
        log_summary(
            "ℹ️  Mock students defined={defined}, created={created}, skipped={skipped}, total_now={total}".format(
                defined=students_defined,
                created=students_created,
                skipped=students_skipped,
                total=students_after,
            )
        )
        tier_seeded = mock_seeder.seed_tier_maintenance_sessions(
            reason="no mock students detected after student seeding stage"
        )
        pipeline_result["students_seeded"] = students_after
        pipeline_result["instructors_seeded"] = instructors_defined
        pipeline_result["bookings_created"] = bookings_created
        if tier_seeded:
            log_summary(f"seeded {tier_seeded} tier maintenance session(s) for instructor tiers")
        if skip_reviews:
            pipeline_result["reviews_skipped"] = True
            pipeline_result["reviews_created"] = 0
            log_summary(
                f"✅ Seeded {students_defined} students, "
                f"{instructors_defined} instructors, "
                f"{bookings_created} bookings; reviews skipped (probe rows=0)"
            )
        else:
            reviews_created = mock_seeder.create_reviews(strict=False) or 0
            pipeline_result["reviews_created"] = reviews_created
            pipeline_result["reviews_skipped"] = False
            log_summary(
                f"✅ Seeded {students_defined} students, "
                f"{instructors_defined} instructors, "
                f"{bookings_created} bookings, "
                f"{reviews_created} reviews"
            )

    # Optional recovery pass if reviews were skipped despite instructor seeding
    if (
        not dry_run
        and include_mock_users
        and mock_seeder is not None
        and (pipeline_result["reviews_created"] == 0 or pipeline_result["reviews_skipped"])
    ):
        info("pipeline", "Phase 4a/6: Availability recovery (auto)")
        recovery_future = _run_future_bitmap_seeding(weeks, dry_run, "pipeline")
        recovery_backfill = _run_bitmap_backfill(backfill_days, dry_run, "pipeline")
        pipeline_result["future_instructor_weeks"] = max(
            pipeline_result["future_instructor_weeks"], recovery_future["instructor_weeks"]
        )
        pipeline_result["backfill_days"] = max(
            pipeline_result["backfill_days"], recovery_backfill["days_backfilled"]
        )
        recovery_probe = probe_bitmap_coverage(db_url, review_lookback, review_horizon)
        os.environ["BITMAP_PROBE_RESULT"] = json.dumps(recovery_probe)
        info(
            "pipeline",
            f"Probe (post-recovery): bitmap rows in [today-{review_lookback}, today+{review_horizon}] = {recovery_probe['total_rows']}",
        )
        sample_summary = format_probe_sample(recovery_probe.get("sample", []))
        if sample_summary != "none":
            info("pipeline", f"  ↪︎ sample (last 3 ids): {sample_summary}")
        if recovery_probe["total_rows"] > 0:
            skip_reviews = False
            pipeline_result["reviews_skipped"] = False
            recovered_reviews = mock_seeder.create_reviews(strict=False) or 0
            pipeline_result["reviews_created"] = recovered_reviews
            log_summary(f"recovery seeded {recovered_reviews} reviews after availability rerun")
        else:
            info("pipeline", "  ⚠️  Recovery probe still zero; reviews remain skipped.")

    # Phase 5: Platform credits
    phase_heading(5, "Platform credits")
    if dry_run:
        log_summary("dry-run: would seed platform credits")
    elif not include_mock_users:
        log_summary("skipped (mock user seeding disabled)")
    else:
        if mock_seeder is None:
            from scripts.reset_and_seed_yaml import DatabaseSeeder  # noqa: E402

            mock_seeder = DatabaseSeeder()
        credits_created = mock_seeder.create_sample_platform_credits() or 0
        pipeline_result["credits_created"] = credits_created
        log_summary(f"created {credits_created} platform credit(s)")

    # Phase 6: Badges
    phase_heading(6, "Badges")
    if dry_run:
        log_summary("dry-run: would award demo badges")
    elif not include_mock_users:
        log_summary("skipped (mock user seeding disabled)")
    else:
        from scripts.seed_data import seed_demo_student_badges  # noqa: E402

        if mock_seeder is None:
            from scripts.reset_and_seed_yaml import DatabaseSeeder  # noqa: E402

            mock_seeder = DatabaseSeeder()
        badges_awarded = seed_demo_student_badges(mock_seeder.engine, verbose=True) or 0
        pipeline_result["badges_awarded"] = badges_awarded
        log_summary(f"awarded {badges_awarded} demo badge(s)")

    if mock_seeder is not None and not dry_run:
        mock_seeder.print_summary()
    if mock_seeder is not None:
        try:
            mock_seeder.engine.dispose()
        except Exception:
            pass

    pipeline_result["skip_reviews"] = skip_reviews

    if not dry_run and include_mock_users:
        default_seed_chat = settings.site_mode.lower() not in {"prod", "production", "beta", "live"}
        if settings.env_bool("SEED_CHAT_FIXTURE", default_seed_chat):
            try:
                start_hour = int(os.getenv("CHAT_FIXTURE_START_HOUR", "19") or 19)
                duration_minutes = int(os.getenv("CHAT_FIXTURE_DURATION_MINUTES", "60") or 60)
                days_ahead_min = int(os.getenv("CHAT_FIXTURE_DAYS_AHEAD_MIN", "3") or 3)
                days_ahead_max = int(os.getenv("CHAT_FIXTURE_DAYS_AHEAD_MAX", "10") or 10)
            except ValueError:
                warn("chat fixture config contains invalid integers; skipping fixture seeding")
            else:
                try:
                    fixture_status = seed_chat_fixture_booking(
                        instructor_email=os.getenv("CHAT_INSTRUCTOR_EMAIL", "sarah.chen@example.com"),
                        student_email=os.getenv("CHAT_STUDENT_EMAIL", "emma.johnson@example.com"),
                        start_hour=start_hour,
                        duration_minutes=duration_minutes,
                        days_ahead_min=days_ahead_min,
                        days_ahead_max=days_ahead_max,
                        location=os.getenv("CHAT_FIXTURE_LOCATION", "neutral"),
                        service_name=os.getenv("CHAT_FIXTURE_SERVICE_NAME", "Lesson"),
                        session_factory=SessionLocal,
                    )
                    if fixture_status == "error":
                        warn("chat fixture booking encountered an error; see log output above.")
                except Exception as exc:  # pragma: no cover - best effort seeding
                    warn(f"chat fixture booking failed unexpectedly: {exc}")

    return pipeline_result


def run_reviews_only(dry_run: bool, banner_prefix: str = "pipeline", strict: bool = True) -> None:
    """Seed review bookings using the DatabaseSeeder helper."""

    if dry_run:
        info(banner_prefix, "(dry-run) Would seed review bookings.")
        return

    from scripts.reset_and_seed_yaml import DatabaseSeeder

    lookback = int(os.getenv("SEED_REVIEW_LOOKBACK_DAYS", "90") or 90)
    horizon = int(os.getenv("SEED_REVIEW_HORIZON_DAYS", "21") or 21)
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        fail("DATABASE_URL must be set to run review seeding.")

    probe_result = probe_bitmap_coverage(db_url, lookback, horizon)
    sample_summary = format_probe_sample(probe_result.get("sample", []))
    info(
        banner_prefix,
        f"Bitmap coverage probe: total_rows={probe_result['total_rows']} "
        f"instructors={probe_result['instructor_count']} sample={sample_summary}",
    )
    if probe_result["total_rows"] == 0:
        info(
            banner_prefix,
            "  ❌  Refusing to seed reviews because bitmap probe returned zero rows.\n"
            "      Run `--seed-availability-only` first to seed and backfill availability.",
        )
        raise RuntimeError("Bitmap coverage probe returned zero rows; reviews-only seed aborted.")

    os.environ["BITMAP_PROBE_RESULT"] = json.dumps(probe_result)

    seeder = DatabaseSeeder()
    created = seeder.create_reviews(strict=strict) or 0
    info(banner_prefix, f"Seeded {created} reviews.")


def verify_env_marker(db_url: str, expected_mode: str) -> bool:
    """
    Optional sanity check. If a 'settings' table with key='env_name' exists, verify it.
    Return True if OK or unknown; False if mismatch.
    """
    try:
        import psycopg2  # type: ignore
    except Exception:
        warn("psycopg2 not available; skipping --verify-env check.")
        return True
    try:
        conn = psycopg2.connect(db_url)
        with conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key='env_name'")
            row = cur.fetchone()
            if not row:
                warn("settings.env_name not found; skipping strict verify.")
                return True
            value = (row[0] or "").strip().lower()
            if value not in ALIASES.get(expected_mode, {expected_mode}):
                warn(f"DB env_name='{value}' != expected '{expected_mode}'")
                return False
            return True
    except Exception as e:
        warn(f"--verify-env check skipped ({e})")
        return True


# ---------- post-seed operations ----------


def generate_embeddings(db_url: str, dry_run: bool, mode: str) -> None:
    if dry_run:
        info("dry", f"(dry-run) Would generate embeddings on {redact(db_url)}")
        return
    info("ops", "Generating service embeddings…")
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": db_url}
    subprocess.check_call([sys.executable, "scripts/generate_service_embeddings.py"], cwd=str(BACKEND_DIR), env=env)


def calculate_analytics(db_url: str, dry_run: bool, mode: str) -> None:
    if dry_run:
        info("dry", f"(dry-run) Would calculate service analytics on {redact(db_url)}")
        return
    info("ops", "Calculating service analytics…")
    env = {**os.environ, **_mode_env(mode), "DATABASE_URL": db_url}
    subprocess.check_call([sys.executable, "scripts/calculate_service_analytics.py"], cwd=str(BACKEND_DIR), env=env)


def _render_api_request(url: str, api_key: str, method: str = "GET", data: Optional[dict] = None) -> Optional[dict]:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
        req.data = payload
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset)
            if body:
                return json.loads(body)
            return {}
    except Exception as exc:
        warn(f"Render API request failed ({exc})")
        return None


def _render_list_services(api_key: str) -> list[dict]:
    data = _render_api_request("https://api.render.com/v1/services?limit=100", api_key, method="GET")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "services" in data and isinstance(data["services"], list):
        return data["services"]
    return []


def _render_get_service_id_by_name(api_key: str, service_name: str) -> Optional[str]:
    services = _render_list_services(api_key)
    for svc in services:
        if not isinstance(svc, dict):
            continue
        nested = svc.get("service") if isinstance(svc.get("service"), dict) else None
        flat_name = svc.get("name")
        flat_id = svc.get("id")
        nested_name = nested.get("name") if nested else None
        nested_id = nested.get("id") if nested else None
        if service_name in {flat_name, nested_name}:
            return nested_id or flat_id
    return None


def _render_post_job(api_key: str, service_id: str, command: str) -> bool:
    url = f"https://api.render.com/v1/services/{service_id}/jobs"
    payload = {"startCommand": command}
    resp = _render_api_request(url, api_key, method="POST", data=payload)
    if resp is None:
        warn("Failed to start Render job (no response)")
        return False
    return True


def _render_redeploy_service(api_key: str, service_id: str) -> bool:
    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    payload = {"clearCache": "do_not_clear"}
    resp = _render_api_request(url, api_key, method="POST", data=payload)
    if resp is None:
        warn("Failed to trigger Render deploy")
        return False
    return True


def clear_cache(mode: str, dry_run: bool) -> None:
    if mode == "int":
        info("CACHE", "Skipping cache clear for INT")
        return
    if mode == "stg":
        if dry_run:
            info("DRY", "(dry-run) Would run local cache clear script for STG")
            return
        info("CACHE", "Clearing cache locally via script…")
        try:
            result = subprocess.run(
                [sys.executable, "scripts/clear_cache.py", "--scope", "all", "--echo-sentinel"],
                cwd=str(BACKEND_DIR),
                capture_output=True,
                text=True,
                check=True,
            )
            output = result.stdout or ""
            if "CACHE_CLEAR_OK" in output:
                color_log_info("stg", "Local cache cleared successfully")
            else:
                color_log_warn("stg", "Local cache script completed without sentinel acknowledgment")
        except FileNotFoundError:
            color_log_warn("stg", "clear_cache.py not found; skipping cache clear")
        except subprocess.CalledProcessError as exc:
            color_log_warn("stg", f"Local cache clear failed: {exc.stderr or exc.stdout or exc}")
        return

    if mode not in {"preview", "prod"}:
        warn(f"Unknown cache clear mode '{mode}'")
        return

    backend_service = "instainstru-api-preview" if mode == "preview" else "instainstru-api"
    redis_service = "redis-preview" if mode == "preview" else "redis"
    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        color_log_warn(mode, "RENDER_API_KEY not set; skipping Render cache clear")
        return

    if dry_run:
        info("DRY", f"(dry-run) Would trigger Render job on {backend_service}")
        info("DRY", f"(dry-run) Would redeploy Render service {redis_service}")
        return

    backend_id = _render_get_service_id_by_name(api_key, backend_service)
    if backend_id:
        ok = _render_post_job(api_key, backend_id, 'bash -lc "python backend/scripts/clear_cache.py --scope all"')
        if not ok:
            color_log_warn(mode, f"Failed to start cache-clear job for {backend_service}")
    else:
        color_log_warn(mode, f"Could not find Render service '{backend_service}'")

    redis_id = _render_get_service_id_by_name(api_key, redis_service)
    if redis_id:
        ok = _render_redeploy_service(api_key, redis_id)
        if not ok:
            color_log_warn(mode, f"Failed to redeploy Render service '{redis_service}'")
    else:
        color_log_warn(mode, f"Could not find Render service '{redis_service}'")


# ---------- main ----------


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Prepare database by environment.",
        epilog=textwrap.dedent(
            """
Examples:
  python scripts/prep_db.py                # default → int
  python scripts/prep_db.py stg
  python scripts/prep_db.py preview
  python scripts/prep_db.py prod

  SITE_MODE=preview python scripts/prep_db.py --migrate --seed-all
  SITE_MODE=prod    python scripts/prep_db.py --migrate --seed-all --force --yes

  # Seed with additional mock data windows (overrides config defaults)
  python backend/scripts/prep_db.py int --seed-all --set availability_weeks_future=6 --set availability_weeks_past=2
  python backend/scripts/prep_db.py stg --seed-all --set booking_days_future=10 --set booking_days_past=30

Seed-all executes six phases in order (Migrate → Seed future bitmap availability → Backfill bitmap availability →
Mock users + bookings + reviews → Platform credits → Badges). Use --include-mock-users/--exclude-mock-users
to control the mock-data phases (stg/int default to include).
"""
        ),
    )
    parser.add_argument("env", nargs="?", help="env alias: int|stg|preview|prod")
    parser.add_argument("--env", dest="env_flag", help="explicit env alias (same choices as positional)")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--seed-all", action="store_true")
    parser.add_argument("--seed-system-only", action="store_true")
    parser.add_argument("--seed-mock-users", action="store_true")
    parser.add_argument(
        "--seed-availability-only",
        action="store_true",
        help="Run only the bitmap availability pipeline (future + backfill) and exit.",
    )
    parser.add_argument(
        "--seed-reviews-only",
        action="store_true",
        help="Seed review bookings only (requires existing bitmap coverage).",
    )
    parser.add_argument(
        "--include-mock-users",
        action="store_true",
        help="Force inclusion of mock users/instructors/bookings during --seed-all.",
    )
    parser.add_argument(
        "--exclude-mock-users",
        action="store_true",
        help="Skip mock user seeding even when --seed-all is used.",
    )
    parser.add_argument(
        "--seed-all-prod",
        action="store_true",
        help="Allow mock/demo data seeding in prod (requires --force and --yes)",
    )
    parser.add_argument("--dry-run", "--noop", dest="dry_run", action="store_true")
    parser.add_argument("--migrate-tool", type=str, default=None)
    parser.add_argument("--force", action="store_true", help="required for any writes in prod")
    parser.add_argument("--yes", action="store_true", help="non-interactive confirmation for prod")
    parser.add_argument("--verify-env", action="store_true", help="sanity-check DB env marker")
    args = parser.parse_args()

    mode, legacy = detect_site_mode(args.env, args.env_flag)
    if legacy:
        warn(
            "Legacy flags (USE_*_DATABASE) are deprecated. Use SITE_MODE or positional env. This mapping will be removed."
        )

    db_url = resolve_db_url(mode)
    service_db_url = resolve_service_db_url(mode)
    seed_db_url = service_db_url or db_url
    if not db_url:
        missing = {
            "stg": "stg_database_url",
            "preview": "preview_database_url",
            "prod": "prod_database_url",
        }.get(mode, "test_database_url")
        fail(f"Missing database URL for mode '{mode}'. Set {missing} or export an override.")

    os.environ["DATABASE_URL"] = db_url
    site_mode_env = "local" if mode == "stg" else mode
    os.environ["SITE_MODE"] = site_mode_env
    if mode == "int":
        os.environ["TEST_DATABASE_URL"] = db_url
    elif mode == "stg":
        os.environ["STG_DATABASE_URL"] = db_url
        os.environ["LOCAL_DATABASE_URL"] = db_url
    elif mode == "preview":
        os.environ["PREVIEW_DATABASE_URL"] = db_url
    else:
        os.environ["PROD_DATABASE_URL"] = db_url

    # verify env marker (optional)
    if args.verify_env:
        ok = verify_env_marker(db_url, mode)
        if not ok and not args.force:
            info("guard", "Env marker mismatch; re-run with --force to override.")
            sys.exit(0)

    # prod safety
    if mode == "prod":
        if args.seed_all_prod:
            if not (args.force and args.yes):
                fail("Prod mock seeding requires --force and --yes.")
            args.seed_all = True
            args.seed_mock_users = True
            args.seed_system_only = True
        elif args.seed_mock_users or args.seed_all:
            warn("Prod mode: mock user seeding is not allowed. Forcing system-only.")
            args.seed_system_only = True
            args.seed_mock_users = False
            args.seed_all = False
        if not args.dry_run and (args.migrate or args.seed_system_only or args.seed_all_prod):
            if not (args.force and args.yes):
                fail("Prod writes require BOTH --force and --yes.")
        # optional interactive confirmation (only when writing)
        if not args.yes and not args.dry_run and (args.migrate or args.seed_system_only) and not os.getenv("CI"):
            resp = input("You are about to modify PRODUCTION. Type 'yes' to continue: ").strip().lower()
            if resp != "yes":
                info("prod", "Operation cancelled.")
                sys.exit(0)

    if args.seed_availability_only and args.seed_reviews_only:
        fail("Cannot combine --seed-availability-only with --seed-reviews-only.")

    include_mock_users = args.include_mock_users or args.seed_mock_users
    mock_default_message: Optional[str] = None
    if args.exclude_mock_users:
        include_mock_users = False
    elif args.seed_all:
        if args.include_mock_users or args.seed_mock_users:
            include_mock_users = True
        elif mode in {"stg", "int"}:
            include_mock_users = True
            mock_default_message = "[seed] defaulting include-mock-users=true for stg/int with --seed-all"
        else:
            include_mock_users = False
    os.environ["INCLUDE_MOCK_USERS"] = "1" if include_mock_users else "0"

    seed_availability_value = os.getenv("SEED_AVAILABILITY")
    auto_default_message: Optional[str] = None
    if mode in {"stg", "int"} and (seed_availability_value is None or seed_availability_value.strip() == ""):
        os.environ["SEED_AVAILABILITY"] = "1"
        auto_default_message = "[seed] defaulting SEED_AVAILABILITY=1 for stg/int when --seed-all is used"

    env_snapshot = build_env_snapshot(mode)
    env_json = snapshot_to_json(env_snapshot)
    print(env_json)
    if auto_default_message:
        print(auto_default_message)
    if mock_default_message:
        print(mock_default_message)
    info(
        "seed",
        f"Inputs: target={mode} seed_all={1 if args.seed_all else 0} include_mock_users={1 if include_mock_users else 0}",
    )

    info("db", f"Using URL for migrations: {redact(db_url)}")
    if seed_db_url != db_url:
        info("db", f"Using seed connection override: {redact(seed_db_url)}")

    seed_availability_enabled = os.getenv("SEED_AVAILABILITY", "0").lower() in {"1", "true", "yes"}

    try:
        if args.seed_availability_only:
            if args.migrate:
                run_migrations(db_url, args.dry_run, args.migrate_tool)
            run_availability_pipeline(mode, args.dry_run)
            info(mode, "Availability pipeline complete.")
            return

        if args.seed_reviews_only:
            if args.migrate:
                run_migrations(db_url, args.dry_run, args.migrate_tool)
            try:
                run_reviews_only(args.dry_run, strict=True)
            except RuntimeError as exc:
                fail(str(exc))
            info(mode, "Review seeding complete.")
            return

        perform_mock_seed = include_mock_users

        if args.seed_all:
            pipeline_stats = run_seed_all_pipeline(
                mode=mode,
                db_url=db_url,
                seed_db_url=seed_db_url,
                migrate=args.migrate,
                dry_run=args.dry_run,
                env_snapshot=env_snapshot,
                include_mock_users=include_mock_users,
            )
            info(
                "pipeline",
                (
                    "Seed-all summary: students={students_seeded}, instructors={instructors_seeded}, "
                    "bookings={bookings_created}, reviews={reviews_created} "
                    "(reviews_skipped={reviews_skipped}), credits={credits_created}, "
                    "badges={badges_awarded}, skip_reviews={skip_reviews}"
                ).format(**pipeline_stats),
            )
        else:
            perform_system_seed = args.seed_system_only or include_mock_users
            perform_mock_seed = include_mock_users
            run_availability_step = seed_availability_enabled

            steps: List[Tuple[str, Callable[[], None]]] = []

            if args.migrate:
                steps.append(("Run database migrations", lambda: run_migrations(db_url, args.dry_run, args.migrate_tool)))
            if run_availability_step:
                steps.append(("Seed bitmap availability/backfill", lambda: run_availability_pipeline(mode, args.dry_run)))
            if perform_system_seed:
                steps.append(("Seed system data", lambda: seed_system_data(db_url, args.dry_run, mode, seed_db_url=seed_db_url)))
            if perform_mock_seed:
                steps.append(("Seed mock users, bookings, reviews", lambda: seed_mock_users(db_url, args.dry_run, mode, seed_db_url=seed_db_url)))

            if steps:
                info("pipeline", "Executing seeding pipeline in the following order:")
                for idx, (label, _) in enumerate(steps, start=1):
                    info("pipeline", f"  {idx}. {label}")
                for idx, (label, action) in enumerate(steps, start=1):
                    info("pipeline", f"[Step {idx}/{len(steps)}] {label}")
                    action()

        if (
            not args.dry_run
            and mode == "prod"
            and args.seed_all_prod
            and perform_mock_seed
        ):
            from importlib import import_module

            db_module = import_module("app.database")
            seed_module = import_module("scripts.seed_data")

            with db_module.SessionLocal() as session:
                created, existing = seed_module.seed_beta_access_for_instructors(session)
            info(
                mode,
                f"Ensured beta access for instructors (created={created}, existing={existing})",
            )

        if args.migrate or args.seed_all or args.seed_system_only or args.seed_mock_users:
            generate_embeddings(db_url, args.dry_run, mode)
            calculate_analytics(db_url, args.dry_run, mode)
            clear_cache(mode, args.dry_run)
        info(mode, "Complete!")
    except subprocess.CalledProcessError as e:
        if mode in {"prod", "preview"} and not service_db_url:
            warn("Command failed; consider setting a service-role DSN (e.g., PROD_SERVICE_DATABASE_URL) for seeding.")
        fail(f"External command failed with exit code {e.returncode}")
    except KeyboardInterrupt:
        fail("Interrupted by user", code=130)


if __name__ == "__main__":
    main()
