# backend/tests/unit/test_subtract_algorithm.py
"""
Test the subtraction algorithm in compute_public_availability.

This tests the specific bug reported: booking at 11:30-12:00 should NOT
wipe out afternoon availability (14:00-24:00).
"""
from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import seed_day
from tests.utils.booking_timezone import booking_timezone_fields

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService
from app.services.availability_service import AvailabilityService
from app.utils.time_utils import time_to_minutes


def _configure_profile(db: Session, instructor_id: str) -> InstructorProfile:
    """Set min_advance_booking_hours and buffer_time to 0 for predictable tests."""
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).one()
    profile.min_advance_booking_hours = 0
    profile.buffer_time_minutes = 0
    db.flush()
    return profile


def _get_active_service(db: Session, profile_id: int) -> InstructorService:
    """Get an active service for the instructor."""
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile_id,
            InstructorService.is_active == True,
        )
        .first()
    )
    if service is None:
        raise RuntimeError("Active instructor service not found for test")
    return service


def _create_booking(
    db: Session,
    *,
    instructor_id: str,
    student_id: str,
    service: InstructorService,
    booking_date: date,
    start_time: time,
    end_time: time,
    lesson_timezone: str,
) -> Booking:
    """Create a CONFIRMED booking."""
    duration_minutes = time_to_minutes(end_time, is_end_time=True) - time_to_minutes(
        start_time, is_end_time=False
    )
    tz_fields = booking_timezone_fields(
        booking_date, start_time, end_time, instructor_timezone=lesson_timezone
    )
    # tz_fields includes lesson_timezone, so don't pass it separately
    booking = Booking(
        id=generate_ulid(),
        instructor_id=instructor_id,
        student_id=student_id,
        instructor_service_id=service.id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration_minutes,
        status=BookingStatus.CONFIRMED,
        service_name=service.catalog_entry.name if service.catalog_entry else "Service",
        hourly_rate=service.hourly_rate,
        total_price=service.hourly_rate,
        **tz_fields,
    )
    db.add(booking)
    db.flush()
    return booking


def _clear_test_bookings(db: Session, instructor_id: str, target_date: date) -> None:
    """Clear all bookings for the instructor on the given date."""
    db.query(Booking).filter(
        Booking.instructor_id == instructor_id,
        Booking.booking_date == target_date,
    ).delete()
    db.flush()


