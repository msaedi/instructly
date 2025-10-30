from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable
from unittest.mock import Mock

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.availability import AvailabilitySlot
from app.services.retention_service import RetentionService

try:  # pragma: no cover - compatibility when running from backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


OLDER_THAN = 45
CUTOFF_DAYS = 30
NOW = datetime.now(timezone.utc)
OLD_TS = NOW - timedelta(days=OLDER_THAN)
RECENT_TS = NOW - timedelta(days=10)


def _ensure_deleted_at_column(db: Session, table: str) -> None:
    inspector = inspect(db.bind)
    columns = {col["name"] for col in inspector.get_columns(table)}
    if "deleted_at" in columns:
        return

    column_type = "TIMESTAMPTZ" if db.bind.dialect.name == "postgresql" else "TIMESTAMP"
    db.execute(text(f"ALTER TABLE {table} ADD COLUMN deleted_at {column_type}"))
    db.commit()


def _count_deleted_before(db: Session, table: str, cutoff: datetime) -> int:
    query = text(
        f"SELECT COUNT(*) FROM {table} "
        "WHERE deleted_at IS NOT NULL AND deleted_at < :cutoff"
    )
    return int(db.execute(query, {"cutoff": cutoff}).scalar() or 0)


def _count_deleted_after(db: Session, table: str, cutoff: datetime) -> int:
    query = text(
        f"SELECT COUNT(*) FROM {table} "
        "WHERE deleted_at IS NOT NULL AND deleted_at >= :cutoff"
    )
    return int(db.execute(query, {"cutoff": cutoff}).scalar() or 0)


