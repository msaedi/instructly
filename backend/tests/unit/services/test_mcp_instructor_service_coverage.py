"""Unit tests for MCP instructor service coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.mcp_instructor_service import (
    MCPInstructorService,
    _decode_cursor,
    _encode_cursor,
    derive_instructor_status,
)


class TestDeriveInstructorStatus:
    """Tests for derive_instructor_status function."""

    def test_status_live_when_is_live_true(self) -> None:
        """Line 19-20: Returns 'live' when is_live is True."""
        profile = MagicMock()
        profile.is_live = True
        assert derive_instructor_status(profile) == "live"

    def test_status_paused_when_onboarding_completed(self) -> None:
        """Lines 21-22: Returns 'paused' when onboarding completed but not live."""
        profile = MagicMock()
        profile.is_live = False
        profile.onboarding_completed_at = datetime.now(timezone.utc)
        assert derive_instructor_status(profile) == "paused"

    def test_status_onboarding_when_skills_configured(self) -> None:
        """Lines 23-24: Returns 'onboarding' when skills configured."""
        profile = MagicMock()
        profile.is_live = False
        profile.onboarding_completed_at = None
        profile.skills_configured = True
        profile.bgc_status = None
        assert derive_instructor_status(profile) == "onboarding"

    def test_status_onboarding_when_bgc_status_set(self) -> None:
        """Lines 23-24: Returns 'onboarding' when bgc_status is set."""
        profile = MagicMock()
        profile.is_live = False
        profile.onboarding_completed_at = None
        profile.skills_configured = False
        profile.bgc_status = "pending"
        assert derive_instructor_status(profile) == "onboarding"

    def test_status_registered_default(self) -> None:
        """Line 25: Returns 'registered' when no other conditions met."""
        profile = MagicMock()
        profile.is_live = False
        profile.onboarding_completed_at = None
        profile.skills_configured = False
        profile.bgc_status = None
        assert derive_instructor_status(profile) == "registered"


class TestEncodeCursor:
    """Tests for _encode_cursor function."""

    def test_encode_cursor_produces_base64(self) -> None:
        """Lines 29-30: _encode_cursor produces URL-safe base64 without padding."""
        result = _encode_cursor("test_value")
        assert isinstance(result, str)
        assert "=" not in result  # Padding stripped

    def test_encode_cursor_is_reversible(self) -> None:
        """Lines 29-30: _encode_cursor result can be decoded."""
        original = "01K2MAY484FQGFEQVN3VKGYZ58"
        encoded = _encode_cursor(original)
        decoded = _decode_cursor(encoded)
        assert decoded == original


class TestDecodeCursor:
    """Tests for _decode_cursor function."""

    def test_decode_cursor_returns_none_for_empty(self) -> None:
        """Lines 34-35: _decode_cursor returns None for empty cursor."""
        assert _decode_cursor(None) is None
        assert _decode_cursor("") is None

    def test_decode_cursor_handles_padding(self) -> None:
        """Lines 36-38: _decode_cursor restores padding and decodes."""
        original = "test_cursor"
        encoded = _encode_cursor(original)
        decoded = _decode_cursor(encoded)
        assert decoded == original

    def test_decode_cursor_invalid_raises_value_error(self) -> None:
        """Lines 39-41: _decode_cursor raises ValueError for invalid cursor."""
        with pytest.raises(ValueError, match="Invalid cursor"):
            _decode_cursor("!!!invalid!!!")


class TestMCPInstructorServiceListInstructors:
    """Tests for list_instructors method."""

    def test_list_instructors_builds_items(self) -> None:
        """Lines 82-89: list_instructors builds item dictionaries correctly."""
        db = MagicMock()

        # Create mock profile
        mock_user = MagicMock()
        mock_user.first_name = "John"
        mock_user.last_name = "Doe"
        mock_user.email = "john@example.com"

        mock_profile = MagicMock()
        mock_profile.id = "profile_123"
        mock_profile.user_id = "user_123"
        mock_profile.user = mock_user
        mock_profile.is_live = True
        mock_profile.is_founding_instructor = True
        mock_profile.founding_granted_at = datetime.now(timezone.utc)
        mock_profile.onboarding_completed_at = datetime.now(timezone.utc)

        # Mock repository methods
        with patch("app.services.mcp_instructor_service.MCPInstructorRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.list_instructors.return_value = ([mock_profile], "next_cursor_value")
            mock_repo.get_service_lists_for_profiles.return_value = {
                "user_123": {"services": ["Yoga"], "categories": ["Fitness"]}
            }
            mock_repo.get_booking_completed_counts.return_value = {"user_123": 10}
            mock_repo.get_review_stats.return_value = {"user_123": {"rating_avg": 4.5}}
            mock_repo_class.return_value = mock_repo

            service = MCPInstructorService(db)
            result = service.list_instructors(
                status=None,
                is_founding=None,
                service_slug=None,
                category_slug=None,
                limit=10,
                cursor=None,
            )

            assert "items" in result
            assert len(result["items"]) == 1

            item = result["items"][0]
            assert item["user_id"] == "user_123"
            assert item["name"] == "John Doe"
            assert item["email"] == "john@example.com"
            assert item["status"] == "live"
            assert item["is_founding"] is True
            assert item["services"] == ["Yoga"]
            assert item["categories"] == ["Fitness"]
            assert item["rating_avg"] == 4.5
            assert item["bookings_completed"] == 10
            assert item["admin_url"] == "/admin/instructors/profile_123"

    def test_list_instructors_handles_missing_names(self) -> None:
        """Lines 83-85: list_instructors handles missing first/last names."""
        db = MagicMock()

        mock_user = MagicMock()
        mock_user.first_name = None
        mock_user.last_name = None
        mock_user.email = "test@example.com"

        mock_profile = MagicMock()
        mock_profile.id = "profile_123"
        mock_profile.user_id = "user_123"
        mock_profile.user = mock_user
        mock_profile.is_live = False
        mock_profile.onboarding_completed_at = None
        mock_profile.skills_configured = False
        mock_profile.bgc_status = None
        mock_profile.is_founding_instructor = False
        mock_profile.founding_granted_at = None

        with patch("app.services.mcp_instructor_service.MCPInstructorRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.list_instructors.return_value = ([mock_profile], None)
            mock_repo.get_service_lists_for_profiles.return_value = {}
            mock_repo.get_booking_completed_counts.return_value = {}
            mock_repo.get_review_stats.return_value = {}
            mock_repo_class.return_value = mock_repo

            service = MCPInstructorService(db)
            result = service.list_instructors(
                status=None,
                is_founding=None,
                service_slug=None,
                category_slug=None,
                limit=10,
                cursor=None,
            )

            item = result["items"][0]
            assert item["name"] == ""
            assert item["services"] == []
            assert item["categories"] == []
            assert item["rating_avg"] == 0.0
            assert item["bookings_completed"] == 0

    def test_list_instructors_with_cursor_pagination(self) -> None:
        """Lines 62, 108: list_instructors handles cursor pagination."""
        db = MagicMock()

        with patch("app.services.mcp_instructor_service.MCPInstructorRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.list_instructors.return_value = ([], "raw_next")
            mock_repo.get_service_lists_for_profiles.return_value = {}
            mock_repo.get_booking_completed_counts.return_value = {}
            mock_repo.get_review_stats.return_value = {}
            mock_repo_class.return_value = mock_repo

            service = MCPInstructorService(db)
            cursor = _encode_cursor("previous_cursor")
            result = service.list_instructors(
                status=None,
                is_founding=None,
                service_slug=None,
                category_slug=None,
                limit=10,
                cursor=cursor,
            )

            assert result["next_cursor"] is not None


class TestMCPInstructorServiceGetInstructorDetail:
    """Tests for get_instructor_detail method."""

    def test_get_instructor_detail_skips_inactive_services(self) -> None:
        """Line 151: get_instructor_detail skips inactive services."""
        db = MagicMock()

        mock_user = MagicMock()
        mock_user.first_name = "Jane"
        mock_user.last_name = "Doe"
        mock_user.email = "jane@example.com"
        mock_user.phone = "555-1234"

        # Create mock services - one active, one inactive
        mock_active_service = MagicMock()
        mock_active_service.is_active = True
        mock_active_service.hourly_rate = 50.00
        mock_active_service.catalog_entry = MagicMock()
        mock_active_service.catalog_entry.name = "Yoga"
        mock_active_service.catalog_entry.slug = "yoga"
        mock_active_service.catalog_entry.category = MagicMock()
        mock_active_service.catalog_entry.category.name = "Fitness"

        mock_inactive_service = MagicMock()
        mock_inactive_service.is_active = False  # Should be skipped

        mock_profile = MagicMock()
        mock_profile.id = "profile_123"
        mock_profile.user_id = "user_123"
        mock_profile.user = mock_user
        mock_profile.is_live = True
        mock_profile.is_founding_instructor = False
        mock_profile.founding_granted_at = None
        mock_profile.onboarding_completed_at = datetime.now(timezone.utc)
        mock_profile.created_at = datetime.now(timezone.utc)
        mock_profile.updated_at = datetime.now(timezone.utc)
        mock_profile.identity_verified_at = None
        mock_profile.background_check_uploaded_at = None
        mock_profile.bgc_invited_at = None
        mock_profile.bgc_completed_at = None
        mock_profile.bgc_status = None
        mock_profile.bgc_valid_until = None
        mock_profile.response_rate = 0.95
        mock_profile.instructor_services = [mock_active_service, mock_inactive_service]

        with patch("app.services.mcp_instructor_service.MCPInstructorRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_instructor_by_identifier.return_value = mock_profile
            mock_repo.get_booking_stats.return_value = {"completed": 5, "cancelled": 1, "no_show": 0}
            mock_repo.get_review_stats_for_user.return_value = {"rating_avg": 4.8, "rating_count": 3}
            mock_repo_class.return_value = mock_repo

            service = MCPInstructorService(db)
            result = service.get_instructor_detail("user_123")

            # Only active service should be included
            assert len(result["services"]) == 1
            assert result["services"][0]["name"] == "Yoga"
            assert result["services"][0]["is_active"] is True

    def test_get_instructor_detail_handles_missing_catalog_entry(self) -> None:
        """Lines 152-153: get_instructor_detail handles missing catalog_entry."""
        db = MagicMock()

        mock_user = MagicMock()
        mock_user.first_name = "Test"
        mock_user.last_name = "User"
        mock_user.email = "test@example.com"
        mock_user.phone = None

        mock_service = MagicMock()
        mock_service.is_active = True
        mock_service.hourly_rate = 50.00
        mock_service.catalog_entry = None  # No catalog entry

        mock_profile = MagicMock()
        mock_profile.id = "profile_123"
        mock_profile.user_id = "user_123"
        mock_profile.user = mock_user
        mock_profile.is_live = False
        mock_profile.is_founding_instructor = False
        mock_profile.founding_granted_at = None
        mock_profile.onboarding_completed_at = None
        mock_profile.skills_configured = False
        mock_profile.bgc_status = None
        mock_profile.created_at = datetime.now(timezone.utc)
        mock_profile.updated_at = datetime.now(timezone.utc)
        mock_profile.identity_verified_at = None
        mock_profile.background_check_uploaded_at = None
        mock_profile.bgc_invited_at = None
        mock_profile.bgc_completed_at = None
        mock_profile.bgc_valid_until = None
        mock_profile.response_rate = None
        mock_profile.instructor_services = [mock_service]

        with patch("app.services.mcp_instructor_service.MCPInstructorRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_instructor_by_identifier.return_value = mock_profile
            mock_repo.get_booking_stats.return_value = {}
            mock_repo.get_review_stats_for_user.return_value = {}
            mock_repo_class.return_value = mock_repo

            service = MCPInstructorService(db)
            result = service.get_instructor_detail("user_123")

            assert len(result["services"]) == 1
            assert result["services"][0]["name"] == ""
            assert result["services"][0]["category"] == ""
            assert result["stats"]["response_rate"] is None


class TestMCPInstructorServiceGetServiceCoverage:
    """Tests for get_service_coverage method."""

    def test_get_service_coverage_returns_structure(self) -> None:
        """Lines 117-130: get_service_coverage returns correct structure."""
        db = MagicMock()

        with patch("app.services.mcp_instructor_service.MCPInstructorRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_service_coverage.return_value = {
                "labels": ["Yoga", "Piano"],
                "values": [10, 5],
                "total_instructors": 15,
                "total_services_offered": 20,
            }
            mock_repo_class.return_value = mock_repo

            service = MCPInstructorService(db)
            result = service.get_service_coverage(status="live", group_by="service", top=5)

            assert result["group_by"] == "service"
            assert result["labels"] == ["Yoga", "Piano"]
            assert result["values"] == [10, 5]
            assert result["total_instructors"] == 15
            assert result["total_services_offered"] == 20
