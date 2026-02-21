"""Unit tests for 100ms webhook handler helpers and event processing."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: _extract_booking_id_from_room_name
# ---------------------------------------------------------------------------


class TestExtractBookingIdFromRoomName:
    """Tests for room name → booking ID extraction."""

    def test_valid_room_name(self) -> None:
        from app.routes.v1.webhooks_hundredms import _extract_booking_id_from_room_name

        # 26-char ULID
        booking_id = "01HYXZ5G6KFXJKZ9CHQM4E3P7G"
        result = _extract_booking_id_from_room_name(f"lesson-{booking_id}")
        assert result == booking_id

    def test_invalid_prefix(self) -> None:
        from app.routes.v1.webhooks_hundredms import _extract_booking_id_from_room_name

        result = _extract_booking_id_from_room_name("room-01HYXZ5G6KFXJKZ9CHQM4E3P7G")
        assert result is None

    def test_none_input(self) -> None:
        from app.routes.v1.webhooks_hundredms import _extract_booking_id_from_room_name

        assert _extract_booking_id_from_room_name(None) is None

    def test_empty_string(self) -> None:
        from app.routes.v1.webhooks_hundredms import _extract_booking_id_from_room_name

        assert _extract_booking_id_from_room_name("") is None

    def test_wrong_length(self) -> None:
        from app.routes.v1.webhooks_hundredms import _extract_booking_id_from_room_name

        assert _extract_booking_id_from_room_name("lesson-short") is None

    def test_bare_prefix(self) -> None:
        from app.routes.v1.webhooks_hundredms import _extract_booking_id_from_room_name

        assert _extract_booking_id_from_room_name("lesson-") is None


# ---------------------------------------------------------------------------
# Helper: _parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    """Tests for ISO-8601 timestamp parsing."""

    def test_iso_with_z_suffix(self) -> None:
        from app.routes.v1.webhooks_hundredms import _parse_timestamp

        result = _parse_timestamp("2024-01-15T10:30:00Z")
        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2024

    def test_iso_with_offset(self) -> None:
        from app.routes.v1.webhooks_hundredms import _parse_timestamp

        result = _parse_timestamp("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_none_returns_none(self) -> None:
        from app.routes.v1.webhooks_hundredms import _parse_timestamp

        assert _parse_timestamp(None) is None

    def test_empty_string_returns_none(self) -> None:
        from app.routes.v1.webhooks_hundredms import _parse_timestamp

        assert _parse_timestamp("") is None

    def test_non_string_returns_none(self) -> None:
        from app.routes.v1.webhooks_hundredms import _parse_timestamp

        assert _parse_timestamp(12345) is None

    def test_invalid_format_returns_none(self) -> None:
        from app.routes.v1.webhooks_hundredms import _parse_timestamp

        assert _parse_timestamp("not-a-date") is None

    def test_naive_datetime_gets_utc(self) -> None:
        from app.routes.v1.webhooks_hundredms import _parse_timestamp

        result = _parse_timestamp("2024-01-15T10:30:00")
        assert result is not None
        assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Helper: _build_delivery_key
# ---------------------------------------------------------------------------


class TestBuildDeliveryKey:
    """Tests for webhook delivery key generation."""

    def test_uses_event_id_when_present(self) -> None:
        from app.routes.v1.webhooks_hundredms import _build_delivery_key

        key = _build_delivery_key("evt_123", "peer.join.success", {"room_id": "r1", "session_id": "s1"})
        assert key == "evt_123"

    def test_fallback_key_includes_peer_id(self) -> None:
        from app.routes.v1.webhooks_hundredms import _build_delivery_key

        key_student = _build_delivery_key(
            None,
            "peer.join.success",
            {"room_id": "r1", "session_id": "s1", "peer_id": "peer-student"},
        )
        key_instructor = _build_delivery_key(
            None,
            "peer.join.success",
            {"room_id": "r1", "session_id": "s1", "peer_id": "peer-instructor"},
        )
        assert key_student != key_instructor
        assert key_student.endswith(":peer-student")
        assert key_instructor.endswith(":peer-instructor")

    def test_fallback_key_uses_nested_peer_object(self) -> None:
        from app.routes.v1.webhooks_hundredms import _build_delivery_key

        key = _build_delivery_key(
            None,
            "peer.join.success",
            {"room_id": "r1", "session_id": "s1", "peer": {"id": "peer-nested"}},
        )
        assert key == "peer.join.success:r1:s1:peer-nested"

    def test_fallback_key_uses_no_peer_marker_when_missing(self) -> None:
        from app.routes.v1.webhooks_hundredms import _build_delivery_key

        key = _build_delivery_key(None, "session.open.success", {"room_id": "r1", "session_id": "s1"})
        assert key == "session.open.success:r1:s1:no-peer"


# ---------------------------------------------------------------------------
# Signature verification: _verify_hundredms_secret
# ---------------------------------------------------------------------------


class TestVerifyHundredmsSecret:
    """Tests for webhook secret header verification."""

    def test_missing_header_raises_401(self) -> None:
        from fastapi import HTTPException

        from app.routes.v1.webhooks_hundredms import _verify_hundredms_secret

        request = MagicMock()
        request.headers = {}

        with patch("app.routes.v1.webhooks_hundredms.settings") as mock_settings:
            mock_settings.hundredms_webhook_secret = MagicMock()
            mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "test-secret"

            with pytest.raises(HTTPException) as exc_info:
                _verify_hundredms_secret(request)
            assert exc_info.value.status_code == 401

    def test_wrong_secret_value_raises_401(self) -> None:
        from fastapi import HTTPException

        from app.routes.v1.webhooks_hundredms import _verify_hundredms_secret

        request = MagicMock()
        request.headers = {"x-hundredms-secret": "wrong-secret"}

        with patch("app.routes.v1.webhooks_hundredms.settings") as mock_settings:
            mock_settings.hundredms_webhook_secret = MagicMock()
            mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "correct-secret"

            with pytest.raises(HTTPException) as exc_info:
                _verify_hundredms_secret(request)
            assert exc_info.value.status_code == 401

    def test_valid_secret_passes(self) -> None:
        from app.routes.v1.webhooks_hundredms import _verify_hundredms_secret

        request = MagicMock()
        request.headers = {"x-hundredms-secret": "my-secret"}

        with patch("app.routes.v1.webhooks_hundredms.settings") as mock_settings:
            mock_settings.hundredms_webhook_secret = MagicMock()
            mock_settings.hundredms_webhook_secret.get_secret_value.return_value = "my-secret"

            # Should not raise
            _verify_hundredms_secret(request)

    def test_unconfigured_secret_raises_500(self) -> None:
        from fastapi import HTTPException

        from app.routes.v1.webhooks_hundredms import _verify_hundredms_secret

        request = MagicMock()
        request.headers = {"x-hundredms-secret": "anything"}

        with patch("app.routes.v1.webhooks_hundredms.settings") as mock_settings:
            mock_settings.hundredms_webhook_secret = None

            with pytest.raises(HTTPException) as exc_info:
                _verify_hundredms_secret(request)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Event processing: _process_hundredms_event
# ---------------------------------------------------------------------------


class TestProcessHundredmsEvent:
    """Tests for event-type-specific BookingVideoSession updates."""

    def _make_video_session(self) -> MagicMock:
        vs = MagicMock()
        vs.session_id = None
        vs.session_started_at = None
        vs.session_ended_at = None
        vs.session_duration_seconds = None
        vs.instructor_peer_id = None
        vs.student_peer_id = None
        vs.instructor_joined_at = None
        vs.student_joined_at = None
        vs.instructor_left_at = None
        vs.student_left_at = None
        vs.provider_metadata = None
        return vs

    def _make_repo(self, video_session: MagicMock | None = None) -> MagicMock:
        repo = MagicMock()
        repo.get_video_session_by_booking_id.return_value = video_session
        repo.get_by_id.return_value = MagicMock(
            student_id="student_123",
            instructor_id="instructor_123",
            booking_start_utc=datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc),
            duration_minutes=60,
        )
        return repo

    def test_session_open_populates_session_id_and_started_at(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        error, outcome = _process_hundredms_event(
            event_type="session.open.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "room_id": "room123",
                "session_id": "sess456",
                "session_started_at": "2024-06-15T14:00:00Z",
            },
            booking_repo=repo,
        )

        assert outcome == "processed"
        assert error is None
        assert vs.session_id == "sess456"
        assert vs.session_started_at is not None
        repo.flush.assert_called_once()

    def test_session_close_populates_ended_at_and_duration(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        error, outcome = _process_hundredms_event(
            event_type="session.close.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "room_id": "room123",
                "session_id": "sess456",
                "session_duration": 3600,
                "session_stopped_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert outcome == "processed"
        assert vs.session_ended_at is not None
        assert vs.session_duration_seconds == 3600

    def test_peer_join_host_sets_instructor_fields(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-abc",
                "role": "host",
                "joined_at": "2024-06-15T14:00:00Z",
                "metadata": '{"user_id":"instructor_123"}',
            },
            booking_repo=repo,
        )

        assert vs.instructor_peer_id == "peer-abc"
        assert vs.instructor_joined_at is not None
        assert vs.student_peer_id is None

    def test_peer_join_guest_sets_student_fields(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-xyz",
                "role": "guest",
                "joined_at": "2024-06-15T14:01:00Z",
                "metadata": '{"user_id":"student_123"}',
            },
            booking_repo=repo,
        )

        assert vs.student_peer_id == "peer-xyz"
        assert vs.student_joined_at is not None
        assert vs.instructor_peer_id is None

    def test_peer_leave_host_sets_instructor_left_at(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.instructor_joined_at = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "host",
                "left_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.instructor_left_at is not None
        assert vs.student_left_at is None

    def test_peer_leave_guest_sets_student_left_at(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.student_joined_at = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "guest",
                "left_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.student_left_at is not None
        assert vs.instructor_left_at is None

    def test_unrecognized_room_name_returns_skipped(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        repo = self._make_repo()

        error, outcome = _process_hundredms_event(
            event_type="session.open.success",
            data={"room_name": "random-room-name", "session_id": "s1"},
            booking_repo=repo,
        )

        assert outcome == "skipped"
        repo.get_video_session_by_booking_id.assert_not_called()

    def test_missing_video_session_returns_skipped(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        repo = self._make_repo(video_session=None)

        error, outcome = _process_hundredms_event(
            event_type="session.open.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "session_id": "s1",
            },
            booking_repo=repo,
        )

        assert outcome == "skipped"

    def test_peer_join_uses_direct_user_id_field(self) -> None:
        """When data.user_id is present (from 100ms auth token), use it
        instead of relying on metadata JSON parsing."""
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        error, outcome = _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-direct",
                "role": "host",
                "joined_at": "2024-06-15T14:00:00Z",
                "user_id": "instructor_123",
                "metadata": "{}",  # no user_id in metadata
            },
            booking_repo=repo,
        )

        assert outcome == "processed"
        assert vs.instructor_peer_id == "peer-direct"
        assert vs.instructor_joined_at is not None

    def test_peer_join_falls_back_to_metadata_when_no_direct_user_id(self) -> None:
        """When data.user_id is absent, fall back to metadata JSON."""
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        error, outcome = _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-meta",
                "role": "guest",
                "joined_at": "2024-06-15T14:01:00Z",
                "metadata": '{"user_id":"student_123"}',
            },
            booking_repo=repo,
        )

        assert outcome == "processed"
        assert vs.student_peer_id == "peer-meta"
        assert vs.student_joined_at is not None

    def test_peer_join_mismatched_user_id_is_skipped(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        error, outcome = _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-xyz",
                "role": "guest",
                "joined_at": "2024-06-15T14:01:00Z",
                "metadata": '{"user_id":"not-a-participant"}',
            },
            booking_repo=repo,
        )

        assert error is None
        assert outcome == "skipped"
        assert vs.student_joined_at is None

    def test_peer_join_outside_attendance_window_is_skipped(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        repo = self._make_repo(vs)

        error, outcome = _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-xyz",
                "role": "guest",
                "joined_at": "2024-06-15T15:30:00Z",
                "metadata": '{"user_id":"student_123"}',
            },
            booking_repo=repo,
        )

        assert error is None
        assert outcome == "skipped"
        assert vs.student_joined_at is None

    def test_metadata_appended_to_provider_metadata(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.provider_metadata = None
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="session.open.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "session_id": "s1",
                "session_started_at": "2024-06-15T14:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.provider_metadata is not None
        assert "events" in vs.provider_metadata
        assert len(vs.provider_metadata["events"]) == 1
        assert vs.provider_metadata["events"][0]["type"] == "session.open.success"

    def test_metadata_appends_to_existing(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.provider_metadata = {"events": [{"type": "old_event"}]}
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "p1",
                "role": "host",
                "joined_at": "2024-06-15T14:00:00Z",
                "metadata": '{"user_id":"instructor_123"}',
            },
            booking_repo=repo,
        )

        assert len(vs.provider_metadata["events"]) == 2

    # -- Idempotency tests -----------------------------------------------

    def test_duplicate_peer_join_host_preserves_first_timestamp(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        first_join = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        vs.instructor_joined_at = first_join
        vs.instructor_peer_id = "peer-first"
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-second",
                "role": "host",
                "joined_at": "2024-06-15T14:05:00Z",
                "metadata": '{"user_id":"instructor_123"}',
            },
            booking_repo=repo,
        )

        assert vs.instructor_joined_at == first_join
        assert vs.instructor_peer_id == "peer-second"  # peer_id always updates

    def test_duplicate_peer_join_guest_preserves_first_timestamp(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        first_join = datetime(2024, 6, 15, 14, 1, 0, tzinfo=timezone.utc)
        vs.student_joined_at = first_join
        vs.student_peer_id = "peer-first"
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.join.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "peer_id": "peer-second",
                "role": "guest",
                "joined_at": "2024-06-15T14:06:00Z",
                "metadata": '{"user_id":"student_123"}',
            },
            booking_repo=repo,
        )

        assert vs.student_joined_at == first_join
        assert vs.student_peer_id == "peer-second"

    def test_duplicate_peer_leave_host_preserves_first_timestamp(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.instructor_joined_at = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        first_leave = datetime(2024, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        vs.instructor_left_at = first_leave
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "host",
                "left_at": "2024-06-15T16:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.instructor_left_at == first_leave

    def test_duplicate_peer_leave_guest_preserves_first_timestamp(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.student_joined_at = datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        first_leave = datetime(2024, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        vs.student_left_at = first_leave
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "guest",
                "left_at": "2024-06-15T16:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.student_left_at == first_leave

    def test_session_close_backfills_session_started_at(self) -> None:
        """When session.open.success was missed, session.close.success backfills session_started_at."""
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        assert vs.session_started_at is None
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="session.close.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "session_duration": 3600,
                "session_stopped_at": "2024-06-15T15:00:00Z",
                "session_started_at": "2024-06-15T14:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.session_started_at is not None
        assert vs.session_started_at.hour == 14
        assert vs.session_ended_at is not None
        assert vs.session_ended_at.hour == 15

    def test_session_close_does_not_overwrite_existing_session_started_at(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        original_start = datetime(2024, 6, 15, 13, 58, 0, tzinfo=timezone.utc)
        vs.session_started_at = original_start
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="session.close.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "session_duration": 3600,
                "session_stopped_at": "2024-06-15T15:00:00Z",
                "session_started_at": "2024-06-15T14:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.session_started_at == original_start

    def test_peer_leave_host_backfills_join_when_no_prior_join(self) -> None:
        """When peer.join.success was missed, peer.leave.success backfills joined_at."""
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.booking_id = "01HYXZ5G6KFXJKZ9CHQM4E3P7G"
        assert vs.instructor_joined_at is None
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "host",
                "peer_id": "peer-instructor",
                "user_id": "instructor_123",
                "joined_at": "2024-06-15T14:00:00Z",
                "left_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.instructor_joined_at is not None
        assert vs.instructor_peer_id == "peer-instructor"
        assert vs.instructor_left_at is not None

    def test_peer_leave_guest_backfills_join_when_no_prior_join(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.booking_id = "01HYXZ5G6KFXJKZ9CHQM4E3P7G"
        assert vs.student_joined_at is None
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "guest",
                "peer_id": "peer-student",
                "user_id": "student_123",
                "joined_at": "2024-06-15T14:01:00Z",
                "left_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.student_joined_at is not None
        assert vs.student_peer_id == "peer-student"
        assert vs.student_left_at is not None

    def test_peer_leave_host_backfill_rejected_for_mismatched_user_id(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.booking_id = "01HYXZ5G6KFXJKZ9CHQM4E3P7G"
        vs.room_id = "room123"
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "host",
                "peer_id": "peer-attacker",
                "user_id": "not_the_instructor",
                "joined_at": "2024-06-15T14:00:00Z",
                "left_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.instructor_joined_at is None
        assert vs.instructor_left_at is None

    def test_later_session_close_overwrites_timestamp(self) -> None:
        from datetime import datetime

        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        first_end = datetime(2024, 6, 15, 15, 0, 0, tzinfo=timezone.utc)
        vs.session_ended_at = first_end
        vs.session_duration_seconds = 3600
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="session.close.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "session_duration": 7200,
                "session_stopped_at": "2024-06-15T16:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.session_ended_at != first_end
        assert vs.session_duration_seconds == 7200

    # -- Out-of-order tests ----------------------------------------------

    def test_peer_leave_host_without_join_is_ignored(self, caplog: pytest.LogCaptureFixture) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.booking_id = "01HYXZ5G6KFXJKZ9CHQM4E3P7G"
        vs.room_id = "room123"
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "host",
                "left_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.instructor_left_at is None
        assert "Ignoring peer.leave for instructor" in caplog.text

    def test_peer_leave_guest_without_join_is_ignored(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
        vs.booking_id = "01HYXZ5G6KFXJKZ9CHQM4E3P7G"
        vs.room_id = "room123"
        repo = self._make_repo(vs)

        _process_hundredms_event(
            event_type="peer.leave.success",
            data={
                "room_name": "lesson-01HYXZ5G6KFXJKZ9CHQM4E3P7G",
                "role": "guest",
                "left_at": "2024-06-15T15:00:00Z",
            },
            booking_repo=repo,
        )

        assert vs.student_left_at is None


# ---------------------------------------------------------------------------
# In-memory dedup cache: _delivery_seen, _mark_delivery, _unmark_delivery
# ---------------------------------------------------------------------------


class TestDeliveryCache:
    """Tests for the in-memory webhook delivery dedup cache."""

    def _clear_cache(self) -> None:
        from app.routes.v1.webhooks_hundredms import _delivery_cache

        _delivery_cache.clear()

    def setup_method(self) -> None:
        self._clear_cache()

    def teardown_method(self) -> None:
        self._clear_cache()

    def test_unseen_key_returns_false(self) -> None:
        from app.routes.v1.webhooks_hundredms import _delivery_seen

        assert _delivery_seen("new-key") is False

    def test_marked_key_is_seen(self) -> None:
        from app.routes.v1.webhooks_hundredms import _delivery_seen, _mark_delivery

        _mark_delivery("evt-123")
        assert _delivery_seen("evt-123") is True

    def test_unmarked_key_is_no_longer_seen(self) -> None:
        from app.routes.v1.webhooks_hundredms import (
            _delivery_seen,
            _mark_delivery,
            _unmark_delivery,
        )

        _mark_delivery("evt-456")
        assert _delivery_seen("evt-456") is True

        _unmark_delivery("evt-456")
        assert _delivery_seen("evt-456") is False

    def test_none_key_not_marked(self) -> None:
        from app.routes.v1.webhooks_hundredms import _delivery_cache, _mark_delivery

        _mark_delivery(None)
        assert len(_delivery_cache) == 0

    def test_none_key_never_seen(self) -> None:
        from app.routes.v1.webhooks_hundredms import _delivery_seen

        assert _delivery_seen(None) is False

    def test_none_key_unmark_is_noop(self) -> None:
        from app.routes.v1.webhooks_hundredms import _delivery_cache, _unmark_delivery

        _unmark_delivery(None)
        assert len(_delivery_cache) == 0

    def test_empty_string_key_not_marked(self) -> None:
        from app.routes.v1.webhooks_hundredms import _delivery_cache, _mark_delivery

        _mark_delivery("")
        assert len(_delivery_cache) == 0

    def test_cache_evicts_oldest_when_full(self) -> None:
        from app.routes.v1.webhooks_hundredms import (
            _WEBHOOK_CACHE_MAX_SIZE,
            _delivery_cache,
            _delivery_seen,
            _mark_delivery,
        )

        # Fill to max
        for i in range(_WEBHOOK_CACHE_MAX_SIZE):
            _mark_delivery(f"key-{i}")
        assert len(_delivery_cache) == _WEBHOOK_CACHE_MAX_SIZE

        # Add one more — oldest should be evicted
        _mark_delivery("overflow-key")
        assert len(_delivery_cache) == _WEBHOOK_CACHE_MAX_SIZE
        assert _delivery_seen("key-0") is False
        assert _delivery_seen("overflow-key") is True

    @patch("app.routes.v1.webhooks_hundredms.monotonic")
    def test_expired_entries_are_cleaned_on_seen_check(self, mock_monotonic: MagicMock) -> None:
        from app.routes.v1.webhooks_hundredms import (
            _WEBHOOK_CACHE_TTL_SECONDS,
            _delivery_cache,
            _delivery_seen,
            _mark_delivery,
        )

        # Mark at time=0
        mock_monotonic.return_value = 0.0
        _mark_delivery("old-key")
        assert len(_delivery_cache) == 1

        # Check after TTL expires
        mock_monotonic.return_value = float(_WEBHOOK_CACHE_TTL_SECONDS + 1)
        assert _delivery_seen("old-key") is False
        assert len(_delivery_cache) == 0

    def test_multiple_keys_tracked_independently(self) -> None:
        from app.routes.v1.webhooks_hundredms import (
            _delivery_seen,
            _mark_delivery,
            _unmark_delivery,
        )

        _mark_delivery("key-a")
        _mark_delivery("key-b")
        assert _delivery_seen("key-a") is True
        assert _delivery_seen("key-b") is True

        _unmark_delivery("key-a")
        assert _delivery_seen("key-a") is False
        assert _delivery_seen("key-b") is True
