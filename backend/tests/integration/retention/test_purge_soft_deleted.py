from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import seed_day

from app.core.config import settings
from app.models.availability_day import AvailabilityDay
from app.models.service_catalog import InstructorService
from app.services.retention_service import RetentionService

try:  # pragma: no cover - compatibility when running from backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _configure_retention(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    ttl: int = 180,
    keep_recent: int = 30,
    dry_run: bool = False,
) -> None:
    monkeypatch.setattr(settings, "availability_retention_enabled", enabled, raising=False)
    monkeypatch.setattr(settings, "availability_retention_days", ttl, raising=False)
    monkeypatch.setattr(settings, "availability_retention_keep_recent_days", keep_recent, raising=False)
    monkeypatch.setattr(settings, "availability_retention_dry_run", dry_run, raising=False)


def _day_exists(db: Session, instructor_id: str, day_date: date) -> bool:
    return (
        db.query(AvailabilityDay)
        .filter(AvailabilityDay.instructor_id == instructor_id, AvailabilityDay.day_date == day_date)
        .one_or_none()
        is not None
    )


def _service_id(db: Session, instructor_id: str) -> str:
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile.has(user_id=instructor_id),
            InstructorService.is_active.is_(True),
        )
        .order_by(InstructorService.id)
        .first()
    )
    assert service is not None, "test instructor fixture must expose at least one service"
    return service.id


@pytest.mark.integration
def test_purge_availability_days_respects_policy(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    test_instructor,
    test_student,
) -> None:
    _configure_retention(monkeypatch, enabled=True, ttl=180, keep_recent=30, dry_run=False)

    instructor_id = test_instructor.id
    student_id = test_student.id
    today = date.today()
    old_orphan_day = today - timedelta(days=200)
    old_with_booking = today - timedelta(days=190)
    recent_orphan_day = today - timedelta(days=10)
    future_day = today + timedelta(days=10)

    for target in (old_orphan_day, old_with_booking, recent_orphan_day, future_day):
        seed_day(db, instructor_id, target, [("09:00:00", "10:00:00")])

    create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=_service_id(db, instructor_id),
        booking_date=old_with_booking,
        start_time=time(9, 0),
        end_time=time(10, 0),
        allow_overlap=True,
        service_name="Retention keeps booked days",
        hourly_rate=60.0,
        total_price=60.0,
        duration_minutes=60,
    )
    db.commit()

    service = RetentionService(db)
    summary = service.purge_availability_days(today=today)

    assert summary["purged_days"] == 1
    assert summary["inspected_days"] == 1
    assert not _day_exists(db, instructor_id, old_orphan_day)
    assert _day_exists(db, instructor_id, old_with_booking)
    assert _day_exists(db, instructor_id, recent_orphan_day)
    assert _day_exists(db, instructor_id, future_day)
