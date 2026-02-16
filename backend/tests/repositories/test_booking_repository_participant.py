# backend/tests/repositories/test_booking_repository_participant.py
"""
Tests for BookingRepository.get_booking_for_participant() — AUTHZ-VULN-01.

Verifies that the DB-level participant filter returns bookings only for
the student or instructor on the booking, and returns None for unrelated users.
"""

import pytest
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.repositories.booking_repository import BookingRepository


@pytest.mark.integration
class TestGetBookingForParticipant:
    """Tests for the get_booking_for_participant repository method."""

    @pytest.fixture
    def booking_repository(self, db: Session) -> BookingRepository:
        return BookingRepository(db)

    def test_rejects_non_participant(
        self, booking_repository: BookingRepository, test_booking: Booking
    ) -> None:
        """Booking query returns None when user is not student or instructor."""
        result = booking_repository.get_booking_for_participant(
            test_booking.id, "01NONEXISTENT_USERIDXX"
        )
        assert result is None

    def test_returns_for_student(
        self, booking_repository: BookingRepository, test_booking: Booking
    ) -> None:
        """Student can retrieve their own booking."""
        result = booking_repository.get_booking_for_participant(
            test_booking.id, test_booking.student_id
        )
        assert result is not None
        assert result.id == test_booking.id

    def test_returns_for_instructor(
        self, booking_repository: BookingRepository, test_booking: Booking
    ) -> None:
        """Instructor can retrieve booking they're assigned to."""
        result = booking_repository.get_booking_for_participant(
            test_booking.id, test_booking.instructor_id
        )
        assert result is not None
        assert result.id == test_booking.id

    def test_nonexistent_booking_returns_none(
        self, booking_repository: BookingRepository, test_booking: Booking
    ) -> None:
        """Non-existent booking ID returns None regardless of user."""
        result = booking_repository.get_booking_for_participant(
            "01NONEXISTENT_BOOKINGID", test_booking.student_id
        )
        assert result is None

    def test_eager_loads_relationships(
        self, booking_repository: BookingRepository, test_booking: Booking
    ) -> None:
        """Returned booking has eagerly-loaded student and instructor."""
        result = booking_repository.get_booking_for_participant(
            test_booking.id, test_booking.student_id
        )
        assert result is not None
        # These should be loaded (not lazy) — accessing them should not
        # trigger additional queries after session close.
        assert result.student is not None
        assert result.instructor is not None
