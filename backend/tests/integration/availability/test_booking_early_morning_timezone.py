"""Tests for early morning bookings to verify timezone handling.

This test file specifically addresses a bug where _resolve_local_booking_day
incorrectly treated client-provided local times as UTC, causing date shifting
for early morning bookings (midnight-5am).

Bug: Client sends booking_date=Dec 24, start_time=01:00 (in instructor's local TZ)
     Code interpreted as 01:00 UTC, converted to instructor TZ (EST = UTC-5)
     Result: Looked up availability for Dec 23 instead of Dec 24 → booking rejected

Fix: Client always sends times in instructor's local timezone. The booking_date
     IS the correct date for availability lookup - no conversion needed.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService
from app.models.user import User
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService
from app.utils.bitset import bits_from_windows


def _next_monday(reference: date) -> date:
    """Return the next Monday strictly after the reference date."""
    days_ahead = (7 - reference.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return reference + timedelta(days=days_ahead)


# No Stripe mocking needed - tests only validate availability bit checking


@pytest.fixture
def instructor_with_timezone(db: Session, test_instructor: User) -> User:
    """Ensure test instructor has America/New_York timezone."""
    test_instructor.timezone = "America/New_York"
    db.add(test_instructor)
    db.commit()
    db.refresh(test_instructor)
    return test_instructor


@pytest.fixture
def instructor_service(db: Session, instructor_with_timezone: User) -> InstructorService:
    """Get or create an active instructor service."""
    profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()
    assert profile is not None, "Expected instructor profile"

    service = (
        db.query(InstructorService)
        .filter_by(instructor_profile_id=profile.id, is_active=True)
        .first()
    )
    assert service is not None, "Expected active instructor service"
    return service


def _create_booking_data(
    instructor_id: str,
    service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> BookingCreate:
    """Create a BookingCreate schema for testing."""
    return BookingCreate(
        instructor_id=instructor_id,
        instructor_service_id=service_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        selected_duration=60,
        location_type="remote",
    )


class TestEarlyMorningBookingTimezone:
    """Tests for early morning bookings (midnight-5am) that triggered the timezone bug."""

    def test_1am_booking_succeeds_with_availability(
        self,
        db: Session,
        instructor_with_timezone: User,
        instructor_service: InstructorService,
        test_student: User,
    ) -> None:
        """Booking at 1am-2am should succeed when availability exists for that slot.

        This is the primary regression test for the timezone bug.

        Bug scenario:
        - Availability set for Dec 24 01:00-03:00
        - Student tries to book Dec 24 01:00-02:00
        - OLD (buggy): Code treats 01:00 as UTC, converts to EST → Dec 23 20:00
        - OLD (buggy): Looks up Dec 23 availability → not found → REJECTED
        - NEW (fixed): Uses booking_date directly → Dec 24 → FOUND → SUCCESS
        """
        target_day = _next_monday(date.today()) + timedelta(days=3)

        # Set up availability for 01:00-03:00 on target day
        repo = AvailabilityDayRepository(db)
        early_morning_bits = bits_from_windows([("01:00:00", "03:00:00")])
        repo.upsert_week(instructor_with_timezone.id, [(target_day, early_morning_bits)])
        db.commit()

        # Verify bits are set
        stored_bits = repo.get_day_bits(instructor_with_timezone.id, target_day)
        assert stored_bits is not None, "Availability bits should be stored"

        # Create booking data for 01:00-02:00
        booking_data = _create_booking_data(
            instructor_id=instructor_with_timezone.id,
            service_id=instructor_service.id,
            booking_date=target_day,
            start_time=time(1, 0),
            end_time=time(2, 0),
        )

        service = BookingService(db)
        profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()

        # This should NOT raise - availability exists for 1am-2am on target_day
        # Bug caused it to look up wrong day (target_day - 1) and fail
        service._validate_against_availability_bits(booking_data, profile)
        # If we get here without exception, the test passes

    def test_10am_booking_succeeds_with_availability(
        self,
        db: Session,
        instructor_with_timezone: User,
        instructor_service: InstructorService,
    ) -> None:
        """Booking at 10am-11am should succeed (control test - not affected by bug)."""
        target_day = _next_monday(date.today()) + timedelta(days=3)

        # Set up availability for 09:00-12:00 on target day
        repo = AvailabilityDayRepository(db)
        morning_bits = bits_from_windows([("09:00:00", "12:00:00")])
        repo.upsert_week(instructor_with_timezone.id, [(target_day, morning_bits)])
        db.commit()

        booking_data = _create_booking_data(
            instructor_id=instructor_with_timezone.id,
            service_id=instructor_service.id,
            booking_date=target_day,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )

        service = BookingService(db)
        profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()

        # Should not raise
        service._validate_against_availability_bits(booking_data, profile)

    def test_11pm_booking_succeeds_with_availability(
        self,
        db: Session,
        instructor_with_timezone: User,
        instructor_service: InstructorService,
    ) -> None:
        """Booking at 11pm-midnight should succeed (edge case - end of day)."""
        target_day = _next_monday(date.today()) + timedelta(days=3)

        # Set up availability for 22:00-24:00 on target day
        repo = AvailabilityDayRepository(db)
        evening_bits = bits_from_windows([("22:00:00", "24:00:00")])
        repo.upsert_week(instructor_with_timezone.id, [(target_day, evening_bits)])
        db.commit()

        booking_data = _create_booking_data(
            instructor_id=instructor_with_timezone.id,
            service_id=instructor_service.id,
            booking_date=target_day,
            start_time=time(23, 0),
            end_time=time(0, 0),  # Midnight
        )

        service = BookingService(db)
        profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()

        # Should not raise
        service._validate_against_availability_bits(booking_data, profile)

    def test_2am_booking_fails_without_availability(
        self,
        db: Session,
        instructor_with_timezone: User,
        instructor_service: InstructorService,
    ) -> None:
        """Booking at 2am-3am should fail when no availability exists."""
        target_day = _next_monday(date.today()) + timedelta(days=3)

        # NO availability set for this day
        repo = AvailabilityDayRepository(db)
        repo.upsert_week(instructor_with_timezone.id, [(target_day, bytes(6))])  # Empty bits
        db.commit()

        booking_data = _create_booking_data(
            instructor_id=instructor_with_timezone.id,
            service_id=instructor_service.id,
            booking_date=target_day,
            start_time=time(2, 0),
            end_time=time(3, 0),
        )

        service = BookingService(db)
        profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()

        # Should raise because no availability
        from app.core.exceptions import BusinessRuleException
        with pytest.raises(BusinessRuleException, match="Requested time is not available"):
            service._validate_against_availability_bits(booking_data, profile)

    def test_midnight_to_1am_booking_succeeds(
        self,
        db: Session,
        instructor_with_timezone: User,
        instructor_service: InstructorService,
    ) -> None:
        """Booking at midnight (00:00-01:00) should succeed when availability exists."""
        target_day = _next_monday(date.today()) + timedelta(days=3)

        # Set up availability for 00:00-02:00 on target day
        repo = AvailabilityDayRepository(db)
        early_bits = bits_from_windows([("00:00:00", "02:00:00")])
        repo.upsert_week(instructor_with_timezone.id, [(target_day, early_bits)])
        db.commit()

        booking_data = _create_booking_data(
            instructor_id=instructor_with_timezone.id,
            service_id=instructor_service.id,
            booking_date=target_day,
            start_time=time(0, 0),
            end_time=time(1, 0),
        )

        service = BookingService(db)
        profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()

        # Should not raise
        service._validate_against_availability_bits(booking_data, profile)


class TestResolveLocalBookingDay:
    """Direct unit tests for _resolve_local_booking_day method."""

    def test_returns_booking_date_unchanged(
        self,
        db: Session,
        instructor_with_timezone: User,
        instructor_service: InstructorService,
    ) -> None:
        """_resolve_local_booking_day should return booking_date unchanged.

        The client sends booking_date in the instructor's local timezone.
        No conversion is needed - just return the date as-is.
        """
        target_day = date(2025, 12, 24)

        booking_data = _create_booking_data(
            instructor_id=instructor_with_timezone.id,
            service_id=instructor_service.id,
            booking_date=target_day,
            start_time=time(1, 0),  # 1am - would trigger bug
            end_time=time(2, 0),
        )

        service = BookingService(db)
        profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()

        result = service._resolve_local_booking_day(booking_data, profile)

        # Should return Dec 24, NOT Dec 23
        assert result == target_day, (
            f"Expected {target_day}, got {result}. "
            "Bug: 1am treated as UTC, converted to EST → wrong date"
        )

    def test_returns_booking_date_for_all_times(
        self,
        db: Session,
        instructor_with_timezone: User,
        instructor_service: InstructorService,
    ) -> None:
        """_resolve_local_booking_day should return same date for any time."""
        target_day = date(2025, 12, 24)

        # Test times that don't cross midnight (avoids schema validation issues)
        test_times = [
            (time(0, 0), time(1, 0)),    # Midnight to 1am
            (time(1, 0), time(2, 0)),    # 1am (bug trigger)
            (time(4, 30), time(5, 30)),  # 4:30am (bug trigger)
            (time(10, 0), time(11, 0)),  # 10am (safe)
            (time(14, 0), time(15, 0)),  # 2pm (safe)
            (time(22, 0), time(23, 0)),  # 10pm (edge)
        ]

        service = BookingService(db)
        profile = db.query(InstructorProfile).filter_by(user_id=instructor_with_timezone.id).first()

        for start_time, end_time in test_times:
            booking_data = _create_booking_data(
                instructor_id=instructor_with_timezone.id,
                service_id=instructor_service.id,
                booking_date=target_day,
                start_time=start_time,
                end_time=end_time,
            )

            result = service._resolve_local_booking_day(booking_data, profile)
            assert result == target_day, (
                f"For start_time={start_time}, expected {target_day}, got {result}"
            )
