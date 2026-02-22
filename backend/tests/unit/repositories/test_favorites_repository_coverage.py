"""Unit tests for FavoritesRepository — targets missed lines.

Missed lines:
  68-77   add_favorite: IntegrityError handling + generic Exception re-raise
  114-117 remove_favorite: generic Exception re-raise
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.favorites_repository import FavoritesRepository


def _make_repo() -> tuple[FavoritesRepository, MagicMock]:
    mock_db = MagicMock()
    repo = FavoritesRepository.__new__(FavoritesRepository)
    repo.db = mock_db
    repo.model = MagicMock()
    repo.logger = MagicMock()
    return repo, mock_db


# ------------------------------------------------------------------
# add_favorite — lines 68-77
# ------------------------------------------------------------------


class TestAddFavoriteErrorPaths:
    """Cover IntegrityError and generic Exception in add_favorite."""

    def test_integrity_error_returns_none(self) -> None:
        """Lines 68-73: IntegrityError on commit → rollback + return None."""
        repo, mock_db = _make_repo()

        # is_favorited returns False (so we try to create)
        repo.is_favorited = MagicMock(return_value=False)

        # commit raises IntegrityError (race condition duplicate)
        mock_db.commit.side_effect = IntegrityError("dup", {}, None)

        result = repo.add_favorite("student_1", "instructor_1")

        assert result is None
        mock_db.rollback.assert_called_once()

    def test_generic_exception_rolls_back_and_raises(self) -> None:
        """Lines 74-77: Generic Exception on commit → rollback + re-raise."""
        repo, mock_db = _make_repo()

        repo.is_favorited = MagicMock(return_value=False)

        mock_db.commit.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            repo.add_favorite("student_1", "instructor_1")

        mock_db.rollback.assert_called_once()

    def test_generic_exception_on_add_rolls_back_and_raises(self) -> None:
        """Lines 74-77: Generic Exception on db.add → rollback + re-raise."""
        repo, mock_db = _make_repo()

        repo.is_favorited = MagicMock(return_value=False)

        mock_db.add.side_effect = RuntimeError("serialization failure")

        with pytest.raises(RuntimeError, match="serialization failure"):
            repo.add_favorite("student_1", "instructor_1")

        mock_db.rollback.assert_called_once()


# ------------------------------------------------------------------
# remove_favorite — lines 114-117
# ------------------------------------------------------------------


class TestRemoveFavoriteErrorPaths:
    """Cover the generic Exception path in remove_favorite."""

    def test_generic_exception_rolls_back_and_raises(self) -> None:
        """Lines 114-117: Exception during query → rollback + re-raise."""
        repo, mock_db = _make_repo()

        mock_db.query.side_effect = RuntimeError("db connection timeout")

        with pytest.raises(RuntimeError, match="db connection timeout"):
            repo.remove_favorite("student_1", "instructor_1")

        mock_db.rollback.assert_called_once()

    def test_exception_during_delete_rolls_back_and_raises(self) -> None:
        """Lines 114-117: Exception during db.delete → rollback + re-raise."""
        repo, mock_db = _make_repo()

        # query returns a favorite (found)
        favorite = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = favorite

        # delete raises
        mock_db.delete.side_effect = RuntimeError("constraint violation")

        with pytest.raises(RuntimeError, match="constraint violation"):
            repo.remove_favorite("student_1", "instructor_1")

        mock_db.rollback.assert_called_once()

    def test_exception_during_commit_rolls_back_and_raises(self) -> None:
        """Lines 114-117: Exception during commit → rollback + re-raise."""
        repo, mock_db = _make_repo()

        favorite = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = favorite
        mock_db.commit.side_effect = RuntimeError("deadlock detected")

        with pytest.raises(RuntimeError, match="deadlock detected"):
            repo.remove_favorite("student_1", "instructor_1")

        mock_db.rollback.assert_called_once()
