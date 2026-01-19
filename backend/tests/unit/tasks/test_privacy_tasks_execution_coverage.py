"""
Tests for privacy_tasks.py execution paths - targeting uncovered lines.

Covers lines: 87-112, 126-143, 157-187, 206-229, 251-266, 291-321.
"""

from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


class TestApplyRetentionPoliciesExecution:
    """Tests for apply_retention_policies task execution paths (lines 87-112)."""

    def test_successful_retention_policy_application(self) -> None:
        """Test successful execution of apply_retention_policies task."""
        from app.tasks.privacy_tasks import DatabaseTask, apply_retention_policies

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_retention_stats = MagicMock()
        mock_retention_stats.search_events_deleted = 100
        mock_retention_stats.old_bookings_anonymized = 50
        mock_privacy_service.apply_retention_policies.return_value = mock_retention_stats

        mock_cleanup_service = MagicMock()
        mock_cleanup_service.cleanup_all.return_value = (25, 10)

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch("app.tasks.privacy_tasks.SearchHistoryCleanupService") as mock_cleanup_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_cleanup_class.return_value = mock_cleanup_service
            mock_db_prop.return_value = mock_db

            result = apply_retention_policies.run()

            assert result["search_events_deleted"] == 100
            assert result["old_bookings_anonymized"] == 50
            assert result["soft_deleted_searches_removed"] == 25
            assert result["guest_sessions_removed"] == 10
            mock_privacy_class.assert_called_once_with(mock_db)
            mock_cleanup_class.assert_called_once_with(mock_db)

    def test_retention_policy_exception_propagated(self) -> None:
        """Test exception handling in apply_retention_policies (lines 110-112)."""
        from app.tasks.privacy_tasks import DatabaseTask, apply_retention_policies

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.apply_retention_policies.side_effect = Exception("Database error")

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Database error"):
                apply_retention_policies.run()

    def test_cleanup_service_exception_propagated(self) -> None:
        """Test exception from cleanup service is propagated."""
        from app.tasks.privacy_tasks import DatabaseTask, apply_retention_policies

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_retention_stats = MagicMock()
        mock_retention_stats.search_events_deleted = 100
        mock_retention_stats.old_bookings_anonymized = 50
        mock_privacy_service.apply_retention_policies.return_value = mock_retention_stats

        mock_cleanup_service = MagicMock()
        mock_cleanup_service.cleanup_all.side_effect = Exception("Cleanup failed")

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch("app.tasks.privacy_tasks.SearchHistoryCleanupService") as mock_cleanup_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_cleanup_class.return_value = mock_cleanup_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Cleanup failed"):
                apply_retention_policies.run()


class TestCleanupSearchHistoryExecution:
    """Tests for cleanup_search_history task execution paths (lines 126-143)."""

    def test_successful_search_history_cleanup(self) -> None:
        """Test successful execution of cleanup_search_history task."""
        from app.tasks.privacy_tasks import DatabaseTask, cleanup_search_history

        mock_db = MagicMock()

        mock_cleanup_service = MagicMock()
        mock_cleanup_service.cleanup_all.return_value = (50, 25)

        with patch("app.tasks.privacy_tasks.SearchHistoryCleanupService") as mock_cleanup_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_cleanup_class.return_value = mock_cleanup_service
            mock_db_prop.return_value = mock_db

            result = cleanup_search_history.run()

            assert result["soft_deleted_searches_removed"] == 50
            assert result["guest_sessions_removed"] == 25
            assert "cleanup_date" in result
            # Verify date is ISO format
            datetime.fromisoformat(result["cleanup_date"].replace("Z", "+00:00"))

    def test_search_history_cleanup_exception_propagated(self) -> None:
        """Test exception handling in cleanup_search_history (lines 141-143)."""
        from app.tasks.privacy_tasks import DatabaseTask, cleanup_search_history

        mock_db = MagicMock()

        mock_cleanup_service = MagicMock()
        mock_cleanup_service.cleanup_all.side_effect = Exception("Cleanup failed")

        with patch("app.tasks.privacy_tasks.SearchHistoryCleanupService") as mock_cleanup_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_cleanup_class.return_value = mock_cleanup_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Cleanup failed"):
                cleanup_search_history.run()

    def test_search_history_cleanup_with_zero_records(self) -> None:
        """Test cleanup when no records need to be cleaned."""
        from app.tasks.privacy_tasks import DatabaseTask, cleanup_search_history

        mock_db = MagicMock()

        mock_cleanup_service = MagicMock()
        mock_cleanup_service.cleanup_all.return_value = (0, 0)

        with patch("app.tasks.privacy_tasks.SearchHistoryCleanupService") as mock_cleanup_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_cleanup_class.return_value = mock_cleanup_service
            mock_db_prop.return_value = mock_db

            result = cleanup_search_history.run()

            assert result["soft_deleted_searches_removed"] == 0
            assert result["guest_sessions_removed"] == 0


