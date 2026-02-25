"""
Coverage tests for video_service.py targeting missed lines.

Targets:
  - L96: non-confirmed booking status -> ValidationException
  - L117: non-online location -> ValidationException
  - L146: before/after join window -> ValidationException
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import NotFoundException, ServiceException, ValidationException
from app.services.video_service import VideoService


def _make_service() -> VideoService:
    """Create VideoService with mocked dependencies."""
    import logging

    svc = VideoService.__new__(VideoService)
    svc.db = MagicMock()
    svc.hundredms_client = MagicMock()
    svc.booking_repository = MagicMock()
    svc.cache = None
    svc.logger = logging.getLogger("test_video_service")
    return svc


def _make_booking(
    *,
    status="confirmed",
    location_type="online",
    booking_start_utc=None,
    duration_minutes=60,
    instructor_id="INSTR_01",
    student_id="STU_01",
):
    """Create a mock booking."""
    from app.models.booking import BookingStatus, LocationType

    booking = MagicMock()
    booking.status = BookingStatus(status) if isinstance(status, str) else status
    booking.location_type = LocationType(location_type) if isinstance(location_type, str) else location_type
    booking.booking_start_utc = booking_start_utc or (datetime.now(timezone.utc) + timedelta(minutes=5))
    booking.duration_minutes = duration_minutes
    booking.instructor_id = instructor_id
    return booking


@pytest.mark.unit
class TestValidateJoinableBooking:
    """Cover _validate_joinable_booking branches."""

    def test_not_confirmed_raises(self):
        """L40-41: booking not confirmed -> ValidationException."""
        svc = _make_service()
        from app.models.booking import BookingStatus
        booking = MagicMock()
        booking.status = BookingStatus.PENDING
        now = datetime.now(timezone.utc)

        with pytest.raises(ValidationException, match="not confirmed"):
            svc._validate_joinable_booking(booking, now)

    def test_not_online_raises(self):
        """L43-44: booking not online -> ValidationException."""
        svc = _make_service()
        from app.models.booking import BookingStatus, LocationType
        booking = MagicMock()
        booking.status = BookingStatus.CONFIRMED
        booking.location_type = LocationType.STUDENT_LOCATION
        now = datetime.now(timezone.utc)

        with pytest.raises(ValidationException, match="not an online lesson"):
            svc._validate_joinable_booking(booking, now)

    def test_before_join_window_raises(self):
        """L51-52: now < join_opens_at -> ValidationException."""
        svc = _make_service()
        from app.models.booking import BookingStatus, LocationType
        booking = MagicMock()
        booking.status = BookingStatus.CONFIRMED
        booking.location_type = LocationType.ONLINE
        booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(hours=2)
        booking.duration_minutes = 60
        now = datetime.now(timezone.utc)

        with pytest.raises(ValidationException, match="not opened yet"):
            svc._validate_joinable_booking(booking, now)

    def test_after_join_window_raises(self):
        """L53-54: now > join_closes_at -> ValidationException."""
        svc = _make_service()
        from app.models.booking import BookingStatus, LocationType
        booking = MagicMock()
        booking.status = BookingStatus.CONFIRMED
        booking.location_type = LocationType.ONLINE
        booking.booking_start_utc = datetime.now(timezone.utc) - timedelta(hours=2)
        booking.duration_minutes = 60
        now = datetime.now(timezone.utc)

        with pytest.raises(ValidationException, match="has closed"):
            svc._validate_joinable_booking(booking, now)

    def test_within_window_passes(self):
        """Happy path: within join window -> no exception."""
        svc = _make_service()
        from app.models.booking import BookingStatus, LocationType
        booking = MagicMock()
        booking.status = BookingStatus.CONFIRMED
        booking.location_type = LocationType.ONLINE
        booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(minutes=5)
        booking.duration_minutes = 60
        now = datetime.now(timezone.utc)

        # Should not raise
        svc._validate_joinable_booking(booking, now)


@pytest.mark.unit
class TestJoinLesson:
    """Cover join_lesson branches."""

    def test_booking_not_found_raises(self):
        """L70-71: booking is None -> NotFoundException."""
        svc = _make_service()
        svc.booking_repository.get_booking_for_participant_for_update.return_value = None

        with pytest.raises(NotFoundException, match="Booking not found"):
            svc.join_lesson("BOOK_01", "USR_01")
        svc.booking_repository.release_lock_for_external_call.assert_called()

    def test_video_session_unavailable_raises(self):
        """L145-146: video_session is None after all attempts -> ServiceException."""
        svc = _make_service()
        from app.models.booking import BookingStatus, LocationType

        booking = MagicMock()
        booking.status = BookingStatus.CONFIRMED
        booking.location_type = LocationType.ONLINE
        booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(minutes=5)
        booking.duration_minutes = 60
        booking.instructor_id = "INSTR_01"

        svc.booking_repository.get_booking_for_participant_for_update.return_value = booking
        svc.booking_repository.get_video_session_by_booking_id.return_value = None

        # Room creation returns valid room
        svc.hundredms_client.create_room.return_value = {"id": "ROOM_01"}

        # Re-check after room creation: booking still valid but video_session returns room_id = None
        mock_session = MagicMock()
        mock_session.room_id = None

        # First call in initial check -> None, second call after room creation -> still None
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                return None
            return mock_session

        svc.booking_repository.get_video_session_by_booking_id.side_effect = side_effect

        # Mock transaction
        svc.db.begin_nested = MagicMock()
        svc.db.begin_nested.return_value.__enter__ = MagicMock()
        svc.db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)

        svc.booking_repository.ensure_video_session.return_value = mock_session

        with pytest.raises(ServiceException, match="unavailable"):
            svc.join_lesson("BOOK_01", "USR_01")

    def test_hundredms_room_creation_failure(self):
        """L97-108: HundredMsError on room creation -> ServiceException."""
        svc = _make_service()
        from app.integrations.hundredms_client import HundredMsError
        from app.models.booking import BookingStatus, LocationType

        booking = MagicMock()
        booking.status = BookingStatus.CONFIRMED
        booking.location_type = LocationType.ONLINE
        booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(minutes=5)
        booking.duration_minutes = 60
        booking.instructor_id = "INSTR_01"

        svc.booking_repository.get_booking_for_participant_for_update.return_value = booking
        svc.booking_repository.get_video_session_by_booking_id.return_value = None

        svc.hundredms_client.create_room.side_effect = HundredMsError(
            message="Provider error", status_code=500
        )

        with pytest.raises(ServiceException, match="Video room setup failed"):
            svc.join_lesson("BOOK_01", "USR_01")

    def test_room_creation_no_room_id(self):
        """L95-96: create_room returns no room id -> ServiceException."""
        svc = _make_service()
        from app.models.booking import BookingStatus, LocationType

        booking = MagicMock()
        booking.status = BookingStatus.CONFIRMED
        booking.location_type = LocationType.ONLINE
        booking.booking_start_utc = datetime.now(timezone.utc) + timedelta(minutes=5)
        booking.duration_minutes = 60
        booking.instructor_id = "INSTR_01"

        svc.booking_repository.get_booking_for_participant_for_update.return_value = booking
        svc.booking_repository.get_video_session_by_booking_id.return_value = None

        svc.hundredms_client.create_room.return_value = {"id": ""}

        with pytest.raises(ServiceException, match="room id"):
            svc.join_lesson("BOOK_01", "USR_01")


@pytest.mark.unit
class TestGetVideoSessionStatus:
    """Cover get_video_session_status."""

    def test_booking_not_found(self):
        svc = _make_service()
        svc.booking_repository.get_booking_for_participant.return_value = None

        with pytest.raises(NotFoundException):
            svc.get_video_session_status("BOOK_01", "USR_01")

    def test_no_video_session(self):
        svc = _make_service()
        svc.booking_repository.get_booking_for_participant.return_value = MagicMock()
        svc.booking_repository.get_video_session_by_booking_id.return_value = None

        result = svc.get_video_session_status("BOOK_01", "USR_01")
        assert result is None

    def test_video_session_exists(self):
        svc = _make_service()
        svc.booking_repository.get_booking_for_participant.return_value = MagicMock()
        mock_session = MagicMock()
        mock_session.room_id = "ROOM_01"
        mock_session.session_started_at = None
        mock_session.session_ended_at = None
        mock_session.instructor_joined_at = None
        mock_session.student_joined_at = None
        svc.booking_repository.get_video_session_by_booking_id.return_value = mock_session

        result = svc.get_video_session_status("BOOK_01", "USR_01")
        assert result["room_id"] == "ROOM_01"