class TestSubtractAlgorithm:
    """Test subtraction algorithm handles various booking scenarios."""

    def test_booking_at_end_of_morning_preserves_afternoon(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability: 09:00-12:00, 14:00-24:00
        Booking: 11:30-12:00
        Expected: 09:00-11:30, 14:00-24:00 (afternoon preserved)

        This is the specific bug reported: a booking at 11:30-12:00
        should NOT affect the afternoon availability (14:00-24:00).
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today() + timedelta(days=7)  # Future date

        # Clear existing bookings for this date
        _clear_test_bookings(db, test_instructor.id, target_date)

        # Seed availability: 09:00-12:00 and 14:00-24:00
        seed_day(db, test_instructor.id, target_date, [
            ("09:00", "12:00"),
            ("14:00", "24:00"),
        ])

        # Create booking at 11:30-12:00
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(11, 30),
            end_time=time(12, 0),
            lesson_timezone=lesson_timezone,
        )

        # Compute availability
        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )

        slots = result.get(target_date.isoformat(), [])

        # Should have 09:00-11:30 and 14:00-00:00 (00:00 represents midnight/24:00)
        expected = [(time(9, 0), time(11, 30)), (time(14, 0), time(0, 0))]
        assert slots == expected, f"Expected {expected}, got {slots}"

    def test_booking_in_middle_splits_interval(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability: 09:00-17:00
        Booking: 12:00-13:00
        Expected: 09:00-12:00, 13:00-17:00
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today() + timedelta(days=7)

        _clear_test_bookings(db, test_instructor.id, target_date)
        seed_day(db, test_instructor.id, target_date, [("09:00", "17:00")])
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(12, 0),
            end_time=time(13, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result.get(target_date.isoformat(), [])

        expected = [(time(9, 0), time(12, 0)), (time(13, 0), time(17, 0))]
        assert slots == expected, f"Expected {expected}, got {slots}"

    def test_multiple_bookings_preserve_gaps(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability: 09:00-18:00
        Bookings: 10:00-11:00, 14:00-15:00
        Expected: 09:00-10:00, 11:00-14:00, 15:00-18:00
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today() + timedelta(days=7)

        _clear_test_bookings(db, test_instructor.id, target_date)
        seed_day(db, test_instructor.id, target_date, [("09:00", "18:00")])
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
            lesson_timezone=lesson_timezone,
        )
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result.get(target_date.isoformat(), [])

        expected = [
            (time(9, 0), time(10, 0)),
            (time(11, 0), time(14, 0)),
            (time(15, 0), time(18, 0)),
        ]
        assert slots == expected, f"Expected {expected}, got {slots}"

    def test_booking_at_midnight_boundary(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability: 22:00-24:00
        Booking: 22:30-23:00
        Expected: 22:00-22:30, 23:00-00:00
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today() + timedelta(days=7)

        _clear_test_bookings(db, test_instructor.id, target_date)
        seed_day(db, test_instructor.id, target_date, [("22:00", "24:00")])
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(22, 30),
            end_time=time(23, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result.get(target_date.isoformat(), [])

        expected = [(time(22, 0), time(22, 30)), (time(23, 0), time(0, 0))]
        assert slots == expected, f"Expected {expected}, got {slots}"

    def test_disjoint_intervals_unaffected(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability: 09:00-12:00, 14:00-17:00
        Booking: 15:00-16:00 (only affects second interval)
        Expected: 09:00-12:00, 14:00-15:00, 16:00-17:00
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today() + timedelta(days=7)

        _clear_test_bookings(db, test_instructor.id, target_date)
        seed_day(db, test_instructor.id, target_date, [
            ("09:00", "12:00"),
            ("14:00", "17:00"),
        ])
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(15, 0),
            end_time=time(16, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result.get(target_date.isoformat(), [])

        expected = [
            (time(9, 0), time(12, 0)),
            (time(14, 0), time(15, 0)),
            (time(16, 0), time(17, 0)),
        ]
        assert slots == expected, f"Expected {expected}, got {slots}"

    def test_booking_consumes_entire_interval(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability: 09:00-10:00, 14:00-15:00
        Booking: 09:00-10:00 (consumes first interval entirely)
        Expected: 14:00-15:00 (second interval remains)
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today() + timedelta(days=7)

        _clear_test_bookings(db, test_instructor.id, target_date)
        seed_day(db, test_instructor.id, target_date, [
            ("09:00", "10:00"),
            ("14:00", "15:00"),
        ])
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result.get(target_date.isoformat(), [])

        expected = [(time(14, 0), time(15, 0))]
        assert slots == expected, f"Expected {expected}, got {slots}"

    def test_last_slot_of_day_does_not_corrupt_earlier_slots(
        self, db: Session, test_instructor, test_student
    ):
        """
        REGRESSION: Adding 11:30 PM - midnight must not affect earlier slots.

        Availability: 17:00-18:00, 21:00-22:00, 23:30-24:00
        No bookings
        Expected output: All three windows present

        Bug: Adding 23:30-24:00 was causing 17:00-18:00 and 21:00-22:00 to disappear
        """
        _configure_profile(db, test_instructor.id)
        target_date = date.today() + timedelta(days=7)

        _clear_test_bookings(db, test_instructor.id, target_date)

        # Set availability with the last slot of day (23:30-24:00)
        seed_day(db, test_instructor.id, target_date, [
            ("17:00", "18:00"),
            ("21:00", "22:00"),
            ("23:30", "24:00"),
        ])

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result.get(target_date.isoformat(), [])

        # All three windows should be present
        expected = [
            (time(17, 0), time(18, 0)),
            (time(21, 0), time(22, 0)),
            (time(23, 30), time(0, 0)),  # 00:00 represents midnight/24:00
        ]
        assert slots == expected, f"Expected {expected}, got {slots}"

    def test_last_slot_with_booking_preserves_other_slots(
        self, db: Session, test_instructor, test_student
    ):
        """
        Availability: 17:00-18:00, 21:00-24:00 (includes 23:30-24:00)
        Booking: 22:00-23:00
        Expected: 17:00-18:00, 21:00-22:00, 23:00-00:00

        The midnight window should not corrupt earlier availability.
        """
        profile = _configure_profile(db, test_instructor.id)
        service = _get_active_service(db, profile.id)
        lesson_timezone = test_instructor.timezone or "America/New_York"
        target_date = date.today() + timedelta(days=7)

        _clear_test_bookings(db, test_instructor.id, target_date)

        # Set availability including slot up to midnight
        seed_day(db, test_instructor.id, target_date, [
            ("17:00", "18:00"),
            ("21:00", "24:00"),
        ])

        # Booking in the evening
        _create_booking(
            db,
            instructor_id=test_instructor.id,
            student_id=test_student.id,
            service=service,
            booking_date=target_date,
            start_time=time(22, 0),
            end_time=time(23, 0),
            lesson_timezone=lesson_timezone,
        )

        availability_service = AvailabilityService(db)
        result = availability_service.compute_public_availability(
            test_instructor.id, target_date, target_date
        )
        slots = result.get(target_date.isoformat(), [])

        expected = [
            (time(17, 0), time(18, 0)),
            (time(21, 0), time(22, 0)),
            (time(23, 0), time(0, 0)),
        ]
        assert slots == expected, f"Expected {expected}, got {slots}"
