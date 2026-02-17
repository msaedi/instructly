"""Unit tests for AvailabilityRepository — targets missed lines.

Missed lines:
  93-95   create_blackout_date: SQLAlchemyError path (non-IntegrityError)
  126-128 delete_blackout_date: SQLAlchemyError path
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.repositories.availability_repository import AvailabilityRepository


def _make_repo() -> tuple[AvailabilityRepository, MagicMock]:
    mock_db = MagicMock()
    repo = AvailabilityRepository.__new__(AvailabilityRepository)
    repo.db = mock_db
    repo.logger = MagicMock()
    return repo, mock_db


# ------------------------------------------------------------------
# create_blackout_date — lines 93-95
# ------------------------------------------------------------------


class TestCreateBlackoutDate:
    """Cover the SQLAlchemyError (non-IntegrityError) path."""

    def test_sqlalchemy_error_raises_repository_exception(self) -> None:
        """Lines 93-95: SQLAlchemyError on add/flush → RepositoryException."""
        repo, mock_db = _make_repo()

        mock_db.add.side_effect = SQLAlchemyError("connection reset")

        with pytest.raises(RepositoryException, match="Failed to create blackout"):
            repo.create_blackout_date("inst_1", date(2025, 7, 4), reason="holiday")

    def test_sqlalchemy_error_on_flush(self) -> None:
        """Lines 93-95: SQLAlchemyError on flush → RepositoryException."""
        repo, mock_db = _make_repo()

        mock_db.flush.side_effect = SQLAlchemyError("disk full")

        with pytest.raises(RepositoryException, match="Failed to create blackout"):
            repo.create_blackout_date("inst_1", date(2025, 12, 25))


# ------------------------------------------------------------------
# delete_blackout_date — lines 126-128
# ------------------------------------------------------------------


class TestDeleteBlackoutDate:
    """Cover the SQLAlchemyError path in delete_blackout_date."""

    def test_sqlalchemy_error_raises_repository_exception(self) -> None:
        """Lines 126-128: SQLAlchemyError → RepositoryException."""
        repo, mock_db = _make_repo()

        mock_db.query.return_value.filter.return_value.delete.side_effect = SQLAlchemyError(
            "lock timeout"
        )

        with pytest.raises(RepositoryException, match="Failed to delete blackout"):
            repo.delete_blackout_date("blackout_1", "inst_1")

    def test_sqlalchemy_error_on_flush_after_delete(self) -> None:
        """Lines 126-128: SQLAlchemyError on flush after delete → RepositoryException."""
        repo, mock_db = _make_repo()

        mock_db.query.return_value.filter.return_value.delete.return_value = 1
        mock_db.flush.side_effect = SQLAlchemyError("serialization failure")

        with pytest.raises(RepositoryException, match="Failed to delete blackout"):
            repo.delete_blackout_date("blackout_1", "inst_1")
