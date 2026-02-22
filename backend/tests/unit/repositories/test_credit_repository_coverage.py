"""Unit tests for CreditRepository — targets missed lines and branch partials.

Missed lines:
  203-204 list_credits_for_user: include_expired=False branch (exclude expired credits)
  213-215 list_credits_for_user: exception path
  230->232 get_revoked_credits_for_user: revoked_reason filter branch
  234-236 get_revoked_credits_for_user: exception path
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import RepositoryException
from app.repositories.credit_repository import CreditRepository


def _make_repo() -> tuple[CreditRepository, MagicMock]:
    mock_db = MagicMock()
    repo = CreditRepository.__new__(CreditRepository)
    repo.db = mock_db
    repo.model = MagicMock()
    repo.logger = MagicMock()
    return repo, mock_db


# ------------------------------------------------------------------
# list_credits_for_user — lines 203-204, 213-215
# ------------------------------------------------------------------


class TestListCreditsForUser:
    """Cover the include_expired=False branch and error path."""

    def test_exclude_expired_adds_extra_filter(self) -> None:
        """Lines 203-204: include_expired=False → adds filter excluding expired."""
        repo, mock_db = _make_repo()

        chain = mock_db.query.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.all.return_value = []

        result = repo.list_credits_for_user(user_id="user_1", include_expired=False)

        assert result == []
        # Verify the extra filter was applied (filter called on top of initial filter)
        chain.filter.assert_called()

    def test_include_expired_true_skips_extra_filter(self) -> None:
        """Lines 202-211: include_expired=True → no extra filter."""
        repo, mock_db = _make_repo()

        chain = mock_db.query.return_value.filter.return_value
        chain.order_by.return_value.all.return_value = ["credit_1"]

        result = repo.list_credits_for_user(user_id="user_1", include_expired=True)

        assert result == ["credit_1"]

    def test_exception_wraps_in_repository_exception(self) -> None:
        """Lines 213-215: Exception during query → RepositoryException."""
        repo, mock_db = _make_repo()

        mock_db.query.side_effect = RuntimeError("connection pool exhausted")

        with pytest.raises(RepositoryException, match="Failed to list credits"):
            repo.list_credits_for_user(user_id="user_1")


# ------------------------------------------------------------------
# get_revoked_credits_for_user — lines 230->232, 234-236
# ------------------------------------------------------------------


class TestGetRevokedCreditsForUser:
    """Cover the revoked_reason filter branch and error path."""

    def test_with_revoked_reason_adds_filter(self) -> None:
        """Line 231: revoked_reason is truthy → adds extra filter."""
        repo, mock_db = _make_repo()

        chain = (
            mock_db.query.return_value
            .filter.return_value
            .filter.return_value
        )
        chain.filter.return_value.order_by.return_value.all.return_value = []

        result = repo.get_revoked_credits_for_user(
            user_id="user_1", revoked_reason="admin_action"
        )

        assert result == []

    def test_without_revoked_reason_skips_filter(self) -> None:
        """Line 230: revoked_reason is None → no extra filter."""
        repo, mock_db = _make_repo()

        chain = (
            mock_db.query.return_value
            .filter.return_value
            .filter.return_value
        )
        chain.order_by.return_value.all.return_value = ["credit_revoked"]

        result = repo.get_revoked_credits_for_user(user_id="user_1")

        assert result == ["credit_revoked"]

    def test_exception_wraps_in_repository_exception(self) -> None:
        """Lines 234-236: Exception during query → RepositoryException."""
        repo, mock_db = _make_repo()

        mock_db.query.side_effect = RuntimeError("db offline")

        with pytest.raises(RepositoryException, match="Failed to load revoked credits"):
            repo.get_revoked_credits_for_user(user_id="user_1")
