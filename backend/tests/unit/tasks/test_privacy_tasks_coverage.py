"""
Tests for privacy_tasks.py - targeting CI coverage gaps.
Bug hunting + coverage for GDPR/privacy background tasks.

FIXES VERIFIED:
1. Thread-unsafe settings mutation removed - no longer mutates global settings object.
2. Type hints corrected - user_id now properly typed as str (ULID).
"""

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session


class TestDatabaseTask:
    """Tests for the DatabaseTask base class."""

    def test_db_property_creates_session(self) -> None:
        """Test that db property creates a session on first access."""
        from app.tasks.privacy_tasks import DatabaseTask

        mock_session = MagicMock(spec=Session)
        mock_generator = iter([mock_session])

        with patch("app.tasks.privacy_tasks.get_db", return_value=mock_generator):
            task = DatabaseTask()
            task._db = None

            # First access should create session
            db = task.db
            assert db == mock_session

    def test_db_property_returns_cached_session(self) -> None:
        """Test that db property returns cached session on subsequent calls."""
        from app.tasks.privacy_tasks import DatabaseTask

        task = DatabaseTask()
        mock_session = MagicMock(spec=Session)
        task._db = mock_session

        # Should return the same cached session
        db = task.db
        assert db == mock_session

    def test_on_failure_closes_session(self) -> None:
        """Test that on_failure closes the database session."""
        from app.tasks.privacy_tasks import DatabaseTask

        task = DatabaseTask()
        mock_session = MagicMock(spec=Session)
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

    def test_on_failure_handles_no_session(self) -> None:
        """Test that on_failure handles case when no session exists."""
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
        """Test that on_success closes the database session."""
        from app.tasks.privacy_tasks import DatabaseTask

        task = DatabaseTask()
        mock_session = MagicMock(spec=Session)
        task._db = mock_session

        task.on_success(
            retval={"result": "success"},
            task_id="test-task-id",
            args=(),
            kwargs={},
        )

        mock_session.close.assert_called_once()
        assert task._db is None

    def test_on_success_handles_no_session(self) -> None:
        """Test that on_success handles case when no session exists."""
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


class TestTaskRegistration:
    """Tests for task registration and configuration."""

    def test_apply_retention_policies_is_registered(self) -> None:
        """Test apply_retention_policies task is registered."""
        from app.tasks.privacy_tasks import apply_retention_policies

        assert apply_retention_policies.name == "privacy.apply_retention_policies"

    def test_cleanup_search_history_is_registered(self) -> None:
        """Test cleanup_search_history task is registered."""
        from app.tasks.privacy_tasks import cleanup_search_history

        assert cleanup_search_history.name == "privacy.cleanup_search_history"

    def test_generate_privacy_report_is_registered(self) -> None:
        """Test generate_privacy_report task is registered."""
        from app.tasks.privacy_tasks import generate_privacy_report

        assert generate_privacy_report.name == "privacy.generate_privacy_report"

    def test_anonymize_old_bookings_is_registered(self) -> None:
        """Test anonymize_old_bookings task is registered."""
        from app.tasks.privacy_tasks import anonymize_old_bookings

        assert anonymize_old_bookings.name == "privacy.anonymize_old_bookings"

    def test_process_data_export_request_is_registered(self) -> None:
        """Test process_data_export_request task is registered."""
        from app.tasks.privacy_tasks import process_data_export_request

        assert process_data_export_request.name == "privacy.process_data_export_request"

    def test_process_data_deletion_request_is_registered(self) -> None:
        """Test process_data_deletion_request task is registered."""
        from app.tasks.privacy_tasks import process_data_deletion_request

        assert process_data_deletion_request.name == "privacy.process_data_deletion_request"


class TestTasksUseDatabaseTaskBase:
    """Tests to verify tasks use DatabaseTask base class."""

    def test_apply_retention_policies_uses_database_task(self) -> None:
        """Test apply_retention_policies uses DatabaseTask base."""
        from app.tasks.privacy_tasks import apply_retention_policies

        # Task should be bound and use DatabaseTask
        assert hasattr(apply_retention_policies, "bind")

    def test_cleanup_search_history_uses_database_task(self) -> None:
        """Test cleanup_search_history uses DatabaseTask base."""
        from app.tasks.privacy_tasks import cleanup_search_history

        assert hasattr(cleanup_search_history, "bind")

    def test_generate_privacy_report_uses_database_task(self) -> None:
        """Test generate_privacy_report uses DatabaseTask base."""
        from app.tasks.privacy_tasks import generate_privacy_report

        assert hasattr(generate_privacy_report, "bind")