class TestGeneratePrivacyReportExecution:
    """Tests for generate_privacy_report task execution paths (lines 157-187)."""

    def test_successful_privacy_report_generation(self) -> None:
        """Test successful execution of generate_privacy_report task."""
        from app.tasks.privacy_tasks import DatabaseTask, generate_privacy_report

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.get_privacy_statistics.return_value = {
            "total_users": 1000,
            "users_with_exports": 50,
        }

        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.return_value = {
            "soft_deleted_eligible": 100,
            "guest_sessions_eligible": 50,
        }

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch("app.tasks.privacy_tasks.SearchHistoryCleanupService") as mock_cleanup_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_cleanup_class.return_value = mock_cleanup_service
            mock_db_prop.return_value = mock_db

            result = generate_privacy_report.run()

            assert "report_date" in result
            assert result["privacy_statistics"]["total_users"] == 1000
            assert result["cleanup_statistics"]["soft_deleted_eligible"] == 100
            assert result["compliance_status"]["gdpr_data_export_enabled"] is True
            assert result["compliance_status"]["gdpr_data_deletion_enabled"] is True
            assert result["compliance_status"]["automated_retention_active"] is True

    def test_privacy_report_exception_propagated(self) -> None:
        """Test exception handling in generate_privacy_report (lines 185-187)."""
        from app.tasks.privacy_tasks import DatabaseTask, generate_privacy_report

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.get_privacy_statistics.side_effect = Exception("Stats error")

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Stats error"):
                generate_privacy_report.run()

    def test_privacy_report_cleanup_stats_exception(self) -> None:
        """Test exception from cleanup stats is propagated."""
        from app.tasks.privacy_tasks import DatabaseTask, generate_privacy_report

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.get_privacy_statistics.return_value = {}

        mock_cleanup_service = MagicMock()
        mock_cleanup_service.get_cleanup_statistics.side_effect = Exception("Cleanup stats error")

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch("app.tasks.privacy_tasks.SearchHistoryCleanupService") as mock_cleanup_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_cleanup_class.return_value = mock_cleanup_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Cleanup stats error"):
                generate_privacy_report.run()


class TestAnonymizeOldBookingsExecution:
    """Tests for anonymize_old_bookings task execution paths (lines 206-229)."""

    def test_successful_booking_anonymization(self) -> None:
        """Test successful execution of anonymize_old_bookings task."""
        from app.tasks.privacy_tasks import DatabaseTask, anonymize_old_bookings

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_retention_stats = MagicMock()
        mock_retention_stats.old_bookings_anonymized = 75
        mock_privacy_service.apply_retention_policies.return_value = mock_retention_stats

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            result = anonymize_old_bookings.run()

            assert result == 75
            mock_privacy_class.assert_called_once_with(mock_db)

    def test_booking_anonymization_with_custom_days_logs_warning(self) -> None:
        """Test that custom days_old logs a warning (lines 211-216)."""
        from app.tasks.privacy_tasks import DatabaseTask, anonymize_old_bookings

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_retention_stats = MagicMock()
        mock_retention_stats.old_bookings_anonymized = 30
        mock_privacy_service.apply_retention_policies.return_value = mock_retention_stats

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop, \
             patch("app.tasks.privacy_tasks.logger") as mock_logger:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            # Pass a custom days_old value that differs from default
            result = anonymize_old_bookings.run(days_old=365)

            assert result == 30
            # Verify warning was logged about custom days_old
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Custom days_old=365 requested" in warning_call

    def test_booking_anonymization_with_same_days_no_warning(self) -> None:
        """Test that matching days_old does not log a warning."""
        from app.tasks.privacy_tasks import DatabaseTask, anonymize_old_bookings

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_retention_stats = MagicMock()
        mock_retention_stats.old_bookings_anonymized = 30
        mock_privacy_service.apply_retention_policies.return_value = mock_retention_stats

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop, \
             patch("app.tasks.privacy_tasks.logger") as mock_logger:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            # Pass the default value (2555) - should not trigger warning
            result = anonymize_old_bookings.run(days_old=2555)

            assert result == 30
            # Verify warning was NOT called
            mock_logger.warning.assert_not_called()

    def test_booking_anonymization_exception_propagated(self) -> None:
        """Test exception handling in anonymize_old_bookings (lines 227-229)."""
        from app.tasks.privacy_tasks import DatabaseTask, anonymize_old_bookings

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.apply_retention_policies.side_effect = Exception("Anonymization error")

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Anonymization error"):
                anonymize_old_bookings.run()


