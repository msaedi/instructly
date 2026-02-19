"""Tests for the VideoService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.integrations.hundredms_client import FakeHundredMsClient, HundredMsError
from app.services.video_service import VideoService

# ── Helpers ───────────────────────────────────────────────────────────


def _make_booking(**overrides):
    """Create a mock booking with sensible defaults."""
    now_utc = datetime.now(timezone.utc)
    booking = Mock()
    booking.id = "01BOOKING_ID_TEST_ULID_26"
    booking.student_id = "01STUDENT_ID_TEST_ULID_26"
    booking.instructor_id = "01INSTRUC_ID_TEST_ULID_26"
    booking.status = "CONFIRMED"
    booking.location_type = "online"
    booking.booking_start_utc = now_utc + timedelta(minutes=2)  # 2min from now (inside window)
    booking.duration_minutes = 60
    for key, value in overrides.items():
        setattr(booking, key, value)
    return booking


def _make_service(
    *,
    booking=None,
    video_session=None,
    ensure_returns=None,
):
    """Create a VideoService with mocked dependencies."""
    fake_client = FakeHundredMsClient()
    mock_db = Mock()

    service = VideoService(db=mock_db, hundredms_client=fake_client)

    # Patch the repository that was created in __init__
    mock_repo = Mock()
    mock_repo.get_booking_for_participant.return_value = booking
    mock_repo.get_booking_for_participant_for_update.return_value = booking
    mock_repo.get_video_session_by_booking_id.return_value = video_session
    mock_repo.ensure_video_session.return_value = ensure_returns or video_session
    service.booking_repository = mock_repo

    return service, fake_client, mock_repo


def _make_video_session(**overrides):
    """Create a mock BookingVideoSession."""
    vs = Mock()
    vs.room_id = "room_abc123"
    vs.room_name = "lesson-01BOOKING_ID_TEST_ULID_26"
    vs.session_started_at = None
    vs.session_ended_at = None
    vs.instructor_joined_at = None
    vs.student_joined_at = None
    for key, value in overrides.items():
        setattr(vs, key, value)
    return vs


# ── Happy path ────────────────────────────────────────────────────────


class TestJoinLessonHappyPath:
    def test_student_gets_guest_role(self):
        booking = _make_booking()
        vs = _make_video_session()
        service, fake_client, _ = _make_service(booking=booking, video_session=vs)

        result = service.join_lesson(booking.id, booking.student_id)

        assert result["role"] == "guest"
        assert result["booking_id"] == booking.id
        assert result["room_id"] == vs.room_id
        assert "auth_token" in result

    def test_instructor_gets_host_role(self):
        booking = _make_booking()
        vs = _make_video_session()
        service, fake_client, _ = _make_service(booking=booking, video_session=vs)

        result = service.join_lesson(booking.id, booking.instructor_id)

        assert result["role"] == "host"

    def test_creates_room_on_first_join(self):
        booking = _make_booking()
        new_vs = _make_video_session()
        service, fake_client, mock_repo = _make_service(
            booking=booking,
            video_session=None,  # No existing session
            ensure_returns=new_vs,
        )

        result = service.join_lesson(booking.id, booking.student_id)

        # Verify create_room was called
        create_calls = [c for c in fake_client._calls if c["method"] == "create_room"]
        assert len(create_calls) == 1
        assert create_calls[0]["name"] == f"lesson-{booking.id}"

        # Verify ensure_video_session was called
        mock_repo.ensure_video_session.assert_called_once()
        assert result["room_id"] == new_vs.room_id

    def test_reuses_existing_room(self):
        booking = _make_booking()
        vs = _make_video_session()
        service, fake_client, mock_repo = _make_service(booking=booking, video_session=vs)

        service.join_lesson(booking.id, booking.student_id)

        # create_room should NOT have been called
        create_calls = [c for c in fake_client._calls if c["method"] == "create_room"]
        assert len(create_calls) == 0

    def test_releases_lock_before_external_room_creation(self):
        booking = _make_booking()
        new_vs = _make_video_session()
        service, _, mock_repo = _make_service(
            booking=booking,
            video_session=None,
            ensure_returns=new_vs,
        )

        service.join_lesson(booking.id, booking.student_id)

        mock_repo.rollback.assert_called_once()

    def test_reuses_session_created_while_unlocked(self):
        booking = _make_booking()
        concurrent_vs = _make_video_session(room_id="room_created_elsewhere")
        service, fake_client, mock_repo = _make_service(
            booking=booking,
            video_session=None,
        )
        mock_repo.get_video_session_by_booking_id.side_effect = [None, concurrent_vs]

        result = service.join_lesson(booking.id, booking.student_id)

        assert result["room_id"] == "room_created_elsewhere"
        mock_repo.ensure_video_session.assert_not_called()
        mock_repo.rollback.assert_called_once()
        create_calls = [c for c in fake_client._calls if c["method"] == "create_room"]
        assert len(create_calls) == 1


# ── Timing validation ─────────────────────────────────────────────────


class TestJoinLessonTiming:
    def test_rejects_too_early(self):
        from app.core.exceptions import ValidationException

        # TESTING-ONLY: revert before production (was minutes=10)
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc) + timedelta(minutes=20),
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        with pytest.raises(ValidationException, match="not opened yet"):
            service.join_lesson(booking.id, booking.student_id)

    def test_allows_join_at_t_minus_5(self):
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        result = service.join_lesson(booking.id, booking.student_id)
        assert result["role"] == "guest"

    def test_allows_join_at_start_time(self):
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc),
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        result = service.join_lesson(booking.id, booking.student_id)
        assert result["role"] == "guest"

    def test_allows_join_during_grace_period(self):
        # 60min lesson → grace = min(60*0.25, 15) = 15min
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc) - timedelta(minutes=10),
            duration_minutes=60,
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        result = service.join_lesson(booking.id, booking.student_id)
        assert result["role"] == "guest"

    def test_rejects_after_grace_period(self):
        from app.core.exceptions import ValidationException

        # TESTING-ONLY: revert before production (was minutes=20, grace was 15min)
        # 60min lesson → grace = max(60-5, 15) = 55min, start was 60min ago → expired
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc) - timedelta(minutes=60),
            duration_minutes=60,
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        with pytest.raises(ValidationException, match="closed"):
            service.join_lesson(booking.id, booking.student_id)

    def test_grace_period_30min_lesson(self):
        # 30min lesson → grace = min(30*0.25, 15) = 7.5min
        # Start was 7min ago → should still be allowed
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc) - timedelta(minutes=7),
            duration_minutes=30,
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        result = service.join_lesson(booking.id, booking.student_id)
        assert result["role"] == "guest"

    def test_grace_period_30min_lesson_expired(self):
        from app.core.exceptions import ValidationException

        # TESTING-ONLY: revert before production (was minutes=8, grace was 7.5min)
        # 30min lesson → grace = max(30-5, 7.5) = 25min, start was 30min ago → expired
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc) - timedelta(minutes=30),
            duration_minutes=30,
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        with pytest.raises(ValidationException, match="closed"):
            service.join_lesson(booking.id, booking.student_id)

    def test_grace_period_90min_lesson_capped_at_15(self):
        # 90min lesson → grace = min(90*0.25, 15) = min(22.5, 15) = 15min
        # Start was 14min ago → should still be allowed
        booking = _make_booking(
            booking_start_utc=datetime.now(timezone.utc) - timedelta(minutes=14),
            duration_minutes=90,
        )
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        result = service.join_lesson(booking.id, booking.student_id)
        assert result["role"] == "guest"

    def test_revalidates_after_unlock_when_booking_changes(self):
        from app.core.exceptions import ValidationException

        booking = _make_booking()
        cancelled_booking = _make_booking(status="CANCELLED")
        vs = _make_video_session()
        service, _, mock_repo = _make_service(booking=booking, video_session=None, ensure_returns=vs)
        mock_repo.get_booking_for_participant_for_update.side_effect = [booking, cancelled_booking]
        mock_repo.get_video_session_by_booking_id.side_effect = [None, None]

        with pytest.raises(ValidationException, match="not confirmed"):
            service.join_lesson(booking.id, booking.student_id)


# ── Booking validation ────────────────────────────────────────────────


class TestJoinLessonValidation:
    def test_rejects_non_confirmed(self):
        from app.core.exceptions import ValidationException

        booking = _make_booking(status="PENDING")
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        with pytest.raises(ValidationException, match="not confirmed"):
            service.join_lesson(booking.id, booking.student_id)

    def test_rejects_non_online(self):
        from app.core.exceptions import ValidationException

        booking = _make_booking(location_type="student_location")
        vs = _make_video_session()
        service, _, _ = _make_service(booking=booking, video_session=vs)

        with pytest.raises(ValidationException, match="not an online lesson"):
            service.join_lesson(booking.id, booking.student_id)

    def test_not_found_for_non_participant(self):
        from app.core.exceptions import NotFoundException

        service, _, _ = _make_service(booking=None)

        with pytest.raises(NotFoundException):
            service.join_lesson("01BOOKING_ID_TEST_ULID_26", "01UNKNOWN_USER_ULID_26CH")


# ── Status endpoint ───────────────────────────────────────────────────


class TestVideoSessionStatus:
    def test_returns_dict_when_session_exists(self):
        booking = _make_booking()
        vs = _make_video_session(
            session_started_at=datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc),
        )
        service, _, _ = _make_service(booking=booking, video_session=vs)

        result = service.get_video_session_status(booking.id, booking.student_id)

        assert result is not None
        assert result["room_id"] == vs.room_id
        assert result["session_started_at"] == vs.session_started_at

    def test_returns_none_when_no_session(self):
        booking = _make_booking()
        service, _, _ = _make_service(booking=booking, video_session=None)

        result = service.get_video_session_status(booking.id, booking.student_id)
        assert result is None

    def test_not_found_for_non_participant(self):
        from app.core.exceptions import NotFoundException

        service, _, _ = _make_service(booking=None)

        with pytest.raises(NotFoundException):
            service.get_video_session_status("01BOOKING_ID_TEST_ULID_26", "01UNKNOWN_USER_ULID_26CH")


# ── Error handling ────────────────────────────────────────────────────


class TestJoinLessonErrors:
    def test_hundredms_error_wrapped_in_service_exception(self):
        from app.core.exceptions import ServiceException

        booking = _make_booking()
        service, fake_client, mock_repo = _make_service(
            booking=booking,
            video_session=None,  # Will trigger room creation
        )

        # Replace create_room to raise HundredMsError
        def failing_create_room(**kwargs):
            raise HundredMsError("API down", status_code=500)

        fake_client.create_room = failing_create_room

        with pytest.raises(ServiceException, match="100ms"):
            service.join_lesson(booking.id, booking.student_id)

    def test_auth_token_failure_wrapped_in_service_exception(self):
        """Room created successfully but auth token generation fails.

        This is a realistic production scenario (e.g. 100ms key rotation
        mid-request, network timeout after room creation). Verifies the
        error message distinguishes token failure from room failure.
        """
        from app.core.exceptions import ServiceException

        booking = _make_booking()
        vs = _make_video_session()
        service, fake_client, _ = _make_service(booking=booking, video_session=vs)

        # Room exists, but token generation fails
        def failing_generate_auth_token(**kwargs):
            raise HundredMsError("Token signing failed", status_code=500)

        fake_client.generate_auth_token = failing_generate_auth_token

        with pytest.raises(ServiceException, match="auth token generation failed"):
            service.join_lesson(booking.id, booking.student_id)