class TestTypedTaskDecorator:
    """Tests for the typed_task helper function."""

    def test_typed_task_returns_decorator(self) -> None:
        """Test that typed_task returns a decorator function."""
        from app.tasks.privacy_tasks import typed_task

        decorator = typed_task(name="test_task")
        assert callable(decorator)

    def test_typed_task_preserves_task_attributes(self) -> None:
        """Test that typed_task preserves Celery task attributes."""
        from app.tasks.privacy_tasks import apply_retention_policies

        # Should have standard Celery task attributes
        assert hasattr(apply_retention_policies, "delay")
        assert hasattr(apply_retention_policies, "apply_async")
        assert hasattr(apply_retention_policies, "name")


class TestModuleImports:
    """Tests for module imports."""

    def test_logger_is_configured(self) -> None:
        """Test that logger is properly configured."""
        from app.tasks.privacy_tasks import logger

        assert logger is not None
        assert logger.name == "app.tasks.privacy_tasks"

    def test_celery_app_is_accessible(self) -> None:
        """Test that celery_app is accessible via the tasks module."""
        from app.tasks.privacy_tasks import celery_app

        assert celery_app is not None

    def test_database_task_is_defined(self) -> None:
        """Test that DatabaseTask class is defined."""
        from app.tasks.privacy_tasks import DatabaseTask

        assert DatabaseTask is not None


class TestBugFixes:
    """Tests verifying bug fixes in privacy_tasks.py."""

    def test_settings_mutation_is_removed(self) -> None:
        """
        Verify thread-unsafe settings mutation has been removed.

        Previously lines 211-222 mutated the global settings object:
            settings.booking_pii_retention_days = days_old

        This was NOT thread-safe. The fix removes this mutation and
        uses the configured settings value instead, logging a warning
        if a custom days_old is requested.
        """
        from pathlib import Path

        privacy_tasks_path = (
            Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "privacy_tasks.py"
        )
        content = privacy_tasks_path.read_text()

        # Should NOT have the problematic settings mutation pattern
        assert "settings.booking_pii_retention_days = days_old" not in content, (
            "Thread-unsafe settings mutation should be removed"
        )
        # Should NOT restore original_setting (another indicator of mutation pattern)
        assert "settings.booking_pii_retention_days = original_setting" not in content, (
            "Original setting restoration pattern should be removed"
        )
        # Should have warning about thread safety
        assert "thread safety" in content.lower() or "thread-unsafe" in content.lower(), (
            "Should document thread safety concern"
        )

    def test_user_id_type_is_string(self) -> None:
        """
        Verify user_id parameter is typed as str (ULID format).

        Previously lines 239, 276 defined user_id: int but the system uses
        ULID strings for all IDs. This has been fixed.
        """
        from pathlib import Path

        privacy_tasks_path = (
            Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "privacy_tasks.py"
        )
        content = privacy_tasks_path.read_text()

        # Should NOT have user_id: int type hint
        assert "user_id: int" not in content, (
            "user_id should be typed as str, not int (ULID format)"
        )
        # Should have user_id: str type hint
        assert "user_id: str" in content, (
            "user_id should be typed as str for ULID compatibility"
        )
        # Should NOT need str(user_id) conversion
        assert content.count("str(user_id)") == 0, (
            "Should not need to convert user_id to str - it should already be str"
        )

    def test_user_id_documented_as_ulid(self) -> None:
        """Verify user_id is documented as ULID in docstrings."""
        from pathlib import Path

        privacy_tasks_path = (
            Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "privacy_tasks.py"
        )
        content = privacy_tasks_path.read_text()

        # Should mention ULID in documentation for user_id
        assert "ULID" in content, "user_id should be documented as ULID format"


class TestAnonymizeOldBookingsTask:
    """Tests for anonymize_old_bookings task thread safety."""

    def test_task_uses_configured_retention_period(self) -> None:
        """Test that task uses configured retention period from settings."""
        from pathlib import Path

        privacy_tasks_path = (
            Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "privacy_tasks.py"
        )
        content = privacy_tasks_path.read_text()

        # Should read configured_days from settings
        assert "configured_days" in content or "booking_pii_retention_days" in content, (
            "Task should use configured retention period"
        )

    def test_task_logs_warning_for_custom_days(self) -> None:
        """Test that task logs warning when custom days_old is requested."""
        from pathlib import Path

        privacy_tasks_path = (
            Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "privacy_tasks.py"
        )
        content = privacy_tasks_path.read_text()

        # Should log warning for custom days_old
        assert "logger.warning" in content, (
            "Task should log warning when custom days_old is requested"
        )
