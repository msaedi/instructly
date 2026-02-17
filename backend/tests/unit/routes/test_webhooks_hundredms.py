"""Unit tests for 100ms webhook handler helpers and event processing."""

from __future__ import annotations

from datetime import timezone
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
            },
            booking_repo=repo,
        )

        assert vs.student_peer_id == "peer-xyz"
        assert vs.student_joined_at is not None
        assert vs.instructor_peer_id is None

    def test_peer_leave_host_sets_instructor_left_at(self) -> None:
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
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
        from app.routes.v1.webhooks_hundredms import _process_hundredms_event

        vs = self._make_video_session()
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
            },
            booking_repo=repo,
        )

        assert len(vs.provider_metadata["events"]) == 2
