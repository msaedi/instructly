from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, List

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.availability import AvailabilitySlot
from app.services.cache_service import CacheService
from app.tasks.retention_tasks import purge_soft_deleted_task

try:  # pragma: no cover - compatibility when running from backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe

from tests.integration.retention.test_purge_soft_deleted import (  # noqa: E402
    _count_deleted_after,
    _count_deleted_before,
    _ensure_deleted_at_column,
)

OLDER_THAN = 45
CUTOFF_DAYS = 30
NOW = datetime.now(timezone.utc)
OLD_TS = NOW - timedelta(days=OLDER_THAN)
RECENT_TS = NOW - timedelta(days=10)


@pytest.mark.integration
def test_retention_celery_task(
    monkeypatch,
    db: Session,
    test_instructor,
    test_student,
) -> None:
    instructor = test_instructor
    student = test_student

    for table in ("instructor_services", "bookings", "user_favorites"):
        _ensure_deleted_at_column(db, table)

    old_slot = AvailabilitySlot(
        instructor_id=instructor.id,
        specific_date=date.today(),
        start_time=time(8, 0),
        end_time=time(9, 0),
        deleted_at=OLD_TS,
    )
    recent_slot = AvailabilitySlot(
        instructor_id=instructor.id,
        specific_date=date.today(),
        start_time=time(10, 0),
        end_time=time(11, 0),
        deleted_at=RECENT_TS,
    )
    db.add_all([old_slot, recent_slot])
    db.commit()

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
    assert services, "Instructor fixture should expose at least one service"

    db.execute(
        text(
            "UPDATE instructor_services "
            "SET deleted_at = :deleted_at, is_active = false "
            "WHERE id = :service_id"
        ),
        {"service_id": services[0], "deleted_at": OLD_TS},
    )
    db.commit()

    booking_date = date.today() + timedelta(days=5)
    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=services[0],
        booking_date=booking_date,
        start_time=time(13, 0),
        end_time=time(14, 0),
        allow_overlap=True,
        service_name="Retention Task Test",
        hourly_rate=45.0,
        total_price=60.0,
        duration_minutes=60,
    )
    db.commit()
    db.execute(
        text("UPDATE bookings SET deleted_at = :ts WHERE id = :booking_id"),
        {"booking_id": booking.id, "ts": OLD_TS},
    )
    db.commit()

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
    db.commit()

    cutoff = NOW - timedelta(days=CUTOFF_DAYS)
    cleared_prefixes: List[str] = []
    original_clear_prefix = CacheService.clear_prefix

    def tracking_clear_prefix(self: CacheService, prefix: str) -> int:
        cleared_prefixes.append(prefix)
        return original_clear_prefix(self, prefix)

    monkeypatch.setenv("AVAILABILITY_TEST_MEMORY_CACHE", "1")
    monkeypatch.setattr(CacheService, "clear_prefix", tracking_clear_prefix)

    result = purge_soft_deleted_task.apply(
        args=[],
        kwargs={"days": CUTOFF_DAYS, "chunk_size": 10, "dry_run": False},
    ).get()

    assert result["availability_slots"]["deleted"] == 1
    assert result["instructor_services"]["deleted"] == 1
    assert result["bookings"]["deleted"] == 1
    assert result["user_favorites"]["deleted"] == 1

    assert _count_deleted_before(db, "availability_slots", cutoff) == 0
    assert _count_deleted_before(db, "instructor_services", cutoff) == 0
    assert _count_deleted_before(db, "bookings", cutoff) == 0
    assert _count_deleted_before(db, "user_favorites", cutoff) == 0

    assert _count_deleted_after(db, "availability_slots", cutoff) == 1
    assert _count_deleted_after(db, "instructor_services", cutoff) == 0
    assert _count_deleted_after(db, "bookings", cutoff) == 0
    assert _count_deleted_after(db, "user_favorites", cutoff) == 0

    def _assert_prefixes(expected: Iterable[str]) -> None:
        for prefix in expected:
            assert any(p.startswith(prefix) for p in cleared_prefixes)

    _assert_prefixes(["avail:", "week:", "conf:", "public_availability:", "slot:"])
    _assert_prefixes(["catalog:services:", "catalog:top-services:", "svc:"])
    _assert_prefixes(["booking_stats:", "booking:get_student_bookings:", "bookings:date:"])
    _assert_prefixes(["favorites:"])
