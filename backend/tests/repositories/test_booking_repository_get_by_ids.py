"""Integration tests for BookingRepository.get_by_ids."""

from __future__ import annotations

from datetime import time, timedelta

import pytest

from app.models.booking import BookingStatus
from app.repositories.booking_repository import BookingRepository

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


@pytest.mark.integration
def test_get_by_ids_matches_individual_fetches(db, test_booking) -> None:
    repo = BookingRepository(db)

    second_booking = create_booking_pg_safe(
        db,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=test_booking.booking_date + timedelta(days=1),
        start_time=time(13, 0),
        end_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        service_name="Follow-up Lesson",
        hourly_rate=50.0,
        total_price=50.0,
        duration_minutes=60,
        meeting_location="Test Location",
        service_area="Manhattan",
        location_type="student_location",
        offset_index=99,
    )
    db.commit()

    booking_ids = [test_booking.id, second_booking.id]
    batch_bookings = {booking.id: booking for booking in repo.get_by_ids(booking_ids)}
    single_bookings = {
        booking_id: repo.get_by_id(booking_id)
        for booking_id in booking_ids
    }

    assert set(batch_bookings) == set(booking_ids)
    for booking_id in booking_ids:
        batch_booking = batch_bookings[booking_id]
        single_booking = single_bookings[booking_id]

        assert single_booking is not None
        assert batch_booking.id == single_booking.id
        assert batch_booking.instructor_service is not None
        assert single_booking.instructor_service is not None
        assert batch_booking.instructor_service.id == single_booking.instructor_service.id
