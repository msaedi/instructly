"""Unit tests for video session fields in booking responses."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock

from app.schemas.booking import BookingResponse, _extract_satellite_fields

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _make_video_session(**overrides: object) -> MagicMock:
    """Create a mock BookingVideoSession with sensible defaults."""
    defaults = {
        "room_id": "rm_abc123",
        "room_name": "lesson-01BOOKING000000000000000",
        "session_id": None,
        "session_started_at": None,
        "session_ended_at": None,
        "session_duration_seconds": None,
        "instructor_peer_id": None,
        "student_peer_id": None,
        "instructor_joined_at": None,
        "student_joined_at": None,
        "instructor_left_at": None,
        "student_left_at": None,
        "provider_metadata": None,
    }
    defaults.update(overrides)
    session = MagicMock()
    for attr, val in defaults.items():
        setattr(session, attr, val)
    return session


def _make_booking(**overrides: object) -> MagicMock:
    """Create a mock Booking with all fields _extract_satellite_fields reads."""
    defaults: dict[str, object] = {
        # Core fields
        "id": "01BOOKING000000000000000000",
        "student_id": "01STUDENT0000000000000000",
        "instructor_id": "01INSTRUC000000000000000",
        "instructor_service_id": "01SERVICE000000000000000",
        "booking_date": date(2025, 6, 15),
        "start_time": time(10, 0),
        "end_time": time(11, 0),
        "service_name": "Piano",
        "hourly_rate": 50.0,
        "total_price": 50.0,
        "duration_minutes": 60,
        "status": "CONFIRMED",
        "booking_start_utc": _utc(2025, 6, 15, 14, 0),
        "booking_end_utc": _utc(2025, 6, 15, 15, 0),
        "lesson_timezone": "America/New_York",
        "instructor_tz_at_booking": "America/New_York",
        "student_tz_at_booking": "America/New_York",
        "location_type": "online",
        "location_address": None,
        "location_lat": None,
        "location_lng": None,
        "location_place_id": None,
        "service_area": "Manhattan",
        "meeting_location": None,
        "student_note": None,
        "instructor_note": None,
        "created_at": _utc(2025, 6, 10, 12, 0),
        "confirmed_at": _utc(2025, 6, 10, 12, 5),
        "completed_at": None,
        "cancelled_at": None,
        "cancelled_by_id": None,
        "cancellation_reason": None,
        "has_locked_funds": None,
        "rescheduled_from_booking_id": None,
        # Satellite relationships (lazy="noload" means they may be None)
        "no_show_detail": None,
        "lock_detail": None,
        "payment_detail": None,
        "reschedule_detail": None,
        "video_session": None,
    }
    defaults.update(overrides)
    booking = MagicMock()
    for attr, val in defaults.items():
        setattr(booking, attr, val)
    return booking


# ---------------------------------------------------------------------------
# _extract_satellite_fields: video session data extraction
# ---------------------------------------------------------------------------


class TestVideoFieldsInSatelliteExtraction:
    """Tests for video session fields in _extract_satellite_fields."""

    def test_video_fields_none_when_no_video_session(self) -> None:
        booking = _make_booking(video_session=None)
        result = _extract_satellite_fields(booking)

        assert result["video_room_id"] is None
        assert result["video_session_started_at"] is None
        assert result["video_session_ended_at"] is None
        assert result["video_session_duration_seconds"] is None
        assert result["video_instructor_joined_at"] is None
        assert result["video_student_joined_at"] is None

    def test_video_fields_populated_from_video_session(self) -> None:
        started = _utc(2025, 6, 15, 14, 0)
        ended = _utc(2025, 6, 15, 15, 0)
        i_joined = _utc(2025, 6, 15, 13, 58)
        s_joined = _utc(2025, 6, 15, 14, 1)

        vs = _make_video_session(
            room_id="rm_xyz789",
            session_started_at=started,
            session_ended_at=ended,
            session_duration_seconds=3600,
            instructor_joined_at=i_joined,
            student_joined_at=s_joined,
        )
        booking = _make_booking(video_session=vs)
        result = _extract_satellite_fields(booking)

        assert result["video_room_id"] == "rm_xyz789"
        assert result["video_session_started_at"] == started
        assert result["video_session_ended_at"] == ended
        assert result["video_session_duration_seconds"] == 3600
        assert result["video_instructor_joined_at"] == i_joined
        assert result["video_student_joined_at"] == s_joined


# ---------------------------------------------------------------------------
# _extract_satellite_fields: computed join window
# ---------------------------------------------------------------------------


class TestJoinWindowComputation:
    """Tests for can_join_lesson, join_opens_at, join_closes_at."""

    def test_can_join_true_within_window(self) -> None:
        """Inside join window → can_join_lesson=True."""
        now = datetime.now(timezone.utc)
        # Booking starts in 2 minutes — inside [T-5, T+15] window
        booking_start = now + timedelta(minutes=2)

        booking = _make_booking(
            booking_start_utc=booking_start,
            duration_minutes=60,
            location_type="online",
            status="CONFIRMED",
        )
        result = _extract_satellite_fields(booking)

        assert result["can_join_lesson"] is True
        assert result["join_opens_at"] == booking_start - timedelta(minutes=5)
        assert result["join_closes_at"] == booking_start + timedelta(minutes=15)

    def test_can_join_false_before_window(self) -> None:
        """Before join window opens → can_join_lesson=False."""
        now = datetime.now(timezone.utc)
        # Booking starts in 2 hours — well before T-5
        booking_start = now + timedelta(hours=2)

        booking = _make_booking(
            booking_start_utc=booking_start,
            duration_minutes=60,
            location_type="online",
            status="CONFIRMED",
        )
        result = _extract_satellite_fields(booking)

        assert result["can_join_lesson"] is False

    def test_can_join_false_after_window(self) -> None:
        """After join window closes → can_join_lesson=False."""
        now = datetime.now(timezone.utc)
        # 60-min lesson → grace = 15 min. Booking started 1 hour ago (past T+15)
        booking_start = now - timedelta(hours=1)

        booking = _make_booking(
            booking_start_utc=booking_start,
            duration_minutes=60,
            location_type="online",
            status="CONFIRMED",
        )
        result = _extract_satellite_fields(booking)

        assert result["can_join_lesson"] is False

    def test_can_join_none_for_in_person(self) -> None:
        """In-person booking → can_join_lesson=None."""
        now = datetime.now(timezone.utc)
        booking = _make_booking(
            location_type="student_location",
            status="CONFIRMED",
            booking_start_utc=now + timedelta(minutes=2),
            duration_minutes=60,
        )
        result = _extract_satellite_fields(booking)

        assert result["can_join_lesson"] is None
        assert result["join_opens_at"] is None
        assert result["join_closes_at"] is None

    def test_can_join_none_for_non_confirmed(self) -> None:
        """Non-confirmed booking → can_join_lesson=None."""
        now = datetime.now(timezone.utc)
        booking = _make_booking(
            location_type="online",
            status="PENDING",
            booking_start_utc=now + timedelta(minutes=2),
            duration_minutes=60,
        )
        result = _extract_satellite_fields(booking)

        assert result["can_join_lesson"] is None
        assert result["join_opens_at"] is None
        assert result["join_closes_at"] is None

    def test_completed_booking_with_video_session(self) -> None:
        """Completed booking with video session → can_join_lesson=None, video data populated."""
        i_joined = _utc(2025, 6, 15, 13, 58)
        s_joined = _utc(2025, 6, 15, 14, 1)

        vs = _make_video_session(
            room_id="rm_hist",
            session_started_at=_utc(2025, 6, 15, 14, 0),
            session_ended_at=_utc(2025, 6, 15, 15, 0),
            session_duration_seconds=3600,
            instructor_joined_at=i_joined,
            student_joined_at=s_joined,
        )
        booking = _make_booking(
            status="COMPLETED",
            location_type="online",
            video_session=vs,
            booking_start_utc=_utc(2025, 6, 15, 14, 0),
            duration_minutes=60,
        )
        result = _extract_satellite_fields(booking)

        # Join window not computed for non-confirmed
        assert result["can_join_lesson"] is None
        assert result["join_opens_at"] is None
        assert result["join_closes_at"] is None
        # Video session data still populated (viewing history)
        assert result["video_room_id"] == "rm_hist"
        assert result["video_instructor_joined_at"] == i_joined
        assert result["video_student_joined_at"] == s_joined
        assert result["video_session_duration_seconds"] == 3600

    def test_join_window_30min_lesson(self) -> None:
        """30-min lesson → grace = 7.5 min (shorter than default 15)."""
        now = datetime.now(timezone.utc)
        booking_start = now + timedelta(minutes=2)

        booking = _make_booking(
            booking_start_utc=booking_start,
            duration_minutes=30,
            location_type="online",
            status="CONFIRMED",
        )
        result = _extract_satellite_fields(booking)

        expected_opens = booking_start - timedelta(minutes=5)
        expected_closes = booking_start + timedelta(minutes=7.5)
        assert result["join_opens_at"] == expected_opens
        assert result["join_closes_at"] == expected_closes

    def test_join_window_60min_lesson(self) -> None:
        """60-min lesson → grace = 15 min (capped)."""
        now = datetime.now(timezone.utc)
        booking_start = now + timedelta(minutes=2)

        booking = _make_booking(
            booking_start_utc=booking_start,
            duration_minutes=60,
            location_type="online",
            status="CONFIRMED",
        )
        result = _extract_satellite_fields(booking)

        expected_closes = booking_start + timedelta(minutes=15)
        assert result["join_closes_at"] == expected_closes


# ---------------------------------------------------------------------------
# BookingResponse.from_booking() round-trip
# ---------------------------------------------------------------------------


class TestFromBookingVideoFields:
    """Tests for video fields in BookingResponse.from_booking()."""

    def _make_full_booking(self, **overrides: object) -> MagicMock:
        """Booking with all relationships needed for from_booking()."""
        student = MagicMock()
        student.id = "01STUDENT0000000000000000"
        student.first_name = "Jane"
        student.last_name = "Doe"
        student.email = "jane@example.com"

        instructor = MagicMock()
        instructor.id = "01INSTRUC000000000000000"
        instructor.first_name = "John"
        instructor.last_name = "Smith"

        service = MagicMock()
        service.id = "01SERVICE000000000000000"
        service.name = "Piano"
        service.description = "Piano lessons"

        defaults: dict[str, object] = {
            "student": student,
            "instructor": instructor,
            "instructor_service": service,
            "rescheduled_from": None,
        }
        defaults.update(overrides)
        return _make_booking(**defaults)

    def test_from_booking_includes_video_fields(self) -> None:
        """from_booking() includes video session fields in response."""
        started = _utc(2025, 6, 15, 14, 0)
        vs = _make_video_session(
            room_id="rm_full",
            session_started_at=started,
            session_ended_at=_utc(2025, 6, 15, 15, 0),
            session_duration_seconds=3600,
            instructor_joined_at=_utc(2025, 6, 15, 13, 58),
            student_joined_at=_utc(2025, 6, 15, 14, 1),
        )
        booking = self._make_full_booking(video_session=vs)

        response = BookingResponse.from_booking(booking)

        assert response.video_room_id == "rm_full"
        assert response.video_session_started_at == started
        assert response.video_session_duration_seconds == 3600

    def test_from_booking_no_video_session(self) -> None:
        """from_booking() returns None for all video session fields when no session.

        Note: can_join_lesson is a computed timing field based on booking state,
        not video_session existence. Online+confirmed bookings always get a
        join window computation.
        """
        booking = self._make_full_booking(video_session=None)

        response = BookingResponse.from_booking(booking)

        assert response.video_room_id is None
        assert response.video_session_started_at is None
        assert response.video_session_ended_at is None
        assert response.video_session_duration_seconds is None
        assert response.video_instructor_joined_at is None
        assert response.video_student_joined_at is None
