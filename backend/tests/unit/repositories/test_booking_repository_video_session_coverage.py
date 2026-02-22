"""Unit tests for BookingRepository — targets video session + participant error paths.

Missed lines:
  295-305   get_video_session_by_booking_id: error path
  311-332   ensure_video_session: IntegrityError retry + generic Exception reraise
  1238-1240 get_booking_for_participant: error path
  1255-1257 get_booking_for_student: error path
  1272-1274 get_booking_for_instructor: error path
  1301->1303, 1303->1305 get_booking_for_participant_for_update: branch partials
  1306-1308 get_booking_for_participant_for_update: error path
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import RepositoryException
from app.repositories.booking_repository import BookingRepository


def _make_repo() -> tuple[BookingRepository, MagicMock]:
    mock_db = MagicMock()
    repo = BookingRepository.__new__(BookingRepository)
    repo.db = mock_db
    repo.model = MagicMock()
    repo.logger = MagicMock()
    repo.invalidate_entity_cache = MagicMock()
    repo._external_call_lock_savepoint = None
    return repo, mock_db


# ------------------------------------------------------------------
# get_video_session_by_booking_id — lines 295-305
# ------------------------------------------------------------------


class TestGetVideoSessionByBookingId:
    """Cover the error handling path in get_video_session_by_booking_id."""

    def test_returns_video_session_when_found(self) -> None:
        """Happy path: returns the video session."""
        repo, mock_db = _make_repo()
        session = SimpleNamespace(booking_id="bk_1", room_id="room_1")
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = session

        result = repo.get_video_session_by_booking_id("bk_1")

        assert result is not None
        assert result.room_id == "room_1"

    def test_returns_none_when_not_found(self) -> None:
        """Happy path: returns None when no video session."""
        repo, mock_db = _make_repo()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        result = repo.get_video_session_by_booking_id("bk_nonexistent")

        assert result is None

    def test_error_wraps_in_repository_exception(self) -> None:
        """Lines 303-305: Exception → RepositoryException."""
        repo, mock_db = _make_repo()
        mock_db.query.side_effect = RuntimeError("db unavailable")

        with pytest.raises(RepositoryException, match="Failed to get booking video session"):
            repo.get_video_session_by_booking_id("bk_1")


# ------------------------------------------------------------------
# ensure_video_session — lines 311-332
# ------------------------------------------------------------------


class TestEnsureVideoSession:
    """Cover all branches of ensure_video_session."""

    def test_returns_existing_session(self) -> None:
        """Line 312-313: existing session found → return it."""
        repo, mock_db = _make_repo()
        existing = SimpleNamespace(booking_id="bk_1", room_id="room_1")
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = existing

        result = repo.ensure_video_session("bk_1", "room_1", "Test Room")

        assert result is existing
        mock_db.begin_nested.assert_not_called()

    def test_creates_new_session(self) -> None:
        """Lines 314-321: no existing → creates new."""
        repo, mock_db = _make_repo()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None
        nested = MagicMock()
        mock_db.begin_nested.return_value = nested

        repo.ensure_video_session("bk_1", "room_1", "Test Room")

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_integrity_error_retries_and_returns_existing(self) -> None:
        """Lines 322-329: IntegrityError → retry lookup returns session."""
        repo, mock_db = _make_repo()
        session = SimpleNamespace(booking_id="bk_1", room_id="room_1")

        # First call returns None (no existing), second call returns session (after IntegrityError)
        mock_db.query.return_value.filter.return_value.one_or_none.side_effect = [
            None,
            session,
        ]

        nested = MagicMock()
        mock_db.begin_nested.return_value = nested
        mock_db.flush.side_effect = IntegrityError("dup", {}, None)

        result = repo.ensure_video_session("bk_1", "room_1")

        assert result is session
        nested.rollback.assert_called_once()

    def test_integrity_error_retry_returns_none_raises(self) -> None:
        """Lines 327-329: IntegrityError → retry returns None → RepositoryException."""
        repo, mock_db = _make_repo()

        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        nested = MagicMock()
        mock_db.begin_nested.return_value = nested
        mock_db.flush.side_effect = IntegrityError("dup", {}, None)

        with pytest.raises(RepositoryException, match="Failed to ensure booking video session"):
            repo.ensure_video_session("bk_1", "room_1")

        nested.rollback.assert_called_once()

    def test_generic_exception_rolls_back_and_reraises(self) -> None:
        """Lines 330-332: generic Exception → rollback + re-raise."""
        repo, mock_db = _make_repo()

        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        nested = MagicMock()
        mock_db.begin_nested.return_value = nested
        mock_db.flush.side_effect = RuntimeError("deadlock")

        with pytest.raises(RuntimeError, match="deadlock"):
            repo.ensure_video_session("bk_1", "room_1")

        nested.rollback.assert_called_once()


# ------------------------------------------------------------------
# release_lock_for_external_call / lock savepoint scope
# ------------------------------------------------------------------


class TestReleaseLockForExternalCall:
    """Ensure lock release uses savepoint rollback, not full session rollback."""

    def test_release_uses_savepoint_not_session_rollback(self) -> None:
        repo, mock_db = _make_repo()
        savepoint = MagicMock()
        savepoint.is_active = True
        mock_db.begin_nested.return_value = savepoint

        query_chain = (
            mock_db.query.return_value
            .filter.return_value
            .with_for_update.return_value
        )
        query_chain.populate_existing.return_value.first.return_value = SimpleNamespace(id="bk_1")

        repo.get_booking_for_participant_for_update(
            "bk_1",
            "user_1",
            lock_scope_for_external_call=True,
        )
        repo.release_lock_for_external_call()

        savepoint.rollback.assert_called_once()
        mock_db.rollback.assert_not_called()

    def test_release_is_noop_when_no_savepoint_scope_exists(self) -> None:
        repo, mock_db = _make_repo()

        repo.release_lock_for_external_call()

        mock_db.rollback.assert_not_called()


# ------------------------------------------------------------------
# get_booking_for_participant — lines 1238-1240
# ------------------------------------------------------------------


class TestGetBookingForParticipant:
    """Cover the error path in get_booking_for_participant."""

    def test_error_wraps_in_repository_exception(self) -> None:
        """Lines 1238-1240: Exception → RepositoryException."""
        repo, mock_db = _make_repo()
        mock_db.query.side_effect = RuntimeError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to get booking for participant"):
            repo.get_booking_for_participant("bk_1", "user_1")


# ------------------------------------------------------------------
# get_booking_for_student — lines 1255-1257
# ------------------------------------------------------------------


class TestGetBookingForStudent:
    """Cover the error path in get_booking_for_student."""

    def test_error_wraps_in_repository_exception(self) -> None:
        """Lines 1255-1257: Exception → RepositoryException."""
        repo, mock_db = _make_repo()
        mock_db.query.side_effect = RuntimeError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to get booking for student"):
            repo.get_booking_for_student("bk_1", "student_1")


# ------------------------------------------------------------------
# get_booking_for_instructor — lines 1272-1274
# ------------------------------------------------------------------


class TestGetBookingForInstructor:
    """Cover the error path in get_booking_for_instructor."""

    def test_error_wraps_in_repository_exception(self) -> None:
        """Lines 1272-1274: Exception → RepositoryException."""
        repo, mock_db = _make_repo()
        mock_db.query.side_effect = RuntimeError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to get booking for instructor"):
            repo.get_booking_for_instructor("bk_1", "instructor_1")


# ------------------------------------------------------------------
# get_booking_for_participant_for_update — lines 1301->1303, 1303->1305, 1306-1308
# ------------------------------------------------------------------


class TestGetBookingForParticipantForUpdate:
    """Cover branch partials and error path in get_booking_for_participant_for_update."""

    def test_error_wraps_in_repository_exception(self) -> None:
        """Lines 1306-1308: Exception → RepositoryException."""
        repo, mock_db = _make_repo()
        mock_db.query.side_effect = RuntimeError("lock timeout")

        with pytest.raises(
            RepositoryException, match="Failed to get booking for participant"
        ):
            repo.get_booking_for_participant_for_update("bk_1", "user_1")

    def test_no_load_relationships(self) -> None:
        """Line 1301->1303: load_relationships=False → skip eager loading."""
        repo, mock_db = _make_repo()

        query_chain = (
            mock_db.query.return_value
            .filter.return_value
            .with_for_update.return_value
        )
        query_chain.populate_existing.return_value.first.return_value = None

        result = repo.get_booking_for_participant_for_update(
            "bk_1", "user_1", load_relationships=False
        )

        assert result is None

    def test_no_populate_existing(self) -> None:
        """Line 1303->1305: populate_existing=False → skip populate_existing."""
        repo, mock_db = _make_repo()

        # With load_relationships=True but populate_existing=False
        query_chain = (
            mock_db.query.return_value
            .filter.return_value
            .with_for_update.return_value
        )
        # _apply_eager_loading returns a query mock
        repo._apply_eager_loading = MagicMock(return_value=query_chain)
        query_chain.first.return_value = None

        result = repo.get_booking_for_participant_for_update(
            "bk_1", "user_1", load_relationships=True, populate_existing=False
        )

        assert result is None

    def test_both_flags_false(self) -> None:
        """Lines 1301-1305: both flags False → skip eager loading and populate_existing."""
        repo, mock_db = _make_repo()

        query_chain = (
            mock_db.query.return_value
            .filter.return_value
            .with_for_update.return_value
        )
        query_chain.first.return_value = SimpleNamespace(id="bk_1")

        result = repo.get_booking_for_participant_for_update(
            "bk_1", "user_1", load_relationships=False, populate_existing=False
        )

        assert result is not None
        assert result.id == "bk_1"
