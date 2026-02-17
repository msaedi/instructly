"""Tests targeting missed lines in app/services/privacy_service.py.

Missed lines:
  249-250: delete_user_data: account_status assignment raises
  258-259: delete_user_data: phone assignment raises
  262-263: delete_user_data: zip_code assignment raises
  285->292: apply_retention_policies: settings has search_event_retention_days
  292->307: apply_retention_policies: settings has booking_pii_retention_days
  324->330: get_privacy_statistics: settings has search_event_retention_days
"""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch


class TestPrivacyServiceMissedLines:
    """Test missed lines in PrivacyService."""

    def _make_service(self):
        """Create a PrivacyService with all mocked repositories."""
        mock_db = MagicMock()

        with patch("app.services.privacy_service.RepositoryFactory") as MockFactory:
            mock_user_repo = MagicMock()
            mock_booking_repo = MagicMock()
            mock_instructor_repo = MagicMock()
            mock_search_history_repo = MagicMock()
            mock_search_event_repo = MagicMock()
            mock_service_area_repo = MagicMock()

            MockFactory.create_user_repository.return_value = mock_user_repo
            MockFactory.create_booking_repository.return_value = mock_booking_repo
            MockFactory.create_instructor_profile_repository.return_value = mock_instructor_repo
            MockFactory.create_search_history_repository.return_value = mock_search_history_repo
            MockFactory.create_search_event_repository.return_value = mock_search_event_repo
            MockFactory.create_instructor_service_area_repository.return_value = mock_service_area_repo

            from app.services.privacy_service import PrivacyService

            svc = PrivacyService(mock_db)

        return svc

    def test_delete_user_data_account_status_raises(self) -> None:
        """Lines 249-250: setting account_status raises an exception (caught)."""
        svc = self._make_service()

        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.is_active = True

        # Make account_status assignment raise
        type(mock_user).account_status = PropertyMock(side_effect=AttributeError("no attr"))
        # But still allow reading
        mock_user.email = "test@example.com"
        mock_user.first_name = "Test"
        mock_user.last_name = "User"

        svc.user_repository.get_by_id.return_value = mock_user
        svc.booking_repository.get_student_bookings.return_value = []
        svc.booking_repository.get_instructor_bookings.return_value = []
        svc.search_history_repository.delete_user_searches.return_value = 0
        svc.search_event_repository.delete_user_events.return_value = 0
        svc.instructor_repository.get_by_user_id.return_value = None

        # Should not raise despite account_status error
        result = svc.delete_user_data("user123", delete_account=True)
        assert "search_history" in result

    def test_delete_user_data_phone_assignment_raises(self) -> None:
        """Lines 258-259: phone assignment raises (caught)."""
        svc = self._make_service()

        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.is_active = True
        mock_user.account_status = "active"

        # Make phone setter raise
        type(mock_user).phone = PropertyMock(side_effect=AttributeError("no phone"))

        svc.user_repository.get_by_id.return_value = mock_user
        svc.booking_repository.get_student_bookings.return_value = []
        svc.booking_repository.get_instructor_bookings.return_value = []
        svc.search_history_repository.delete_user_searches.return_value = 0
        svc.search_event_repository.delete_user_events.return_value = 0
        svc.instructor_repository.get_by_user_id.return_value = None

        result = svc.delete_user_data("user123", delete_account=True)
        assert "search_history" in result

    def test_delete_user_data_zip_code_assignment_raises(self) -> None:
        """Lines 262-263: zip_code assignment raises (caught)."""
        svc = self._make_service()

        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.is_active = True
        mock_user.account_status = "active"
        mock_user.phone = "555-1234"

        # Make zip_code setter raise
        type(mock_user).zip_code = PropertyMock(side_effect=AttributeError("no zip"))

        svc.user_repository.get_by_id.return_value = mock_user
        svc.booking_repository.get_student_bookings.return_value = []
        svc.booking_repository.get_instructor_bookings.return_value = []
        svc.search_history_repository.delete_user_searches.return_value = 0
        svc.search_event_repository.delete_user_events.return_value = 0
        svc.instructor_repository.get_by_user_id.return_value = None

        result = svc.delete_user_data("user123", delete_account=True)
        assert "search_history" in result

    def test_apply_retention_policies_with_search_event_retention(self) -> None:
        """Lines 285->292: settings has search_event_retention_days."""
        svc = self._make_service()

        with patch("app.services.privacy_service.settings") as mock_settings:
            mock_settings.search_event_retention_days = 90
            # Remove booking_pii_retention_days attr
            del mock_settings.booking_pii_retention_days

            svc.search_event_repository.delete_old_events.return_value = 5

            result = svc.apply_retention_policies()
            assert result.search_events_deleted == 5

    def test_apply_retention_policies_with_booking_retention(self) -> None:
        """Lines 292->307: settings has booking_pii_retention_days."""
        svc = self._make_service()

        with patch("app.services.privacy_service.settings") as mock_settings:
            mock_settings.search_event_retention_days = 90
            mock_settings.booking_pii_retention_days = 365

            svc.search_event_repository.delete_old_events.return_value = 0
            svc.booking_repository.count_old_bookings.return_value = 10

            result = svc.apply_retention_policies()
            assert result.old_bookings_anonymized == 10

    def test_get_privacy_statistics_with_retention_days(self) -> None:
        """Lines 324->330: settings has search_event_retention_days."""
        svc = self._make_service()

        with patch("app.services.privacy_service.settings") as mock_settings:
            mock_settings.search_event_retention_days = 90

            svc.user_repository.count_all.return_value = 100
            svc.user_repository.count_active.return_value = 80
            svc.search_history_repository.count_all_searches.return_value = 500
            svc.search_event_repository.count_all_events.return_value = 1000
            svc.booking_repository.count.return_value = 50
            svc.search_event_repository.count_old_events.return_value = 200

            result = svc.get_privacy_statistics()
            assert result.search_events_eligible_for_deletion == 200

    def test_get_privacy_statistics_without_retention_days(self) -> None:
        """Lines 324->330: settings does NOT have search_event_retention_days."""
        svc = self._make_service()

        with patch("app.services.privacy_service.settings") as mock_settings:
            # Remove the attribute
            del mock_settings.search_event_retention_days

            svc.user_repository.count_all.return_value = 100
            svc.user_repository.count_active.return_value = 80
            svc.search_history_repository.count_all_searches.return_value = 500
            svc.search_event_repository.count_all_events.return_value = 1000
            svc.booking_repository.count.return_value = 50

            result = svc.get_privacy_statistics()
            assert result.search_events_eligible_for_deletion is None
