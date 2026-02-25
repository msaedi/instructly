"""
Coverage tests for badge_admin_service.py targeting missed lines.

Targets:
  - L24: _student_display_name fallback to email/id when no first/last name
  - L65,74: NotFoundException in confirm_award/revoke_award when get_award_with_details returns None
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services.badge_admin_service import BadgeAdminService, _student_display_name


@pytest.mark.unit
class TestStudentDisplayName:
    """Cover _student_display_name edge cases."""

    def test_both_names_present(self):
        """Standard case: first and last name -> 'First L.'"""
        user = MagicMock()
        user.first_name = "John"
        user.last_name = "Doe"
        assert _student_display_name(user) == "John D."

    def test_first_name_only(self):
        """Only first name -> 'First'."""
        user = MagicMock()
        user.first_name = "John"
        user.last_name = ""
        assert _student_display_name(user) == "John"

    def test_last_name_only(self):
        """Only last name -> 'L.'"""
        user = MagicMock()
        user.first_name = ""
        user.last_name = "Doe"
        assert _student_display_name(user) == "D."

    def test_no_names_fallback_to_email(self):
        """L24: No first/last name -> fallback to email."""
        user = MagicMock()
        user.first_name = ""
        user.last_name = ""
        user.email = "john@example.com"
        user.id = "USR_01"
        assert _student_display_name(user) == "john@example.com"

    def test_no_names_no_email_fallback_to_id(self):
        """L24: No first/last name, no email -> fallback to id."""
        user = MagicMock()
        user.first_name = ""
        user.last_name = ""
        user.email = None
        user.id = "USR_01ABC"
        assert _student_display_name(user) == "USR_01ABC"

    def test_none_names_fallback_to_email(self):
        """L24: None first/last name -> fallback to email."""
        user = MagicMock()
        user.first_name = None
        user.last_name = None
        user.email = "test@example.com"
        user.id = "USR_02"
        assert _student_display_name(user) == "test@example.com"

    def test_whitespace_only_names(self):
        """L24: Whitespace-only names -> fallback to email."""
        user = MagicMock()
        user.first_name = "   "
        user.last_name = "   "
        user.email = "space@test.com"
        user.id = "USR_03"
        assert _student_display_name(user) == "space@test.com"


def _make_admin_service() -> BadgeAdminService:
    """Create BadgeAdminService with mocked dependencies."""
    svc = BadgeAdminService.__new__(BadgeAdminService)
    svc.db = MagicMock()
    svc.repository = MagicMock()
    return svc


@pytest.mark.unit
class TestConfirmAward:
    """Cover confirm_award error paths."""

    def test_update_fails_not_found(self):
        """L61-62: update_award_status returns None -> NotFoundException."""
        svc = _make_admin_service()
        svc.repository.update_award_status.return_value = None

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException, match="Award not found or not pending"):
            svc.confirm_award("AWARD_01", datetime.now(timezone.utc))

    def test_get_details_returns_none_after_update(self):
        """L64-65: update succeeds but get_award_with_details returns None -> NotFoundException."""
        svc = _make_admin_service()
        svc.repository.update_award_status.return_value = True
        svc.repository.get_award_with_details.return_value = None

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException, match="Award not found"):
            svc.confirm_award("AWARD_01", datetime.now(timezone.utc))

    def test_confirm_success(self):
        """Happy path: confirm works."""
        svc = _make_admin_service()
        svc.repository.update_award_status.return_value = True

        mock_award = MagicMock()
        mock_award.id = "AWARD_01"
        mock_award.status = "confirmed"
        mock_award.awarded_at = datetime.now(timezone.utc)
        mock_award.hold_until = None
        mock_award.confirmed_at = datetime.now(timezone.utc)
        mock_award.revoked_at = None
        mock_award.progress_snapshot = {}

        mock_badge = MagicMock()
        mock_badge.id = "BADGE_01"
        mock_badge.slug = "test"
        mock_badge.name = "Test Badge"
        mock_badge.criteria_type = "milestone"

        mock_user = MagicMock()
        mock_user.id = "USR_01"
        mock_user.email = "test@example.com"
        mock_user.first_name = "Jane"
        mock_user.last_name = "Doe"

        svc.repository.get_award_with_details.return_value = (mock_award, mock_badge, mock_user)

        result = svc.confirm_award("AWARD_01", datetime.now(timezone.utc))
        assert result["status"] == "confirmed"
        assert result["student"]["display_name"] == "Jane D."


@pytest.mark.unit
class TestRevokeAward:
    """Cover revoke_award error paths."""

    def test_update_fails_not_found(self):
        """L69-70: update_award_status returns None -> NotFoundException."""
        svc = _make_admin_service()
        svc.repository.update_award_status.return_value = None

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException, match="Award not found or not pending"):
            svc.revoke_award("AWARD_01", datetime.now(timezone.utc))

    def test_get_details_returns_none_after_update(self):
        """L72-74: update succeeds but get_award_with_details returns None -> NotFoundException."""
        svc = _make_admin_service()
        svc.repository.update_award_status.return_value = True
        svc.repository.get_award_with_details.return_value = None

        from app.core.exceptions import NotFoundException
        with pytest.raises(NotFoundException, match="Award not found"):
            svc.revoke_award("AWARD_01", datetime.now(timezone.utc))


@pytest.mark.unit
class TestListAwards:
    """Cover list_awards pagination logic."""

    def test_list_awards_with_next_offset(self):
        """L52: offset + len < total -> next_offset set."""
        svc = _make_admin_service()

        mock_award = MagicMock()
        mock_badge = MagicMock()
        mock_badge.id = "B1"
        mock_badge.slug = "test"
        mock_badge.name = "Test"
        mock_badge.criteria_type = "milestone"
        mock_user = MagicMock()
        mock_user.id = "U1"
        mock_user.email = "u@t.com"
        mock_user.first_name = "A"
        mock_user.last_name = "B"

        svc.repository.list_awards.return_value = ([(mock_award, mock_badge, mock_user)], 10)

        result = svc.list_awards(status=None, before=None, limit=1, offset=0)
        assert result["next_offset"] == 1
        assert result["total"] == 10

    def test_list_awards_no_next_offset(self):
        """L52: offset + len >= total -> next_offset is None."""
        svc = _make_admin_service()
        svc.repository.list_awards.return_value = ([], 0)

        result = svc.list_awards(status=None, before=None, limit=10, offset=0)
        assert result["next_offset"] is None
        assert result["total"] == 0