class TestProcessDataExportRequestExecution:
    """Tests for process_data_export_request task execution paths (lines 251-266)."""

    def test_successful_data_export_request(self) -> None:
        """Test successful execution of process_data_export_request task."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_export_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.export_user_data.return_value = {
            "user_profile": {"name": "Test User"},
            "bookings": [],
            "messages": [],
        }

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            result = process_data_export_request.run(
                user_id="01K2MAY484FQGFEQVN3VKGYZ58",
                request_id="req-123",
            )

            assert result["user_profile"]["name"] == "Test User"
            assert result["request_id"] == "req-123"
            assert "processed_at" in result
            mock_privacy_service.export_user_data.assert_called_once_with(
                "01K2MAY484FQGFEQVN3VKGYZ58"
            )

    def test_data_export_without_request_id(self) -> None:
        """Test data export without optional request_id."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_export_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.export_user_data.return_value = {"user_profile": {}}

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            result = process_data_export_request.run(
                user_id="01K2MAY484FQGFEQVN3VKGYZ58",
            )

            assert result["request_id"] is None
            assert "processed_at" in result

    def test_data_export_exception_propagated(self) -> None:
        """Test exception handling in process_data_export_request (lines 264-266)."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_export_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.export_user_data.side_effect = Exception("Export failed")

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Export failed"):
                process_data_export_request.run(
                    user_id="01K2MAY484FQGFEQVN3VKGYZ58",
                )


class TestProcessDataDeletionRequestExecution:
    """Tests for process_data_deletion_request task execution paths (lines 291-321)."""

    def test_successful_data_deletion_with_account_delete(self) -> None:
        """Test data deletion with delete_account=True (lines 299-302)."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_deletion_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.delete_user_data.return_value = {
            "bookings_deleted": 10,
            "messages_deleted": 50,
            "account_deleted": True,
        }

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            result = process_data_deletion_request.run(
                user_id="01K2MAY484FQGFEQVN3VKGYZ58",
                delete_account=True,
                request_id="del-123",
            )

            assert result["user_id"] == "01K2MAY484FQGFEQVN3VKGYZ58"
            assert result["request_id"] == "del-123"
            assert result["delete_account"] is True
            assert result["deletion_stats"]["account_deleted"] is True
            assert "processed_at" in result
            mock_privacy_service.delete_user_data.assert_called_once_with(
                "01K2MAY484FQGFEQVN3VKGYZ58", delete_account=True
            )

    def test_successful_data_anonymization_without_account_delete(self) -> None:
        """Test data anonymization with delete_account=False (lines 303-306)."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_deletion_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.anonymize_user.return_value = True

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            result = process_data_deletion_request.run(
                user_id="01K2MAY484FQGFEQVN3VKGYZ58",
                delete_account=False,
            )

            assert result["user_id"] == "01K2MAY484FQGFEQVN3VKGYZ58"
            assert result["delete_account"] is False
            assert result["deletion_stats"]["anonymized"] == 1
            mock_privacy_service.anonymize_user.assert_called_once_with(
                "01K2MAY484FQGFEQVN3VKGYZ58"
            )

    def test_anonymization_failure_returns_zero(self) -> None:
        """Test that failed anonymization returns 0."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_deletion_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.anonymize_user.return_value = False

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            result = process_data_deletion_request.run(
                user_id="01K2MAY484FQGFEQVN3VKGYZ58",
                delete_account=False,
            )

            assert result["deletion_stats"]["anonymized"] == 0

    def test_data_deletion_without_request_id(self) -> None:
        """Test data deletion without optional request_id."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_deletion_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.anonymize_user.return_value = True

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            result = process_data_deletion_request.run(
                user_id="01K2MAY484FQGFEQVN3VKGYZ58",
            )

            assert result["request_id"] is None

    def test_data_deletion_exception_propagated(self) -> None:
        """Test exception handling in process_data_deletion_request (lines 319-321)."""
        from app.tasks.privacy_tasks import DatabaseTask, process_data_deletion_request

        mock_db = MagicMock()

        mock_privacy_service = MagicMock()
        mock_privacy_service.delete_user_data.side_effect = Exception("Deletion failed")

        with patch("app.tasks.privacy_tasks.PrivacyService") as mock_privacy_class, \
             patch.object(DatabaseTask, "db", new_callable=PropertyMock) as mock_db_prop:
            mock_privacy_class.return_value = mock_privacy_service
            mock_db_prop.return_value = mock_db

            with pytest.raises(Exception, match="Deletion failed"):
                process_data_deletion_request.run(
                    user_id="01K2MAY484FQGFEQVN3VKGYZ58",
                    delete_account=True,
                )


class TestDatabaseTaskBaseClass:
    """Tests for DatabaseTask base class methods."""

    def test_db_property_creates_session(self) -> None:
        """Test that db property creates a session when none exists."""
        from app.tasks.privacy_tasks import DatabaseTask

        mock_session = MagicMock()

        with patch("app.tasks.privacy_tasks.get_db") as mock_get_db:
            mock_get_db.return_value = iter([mock_session])

            task = DatabaseTask()
            task._db = None

            db = task.db

            assert db is mock_session
            mock_get_db.assert_called_once()

    def test_db_property_reuses_existing_session(self) -> None:
        """Test that db property reuses existing session."""
        from app.tasks.privacy_tasks import DatabaseTask

        mock_session = MagicMock()

        task = DatabaseTask()
        task._db = mock_session

        with patch("app.tasks.privacy_tasks.get_db") as mock_get_db:
            db = task.db

            assert db is mock_session
            mock_get_db.assert_not_called()

    def test_on_failure_closes_session(self) -> None:
        """Test that on_failure closes the session."""
        from app.tasks.privacy_tasks import DatabaseTask

        mock_session = MagicMock()

        task = DatabaseTask()
        task._db = mock_session

        task.on_failure(
            exc=Exception("Test error"),
            task_id="test-task-id",
            args=(),
            kwargs={},
            einfo=None,
        )

        mock_session.close.assert_called_once()
        assert task._db is None

    def test_on_failure_with_no_session(self) -> None:
        """Test that on_failure handles no session gracefully."""
        from app.tasks.privacy_tasks import DatabaseTask

        task = DatabaseTask()
        task._db = None

        # Should not raise
        task.on_failure(
            exc=Exception("Test error"),
            task_id="test-task-id",
            args=(),
            kwargs={},
            einfo=None,
        )

        assert task._db is None

    def test_on_success_closes_session(self) -> None:
        """Test that on_success closes the session."""
        from app.tasks.privacy_tasks import DatabaseTask

        mock_session = MagicMock()

        task = DatabaseTask()
        task._db = mock_session

        task.on_success(
            retval={"result": "success"},
            task_id="test-task-id",
            args=(),
            kwargs={},
        )

        mock_session.close.assert_called_once()
        assert task._db is None

    def test_on_success_with_no_session(self) -> None:
        """Test that on_success handles no session gracefully."""
        from app.tasks.privacy_tasks import DatabaseTask

        task = DatabaseTask()
        task._db = None

        # Should not raise
        task.on_success(
            retval={"result": "success"},
            task_id="test-task-id",
            args=(),
            kwargs={},
        )

        assert task._db is None
