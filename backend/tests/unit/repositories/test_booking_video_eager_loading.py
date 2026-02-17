"""Unit tests for video_session eager loading in BookingRepository."""

from __future__ import annotations

from unittest.mock import MagicMock, call

from app.repositories.booking_repository import BookingRepository


def _make_repo() -> tuple[BookingRepository, MagicMock]:
    mock_db = MagicMock()
    repo = BookingRepository.__new__(BookingRepository)
    repo.db = mock_db
    repo.model = MagicMock()
    repo.logger = MagicMock()
    repo.invalidate_entity_cache = MagicMock()
    return repo, mock_db


def _extract_relationship_names(options_call: call) -> list[str]:
    """Extract relationship names from selectinload/joinedload args in .options() call.

    SQLAlchemy Load objects store the relationship key at arg.path[1].key.
    """
    names: list[str] = []
    for arg in options_call.args:
        path = getattr(arg, "path", None)
        if path and len(path) > 1:
            key = getattr(path[1], "key", None)
            if key:
                names.append(key)
    return names


class TestApplyFullEagerLoading:
    """Verify _apply_full_eager_loading includes video_session."""

    def test_includes_video_session(self) -> None:
        """_apply_full_eager_loading must include selectinload for video_session."""
        repo, _ = _make_repo()
        mock_query = MagicMock()

        repo._apply_full_eager_loading(mock_query)

        # .options() should have been called once
        mock_query.options.assert_called_once()

        # Extract the relationship names from the options call
        options_args = mock_query.options.call_args
        relationship_keys = _extract_relationship_names(options_args)

        assert "video_session" in relationship_keys, (
            f"video_session not in eager-loaded relationships: {relationship_keys}"
        )

    def test_includes_all_satellite_relationships(self) -> None:
        """All satellite relationships (including video_session) are eager-loaded."""
        repo, _ = _make_repo()
        mock_query = MagicMock()

        repo._apply_full_eager_loading(mock_query)

        options_args = mock_query.options.call_args
        relationship_keys = _extract_relationship_names(options_args)

        expected = {
            "student",
            "instructor",
            "instructor_service",
            "rescheduled_from",
            "cancelled_by",
            "payment_detail",
            "no_show_detail",
            "lock_detail",
            "reschedule_detail",
            "dispute",
            "transfer",
            "video_session",
        }
        assert expected.issubset(set(relationship_keys)), (
            f"Missing relationships: {expected - set(relationship_keys)}"
        )
