from __future__ import annotations

from datetime import time
from typing import Dict, List, Tuple

import pytest
from sqlalchemy.orm import Session
from tests.factories.booking_builders import create_booking_pg_safe
from tests.utils.availability_builders import future_week_start

from app.core.exceptions import BookingConflictException
from app.models.booking import BookingStatus
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.schemas.booking import BookingCreate
from app.services.availability_service import AvailabilityService
from app.services.booking_service import INSTRUCTOR_CONFLICT_MESSAGE, BookingService
from app.services.cache_service import CacheService


class _StubNotificationService:
    async def send_booking_confirmation(self, booking) -> bool:  # pragma: no cover - trivial
        return True

    async def send_cancellation_notification(self, booking, cancelled_by, reason=None) -> bool:  # pragma: no cover - trivial
        return True


class _StubStripeService:
    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
        pass

    def cancel_payment_intent(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
        return None

    def capture_payment_intent(self, *args, **kwargs) -> Dict[str, int]:  # pragma: no cover - trivial
        return {"amount_received": 0}

    def reverse_transfer(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
        return None


def _normalize_week_map(week_map: Dict[str, List[Dict[str, str]]]) -> List[Tuple[str, Tuple[Tuple[str, str], ...]]]:
    """Convert week availability map into a comparable structure."""
    normalized: List[Tuple[str, Tuple[Tuple[str, str], ...]]] = []
    for date_str, slots in sorted(week_map.items()):
        normalized.append(
            (
                date_str,
                tuple(sorted((slot["start_time"], slot["end_time"]) for slot in slots)),
            )
        )
    return normalized


@pytest.mark.asyncio
async def test_booking_availability_flow(monkeypatch, db: Session, test_instructor, test_student) -> None:
    instructor = test_instructor
    student = test_student

    # Force cache service into in-memory mode to exercise cache-aware paths without Redis.
    monkeypatch.setenv("AVAILABILITY_TEST_MEMORY_CACHE", "1")
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    cache_service = CacheService(db)

    availability_service = AvailabilityService(db, cache_service=cache_service)
    notification_stub = _StubNotificationService()
    booking_service = BookingService(db, notification_service=notification_stub, cache_service=cache_service)

    # Patch StripeService used within cancel_booking to avoid external calls.
    monkeypatch.setattr("app.services.stripe_service.StripeService", _StubStripeService)

    week_start = future_week_start(weeks_ahead=2)
    schedule = [
        {"date": week_start.isoformat(), "start_time": "09:00", "end_time": "10:00"},
        {"date": week_start.isoformat(), "start_time": "11:00", "end_time": "12:00"},
    ]

    await availability_service.save_week_availability(
        instructor.id,
        WeekSpecificScheduleCreate(schedule=schedule, week_start=week_start, clear_existing=True),
    )

    baseline_week = availability_service.get_week_availability(instructor.id, week_start)
    normalized_baseline = _normalize_week_map(baseline_week)

    service = instructor.instructor_profile.instructor_services[0]
    duration = service.duration_options[0]
    price = float(service.hourly_rate) * (duration / 60)
    service_name = getattr(service.catalog_entry, "name", "Test Service")

    booking_one = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=week_start,
        start_time=time(9, 0),
        end_time=time(10, 0),
        service_name=service_name,
        hourly_rate=float(service.hourly_rate),
        total_price=price,
        duration_minutes=duration,
    )
    booking_two = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=week_start,
        start_time=time(11, 0),
        end_time=time(12, 0),
        service_name=service_name,
        hourly_rate=float(service.hourly_rate),
        total_price=price,
        duration_minutes=duration,
    )
    booking_one.payment_status = "captured"
    booking_two.payment_status = "captured"
    db.commit()

    cancelled_booking = await booking_service.cancel_booking(booking_two.id, student)
    assert cancelled_booking.status == BookingStatus.CANCELLED

    db.expire_all()
    after_cancel_week = availability_service.get_week_availability(instructor.id, week_start)
    assert _normalize_week_map(after_cancel_week) == normalized_baseline

    stats = booking_service.get_booking_stats_for_instructor(instructor.id)
    assert stats["total_bookings"] == 2
    assert stats["cancelled_bookings"] == 1
    assert stats["completed_bookings"] == 0

    overlapping_request = BookingCreate(
        instructor_id=instructor.id,
        instructor_service_id=service.id,
        booking_date=week_start,
        start_time=time(9, 30),
        selected_duration=duration,
    )

    with pytest.raises(BookingConflictException) as conflict:
        await booking_service.create_booking(student, overlapping_request, selected_duration=duration)

    assert conflict.value.message == INSTRUCTOR_CONFLICT_MESSAGE

    # Ensure the original confirmed booking remains intact.
    db.refresh(booking_one)
    assert booking_one.status == BookingStatus.CONFIRMED
