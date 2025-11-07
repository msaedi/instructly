# backend/tests/integration/services/test_booking_race_protection.py
"""
Concurrency and cancellation safeguards for BookingService.

These tests ensure that:
• Overlapping bookings for the same instructor are rejected when attempted concurrently.
• Students cannot hold overlapping bookings across instructors.
• Cancelling a booking frees the protected range for future reservations.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BookingConflictException
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog
from app.models.user import User
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.schemas.booking import BookingCreate
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    yield


def _get_service_with_duration(db: Session, instructor: User, duration_minutes: int) -> Service:
    """Fetch an active instructor service that supports the requested duration."""
    profile = db.query(InstructorProfile).filter_by(user_id=instructor.id).first()
    assert profile is not None, "Instructor profile not found"

    services = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active.is_(True))
        .all()
    )
    if not services:
        catalog = (
            db.query(ServiceCatalog)
            .filter(ServiceCatalog.is_active == True)  # noqa: E712
            .first()
        )
        assert catalog is not None, "Service catalog not seeded"
        new_service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog.id,
            hourly_rate=120.0,
            duration_options=[60],
            is_active=True,
        )
        db.add(new_service)
        db.flush()
        services = [new_service]
    for svc in services:
        options = getattr(svc, "duration_options", []) or []
        if duration_minutes in options:
            return svc
    return services[0]


async def _seed_single_day_availability(
    availability_service: AvailabilityService,
    instructor_id: str,
    target_date: date,
    windows: Iterable[tuple[time, time]],
) -> None:
    """Seed availability windows for a single day using the week-based API."""
    week_start = target_date - timedelta(days=target_date.weekday())
    schedule = [
        {
            "date": target_date.isoformat(),
            "start_time": window_start.strftime("%H:%M"),
            "end_time": window_end.strftime("%H:%M"),
        }
        for window_start, window_end in windows
    ]
    payload = WeekSpecificScheduleCreate(
        week_start=week_start,
        clear_existing=True,
        schedule=schedule,
    )
    await availability_service.save_week_availability(instructor_id, payload)


def _build_booking_payload(
    instructor_id: str,
    service_id: str,
    target_date: date,
    start_time_value: time,
    duration_minutes: int,
) -> BookingCreate:
    """Construct a BookingCreate payload with common defaults."""
    return BookingCreate(
        instructor_id=instructor_id,
        instructor_service_id=service_id,
        booking_date=target_date,
        start_time=start_time_value,
        selected_duration=duration_minutes,
        location_type="instructor_location",
        meeting_location="Test Location",
    )


class TestBookingRaceProtection:
    """Concurrency protections for booking creation."""

    @pytest.mark.asyncio
    async def test_two_concurrent_bookings_for_same_instructor_only_one_succeeds(
        self,
        db: Session,
        test_student: User,
        test_instructor: User,
        mock_notification_service,
    ):
        booking_service = BookingService(db, mock_notification_service)
        availability_service = AvailabilityService(db)

        service = _get_service_with_duration(db, test_instructor, duration_minutes=60)
        service.hourly_rate = 120.0
        db.flush()
        target_date = date.today() + timedelta(days=10)
        start_slot = time(15, 0)

        await _seed_single_day_availability(
            availability_service,
            test_instructor.id,
            target_date,
            windows=[(time(12, 0), time(18, 0))],
        )

        base_payload = _build_booking_payload(
            instructor_id=test_instructor.id,
            service_id=service.id,
            target_date=target_date,
            start_time_value=start_slot,
            duration_minutes=60,
        )

        async def attempt_booking() -> Booking:
            payload = base_payload.model_copy()
            return await booking_service.create_booking_with_payment_setup(
                student=test_student,
                booking_data=payload,
                selected_duration=payload.selected_duration,
            )

        results = await asyncio.gather(
            asyncio.create_task(attempt_booking()),
            asyncio.create_task(attempt_booking()),
            return_exceptions=True,
        )

        successes = [result for result in results if isinstance(result, Booking)]
        conflicts = [result for result in results if isinstance(result, BookingConflictException)]

        assert len(successes) == 1, f"Expected one success, got: {results}"
        assert len(conflicts) == 1, f"Expected one conflict, got: {results}"

        persisted = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == test_instructor.id,
                Booking.booking_date == target_date,
                Booking.start_time == start_slot,
            )
            .all()
        )
        assert len(persisted) == 1

    @pytest.mark.asyncio
    async def test_student_cannot_overlap_self_concurrently(
        self,
        db: Session,
        test_student: User,
        test_instructor: User,
        test_instructor_2: User,
        mock_notification_service,
    ):
        booking_service = BookingService(db, mock_notification_service)
        availability_service = AvailabilityService(db)

        target_date = date.today() + timedelta(days=12)
        start_slot = time(10, 0)

        instructor_one_service = _get_service_with_duration(db, test_instructor, duration_minutes=60)
        instructor_two_service = _get_service_with_duration(db, test_instructor_2, duration_minutes=60)
        instructor_one_service.hourly_rate = 120.0
        instructor_two_service.hourly_rate = 120.0
        db.flush()

        await _seed_single_day_availability(
            availability_service,
            test_instructor.id,
            target_date,
            windows=[(time(9, 0), time(12, 0))],
        )
        await _seed_single_day_availability(
            availability_service,
            test_instructor_2.id,
            target_date,
            windows=[(time(9, 0), time(12, 0))],
        )

        payload_one = _build_booking_payload(
            instructor_id=test_instructor.id,
            service_id=instructor_one_service.id,
            target_date=target_date,
            start_time_value=start_slot,
            duration_minutes=60,
        )
        payload_two = _build_booking_payload(
            instructor_id=test_instructor_2.id,
            service_id=instructor_two_service.id,
            target_date=target_date,
            start_time_value=start_slot,
            duration_minutes=60,
        )

        async def attempt(payload: BookingCreate) -> Booking:
            request = payload.model_copy()
            return await booking_service.create_booking_with_payment_setup(
                student=test_student,
                booking_data=request,
                selected_duration=request.selected_duration,
            )

        results = await asyncio.gather(
            asyncio.create_task(attempt(payload_one)),
            asyncio.create_task(attempt(payload_two)),
            return_exceptions=True,
        )

        successes = [result for result in results if isinstance(result, Booking)]
        conflicts = [result for result in results if isinstance(result, BookingConflictException)]

        assert len(successes) == 1, f"Expected exactly one success, got: {results}"
        assert len(conflicts) == 1, f"Expected exactly one conflict, got: {results}"

        student_bookings = db.query(Booking).filter(Booking.student_id == test_student.id).all()
        assert len(student_bookings) == 1

    @pytest.mark.asyncio
    async def test_canceled_booking_frees_span(
        self,
        db: Session,
        test_student: User,
        test_instructor: User,
        mock_notification_service,
    ):
        booking_service = BookingService(db, mock_notification_service)
        availability_service = AvailabilityService(db)

        service = _get_service_with_duration(db, test_instructor, duration_minutes=60)
        service.hourly_rate = 120.0
        db.flush()
        target_date = date.today() + timedelta(days=14)
        start_slot = time(17, 0)

        await _seed_single_day_availability(
            availability_service,
            test_instructor.id,
            target_date,
            windows=[(time(15, 0), time(20, 0))],
        )

        initial_payload = _build_booking_payload(
            instructor_id=test_instructor.id,
            service_id=service.id,
            target_date=target_date,
            start_time_value=start_slot,
            duration_minutes=60,
        )

        original_booking = await booking_service.create_booking_with_payment_setup(
            student=test_student,
            booking_data=initial_payload.model_copy(),
            selected_duration=initial_payload.selected_duration,
        )

        # Mark the booking as cancelled to release the exclusion span.
        db.refresh(original_booking)
        original_booking.status = BookingStatus.CANCELLED
        original_booking.cancelled_at = datetime.now(timezone.utc)
        db.commit()

        replacement = await booking_service.create_booking_with_payment_setup(
            student=test_student,
            booking_data=initial_payload.model_copy(),
            selected_duration=initial_payload.selected_duration,
        )

        assert replacement.id != original_booking.id
        overlapping_bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == test_instructor.id,
                Booking.booking_date == target_date,
                Booking.start_time == start_slot,
            )
            .order_by(Booking.created_at)
            .all()
        )
        assert len(overlapping_bookings) == 2
        assert overlapping_bookings[0].status == BookingStatus.CANCELLED
        assert overlapping_bookings[1].status == BookingStatus.PENDING
