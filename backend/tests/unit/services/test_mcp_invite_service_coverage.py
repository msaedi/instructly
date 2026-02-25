"""
Coverage tests for mcp_invite_service.py targeting missed lines.

Targets:
  - L141: get_invite_detail by code fallback
  - L166,168: _invite_to_detail history branches
  - L190: _resolve_status expired branch
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services.mcp_invite_service import MCPInviteService


def _make_service() -> MCPInviteService:
    """Create MCPInviteService with mocked dependencies."""
    svc = MCPInviteService.__new__(MCPInviteService)
    svc.db = MagicMock()
    svc._audit_repo = MagicMock()
    svc._beta_invite_repo = MagicMock()
    svc._profile_repo = MagicMock()
    svc._config_service = MagicMock()
    svc._user_repo = MagicMock()
    return svc


def _make_invite(
    *,
    used_at=None,
    expires_at=None,
    code="INVITE_CODE",
):
    """Create a mock BetaInvite."""
    invite = MagicMock()
    invite.id = "INV_01"
    invite.code = code
    invite.email = "test@example.com"
    invite.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    invite.expires_at = expires_at
    invite.used_at = used_at
    invite.used_by_user_id = None
    invite.role = "instructor"
    invite.grant_founding_status = False
    invite.metadata_json = {}
    return invite


@pytest.mark.unit
class TestGetInviteDetail:
    """Cover get_invite_detail fallback and empty paths."""

    def test_found_by_id(self):
        """L140: invite found by ID."""
        svc = _make_service()
        invite = _make_invite()
        svc._beta_invite_repo.get_by_id.return_value = invite

        result = svc.get_invite_detail("INV_01")
        assert result["id"] == "INV_01"

    def test_fallback_to_code(self):
        """L141-142: not found by ID -> tries code."""
        svc = _make_service()
        invite = _make_invite()
        svc._beta_invite_repo.get_by_id.return_value = None
        svc._beta_invite_repo.get_by_code.return_value = invite

        result = svc.get_invite_detail("INVITE_CODE")
        assert result["id"] == "INV_01"

    def test_not_found_returns_empty(self):
        """L143-144: neither ID nor code found -> returns {}."""
        svc = _make_service()
        svc._beta_invite_repo.get_by_id.return_value = None
        svc._beta_invite_repo.get_by_code.return_value = None

        result = svc.get_invite_detail("UNKNOWN")
        assert result == {}


@pytest.mark.unit
class TestInviteToDetail:
    """Cover _invite_to_detail history building."""

    def test_accepted_invite_history(self):
        """L165-166: used_at set -> history includes 'accepted'."""
        svc = _make_service()
        invite = _make_invite(used_at=datetime(2024, 1, 2, tzinfo=timezone.utc))

        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        result = svc._invite_to_detail(invite, now)
        statuses = [h["status"] for h in result["status_history"]]
        assert "accepted" in statuses
        assert result["status"] == "accepted"

    def test_expired_invite_history(self):
        """L167-168: expires_at in past, not used -> history includes 'expired'."""
        svc = _make_service()
        invite = _make_invite(expires_at=datetime(2024, 1, 15, tzinfo=timezone.utc))

        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        result = svc._invite_to_detail(invite, now)
        statuses = [h["status"] for h in result["status_history"]]
        assert "expired" in statuses
        assert result["status"] == "expired"

    def test_pending_invite_history(self):
        """Neither used nor expired -> only 'pending' in history."""
        svc = _make_service()
        invite = _make_invite(expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc))

        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        result = svc._invite_to_detail(invite, now)
        assert len(result["status_history"]) == 1
        assert result["status_history"][0]["status"] == "pending"
        assert result["status"] == "pending"


@pytest.mark.unit
class TestResolveStatus:
    """Cover _resolve_status branches."""

    def test_accepted(self):
        invite = _make_invite(used_at=datetime(2024, 1, 2, tzinfo=timezone.utc))
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert MCPInviteService._resolve_status(invite, now) == "accepted"

    def test_expired(self):
        """L189: expires_at < now -> expired."""
        invite = _make_invite(expires_at=datetime(2024, 1, 15, tzinfo=timezone.utc))
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert MCPInviteService._resolve_status(invite, now) == "expired"

    def test_pending(self):
        invite = _make_invite(expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert MCPInviteService._resolve_status(invite, now) == "pending"

    def test_no_expires_at_pending(self):
        """L189: expires_at is None -> pending."""
        invite = _make_invite(expires_at=None)
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert MCPInviteService._resolve_status(invite, now) == "pending"


@pytest.mark.unit
class TestListInvites:
    """Cover list_invites."""

    def test_list_with_results(self):
        svc = _make_service()
        invite = _make_invite()
        svc._beta_invite_repo.list_invites.return_value = ([invite], "cursor_abc")

        result = svc.list_invites()
        assert result["count"] == 1
        assert result["next_cursor"] == "cursor_abc"

    def test_list_empty(self):
        svc = _make_service()
        svc._beta_invite_repo.list_invites.return_value = ([], None)

        result = svc.list_invites()
        assert result["count"] == 0
        assert result["next_cursor"] is None


@pytest.mark.unit
class TestGetFoundingCapRemaining:
    """Cover get_founding_cap_remaining edge cases."""

    def test_invalid_cap_defaults_to_100(self):
        """L43-44: cap_raw is invalid -> defaults to 100."""
        svc = _make_service()
        svc._config_service.get_pricing_config.return_value = (
            {"founding_instructor_cap": "not_a_number"},
            None,
        )
        svc._profile_repo.count_founding_instructors.return_value = 0

        result = svc.get_founding_cap_remaining()
        assert result == 100

    def test_used_exceeds_cap(self):
        """L46: used > cap -> returns 0."""
        svc = _make_service()
        svc._config_service.get_pricing_config.return_value = (
            {"founding_instructor_cap": 10},
            None,
        )
        svc._profile_repo.count_founding_instructors.return_value = 15

        result = svc.get_founding_cap_remaining()
        assert result == 0
