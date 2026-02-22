"""Tests for the BookingVideoSession satellite model."""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.booking import Booking
from app.models.booking_video_session import BookingVideoSession


def test_tablename():
    assert BookingVideoSession.__tablename__ == "booking_video_sessions"


def test_has_expected_columns():
    mapper = inspect(BookingVideoSession)
    column_names = {col.key for col in mapper.column_attrs}
    expected = {
        "id",
        "booking_id",
        "room_id",
        "room_name",
        "session_id",
        "session_started_at",
        "session_ended_at",
        "session_duration_seconds",
        "instructor_peer_id",
        "student_peer_id",
        "instructor_joined_at",
        "student_joined_at",
        "instructor_left_at",
        "student_left_at",
        "provider_metadata",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(column_names), f"Missing columns: {expected - column_names}"


def test_booking_id_is_unique():
    table = BookingVideoSession.__table__
    booking_id_col = table.c.booking_id
    # Check that at least one unique constraint covers booking_id
    assert booking_id_col.unique is True


def test_room_id_is_not_nullable():
    table = BookingVideoSession.__table__
    assert table.c.room_id.nullable is False


def test_booking_relationship_lazy_noload():
    """The video_session relationship on Booking must use lazy='noload'."""
    mapper = inspect(Booking)
    rel = mapper.relationships["video_session"]
    assert rel.lazy == "noload"
    assert rel.uselist is False