@pytest.mark.integration
def test_purge_soft_deleted_rows(
    db: Session, test_instructor, test_student, test_instructor_2
) -> None:
    instructor = test_instructor
    student = test_student
    secondary_instructor = test_instructor_2

    # Ensure optional tables expose deleted_at column for the test database.
    for table in ("instructor_services", "bookings", "user_favorites"):
        _ensure_deleted_at_column(db, table)

    # Availability slots — create soft deleted rows (old + recent) for the instructor.
    old_slot = AvailabilitySlot(
        instructor_id=instructor.id,
        specific_date=date.today(),
        start_time=time(hour=9, minute=0),
        end_time=time(hour=10, minute=0),
        deleted_at=OLD_TS,
    )
    recent_slot = AvailabilitySlot(
        instructor_id=instructor.id,
        specific_date=date.today(),
        start_time=time(hour=11, minute=0),
        end_time=time(hour=12, minute=0),
        deleted_at=RECENT_TS,
    )
    db.add_all([old_slot, recent_slot])
    db.commit()

    # Instructor services — mark one service as old soft delete, keep another recent.
    services = (
        db.execute(
            text(
                "SELECT id FROM instructor_services "
                "WHERE instructor_profile_id = :profile_id "
                "ORDER BY id"
            ),
            {"profile_id": instructor.instructor_profile.id},
        )
        .scalars()
        .all()
    )
    assert len(services) >= 2, "test instructor fixture should provide at least two services"
    db.execute(
        text(
            "UPDATE instructor_services "
            "SET deleted_at = :deleted_at, is_active = false "
            "WHERE id = :service_id"
        ),
        {"service_id": services[0], "deleted_at": OLD_TS},
    )
    db.execute(
        text(
            "UPDATE instructor_services "
            "SET deleted_at = :deleted_at, is_active = false "
            "WHERE id = :service_id"
        ),
        {"service_id": services[1], "deleted_at": RECENT_TS},
    )
    db.commit()

    # Bookings — create two bookings then soft delete via deleted_at column.
    booking_date = date.today() + timedelta(days=7)
    booking_one = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=services[0],
        booking_date=booking_date,
        start_time=time(13, 0),
        end_time=time(14, 0),
        allow_overlap=True,
        service_name="Retention Test",
        hourly_rate=50.0,
        total_price=75.0,
        duration_minutes=60,
    )
    booking_two = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=services[1],
        booking_date=booking_date + timedelta(days=1),
        start_time=time(15, 0),
        end_time=time(16, 0),
        allow_overlap=True,
        service_name="Retention Test",
        hourly_rate=50.0,
        total_price=75.0,
        duration_minutes=60,
    )
    db.commit()
    db.execute(
        text("UPDATE bookings SET deleted_at = :ts WHERE id = :booking_id"),
        {"booking_id": booking_one.id, "ts": OLD_TS},
    )
    db.execute(
        text("UPDATE bookings SET deleted_at = :ts WHERE id = :booking_id"),
        {"booking_id": booking_two.id, "ts": RECENT_TS},
    )
    db.commit()

    # Favorites — insert soft deleted records manually.
    db.execute(
        text(
            "INSERT INTO user_favorites (id, student_id, instructor_id, created_at, deleted_at) "
            "VALUES (:id, :student_id, :instructor_id, :created_at, :deleted_at)"
        ),
        {
            "id": generate_ulid(),
            "student_id": student.id,
            "instructor_id": instructor.id,
            "created_at": NOW,
            "deleted_at": OLD_TS,
        },
    )
    db.execute(
        text(
            "INSERT INTO user_favorites (id, student_id, instructor_id, created_at, deleted_at) "
            "VALUES (:id, :student_id, :instructor_id, :created_at, :deleted_at)"
        ),
        {
            "id": generate_ulid(),
            "student_id": student.id,
            "instructor_id": secondary_instructor.id,
            "created_at": NOW,
            "deleted_at": RECENT_TS,
        },
    )
    db.commit()

    cutoff = NOW - timedelta(days=CUTOFF_DAYS)
    cache_mock = Mock()
    cache_mock.clear_prefix = Mock(return_value=0)

    retention = RetentionService(db, cache_service=cache_mock)

    # Dry run should not delete rows but should report the counts.
    dry_summary = retention.purge_soft_deleted(
        older_than_days=CUTOFF_DAYS,
        chunk_size=10,
        dry_run=True,
    )

    assert dry_summary["availability_slots"]["eligible"] == 1
    assert dry_summary["instructor_services"]["eligible"] == 1
    assert dry_summary["bookings"]["eligible"] == 1
    assert dry_summary["user_favorites"]["eligible"] == 1

    assert _count_deleted_before(db, "availability_slots", cutoff) == 1
    assert _count_deleted_before(db, "instructor_services", cutoff) == 1
    assert _count_deleted_before(db, "bookings", cutoff) == 1
    assert _count_deleted_before(db, "user_favorites", cutoff) == 1

    cache_mock.clear_prefix.reset_mock()

    # Real purge removes old rows while leaving recent ones untouched.
    purge_summary = retention.purge_soft_deleted(
        older_than_days=CUTOFF_DAYS,
        chunk_size=10,
        dry_run=False,
    )

    assert purge_summary["availability_slots"]["deleted"] == 1
    assert purge_summary["instructor_services"]["deleted"] == 1
    assert purge_summary["bookings"]["deleted"] == 1
    assert purge_summary["user_favorites"]["deleted"] == 1

    assert _count_deleted_before(db, "availability_slots", cutoff) == 0
    assert _count_deleted_before(db, "instructor_services", cutoff) == 0
    assert _count_deleted_before(db, "bookings", cutoff) == 0
    assert _count_deleted_before(db, "user_favorites", cutoff) == 0

    assert _count_deleted_after(db, "availability_slots", cutoff) == 1
    assert _count_deleted_after(db, "instructor_services", cutoff) == 1
    assert _count_deleted_after(db, "bookings", cutoff) == 1
    assert _count_deleted_after(db, "user_favorites", cutoff) == 1

    called_prefixes = [call.args[0] for call in cache_mock.clear_prefix.call_args_list]

    def assert_prefixes(expected: Iterable[str]) -> None:
        for prefix in expected:
            assert prefix in called_prefixes

    assert_prefixes(["avail:", "week:", "conf:", "public_availability:", "slot:"])
    assert_prefixes(
        [
            "catalog:services:",
            "catalog:top-services:",
            "catalog:all-services",
            "catalog:kids-available",
            "svc:",
        ]
    )
    assert_prefixes(
        [
            "booking_stats:",
            "booking:get_student_bookings:",
            "booking:get_instructor_bookings:",
            "bookings:date:",
            "user_bookings:",
            "instructor_stats:",
        ]
    )
    assert_prefixes(["favorites:"])
