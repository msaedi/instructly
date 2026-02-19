"""Integration tests for BookingRepository.get_video_no_show_candidates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.booking import BookingStatus
from app.models.booking_video_session import BookingVideoSession
from app.repositories.booking_repository import BookingRepository

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _create_online_confirmed_booking(
    db,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    start_utc: datetime,
):
    return create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=start_utc.date(),
        start_time=start_utc.time().replace(microsecond=0),
        end_time=(start_utc + timedelta(minutes=60)).time().replace(microsecond=0),
        status=BookingStatus.CONFIRMED,
        location_type="online",
        duration_minutes=60,
        service_name="Video Lesson",
        hourly_rate=50.0,
        total_price=50.0,
        meeting_location="Online",
        service_area="Manhattan",
        instructor_timezone="UTC",
        allow_overlap=True,
    )


@pytest.mark.integration
def test_includes_booking_without_video_session_row(db, test_booking) -> None:
    """LEFT JOIN should include mutual no-show candidates with no video_session row."""
    repo = BookingRepository(db)
    now = datetime.now(timezone.utc)
    start_utc = now - timedelta(minutes=30)
    sql_cutoff = now - timedelta(minutes=8)

    booking = _create_online_confirmed_booking(
        db,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        start_utc=start_utc,
    )
    db.commit()

    rows = repo.get_video_no_show_candidates(sql_cutoff)

    matching = [(b, vs) for b, vs in rows if b.id == booking.id]
    assert len(matching) == 1
    _, video_session = matching[0]
    assert video_session is None


@pytest.mark.integration
def test_excludes_booking_with_both_participants_joined(db, test_booking) -> None:
    """Candidates should exclude bookings where both instructor and student joined."""
    repo = BookingRepository(db)
    now = datetime.now(timezone.utc)
    sql_cutoff = now - timedelta(minutes=8)

    no_session_booking = _create_online_confirmed_booking(
        db,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        start_utc=now - timedelta(minutes=30),
    )

    joined_booking = _create_online_confirmed_booking(
        db,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        start_utc=now - timedelta(minutes=120),
    )
    db.add(
        BookingVideoSession(
            booking_id=joined_booking.id,
            room_id="room_joined",
            room_name=f"lesson-{joined_booking.id}",
            instructor_joined_at=now - timedelta(minutes=35),
            student_joined_at=now - timedelta(minutes=34),
        )
    )
    db.commit()

    rows = repo.get_video_no_show_candidates(sql_cutoff)
    row_ids = {booking.id for booking, _video_session in rows}

    assert no_session_booking.id in row_ids
    assert joined_booking.id not in row_ids
