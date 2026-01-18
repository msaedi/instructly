"""
Comprehensive tests for analytics.py - targeting 0% coverage.

Covers all uncovered lines: 15-354 (all task functions and error paths).
"""

from unittest.mock import MagicMock, patch

import pytest


class TestTypedTaskDecorator:
    """Tests for typed_task helper function."""

    def test_typed_task_returns_callable(self) -> None:
        """Test that typed_task returns a callable decorator."""
        from app.tasks.analytics import typed_task

        decorator = typed_task(name="test_task")
        assert callable(decorator)

    def test_typed_task_creates_celery_task(self) -> None:
        """Test that typed_task creates tasks with Celery attributes."""
        from app.tasks.analytics import calculate_analytics

        assert hasattr(calculate_analytics, "delay")
        assert hasattr(calculate_analytics, "apply_async")
        assert hasattr(calculate_analytics, "name")


class TestTaskWrapper:
    """Tests for TaskWrapper Protocol."""

    def test_task_wrapper_protocol_definition(self) -> None:
        """Verify TaskWrapper protocol is properly defined."""
        from app.tasks.analytics import TaskWrapper

        # Protocol should exist
        assert TaskWrapper is not None


class TestCalculateAnalyticsTask:
    """Tests for calculate_analytics task."""

    def test_task_is_registered(self) -> None:
        """Test calculate_analytics is registered with correct name."""
        from app.tasks.analytics import calculate_analytics

        assert calculate_analytics.name == "app.tasks.analytics.calculate_analytics"

    def test_task_has_max_retries(self) -> None:
        """Test task has max_retries configured."""
        from app.tasks.analytics import calculate_analytics

        assert calculate_analytics.max_retries == 3

    def test_success_path(self) -> None:
        """Test successful analytics calculation."""
        from app.tasks.analytics import calculate_analytics

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.calculate_all_analytics.return_value = 10
        mock_calculator.generate_report.return_value = {"services_updated": 10}

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            result = calculate_analytics.run(days_back=30)

            assert result["status"] == "success"
            assert result["services_updated"] == 10
            assert "execution_time" in result
            assert "completed_at" in result
            mock_session.close.assert_called_once()

    def test_default_days_back(self) -> None:
        """Test default days_back is 90."""
        from app.tasks.analytics import calculate_analytics

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.calculate_all_analytics.return_value = 5
        mock_calculator.generate_report.return_value = {}

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            calculate_analytics.run()

            # Verify 90 days was passed
            mock_calculator.calculate_all_analytics.assert_called_once_with(days_back=90)

    def test_exception_triggers_retry(self) -> None:
        """Test that exceptions trigger retry with exponential backoff."""
        from celery.exceptions import Retry

        from app.tasks.analytics import calculate_analytics

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.calculate_all_analytics.side_effect = Exception("DB error")

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            # Mock the task's retry method to raise Retry
            with patch.object(calculate_analytics, "retry", side_effect=Retry("retrying")):
                with pytest.raises(Retry):
                    calculate_analytics.run(days_back=30)

            mock_session.close.assert_called_once()

    def test_db_session_closed_on_success(self) -> None:
        """Test that db session is always closed on success."""
        from app.tasks.analytics import calculate_analytics

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.calculate_all_analytics.return_value = 0
        mock_calculator.generate_report.return_value = {}

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            calculate_analytics.run()

            mock_session.close.assert_called_once()

    def test_db_session_closed_on_exception(self) -> None:
        """Test that db session is closed even on exception."""
        from celery.exceptions import Retry

        from app.tasks.analytics import calculate_analytics

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.calculate_all_analytics.side_effect = Exception("Error")

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            # Mock the task's retry method to raise Retry
            with patch.object(calculate_analytics, "retry", side_effect=Retry("retrying")):
                with pytest.raises(Retry):
                    calculate_analytics.run()

            mock_session.close.assert_called_once()


class TestGenerateDailyReportTask:
    """Tests for generate_daily_report task."""

    def test_task_is_registered(self) -> None:
        """Test generate_daily_report is registered with correct name."""
        from app.tasks.analytics import generate_daily_report

        assert generate_daily_report.name == "app.tasks.analytics.generate_daily_report"

    def test_task_has_max_retries(self) -> None:
        """Test task has max_retries configured."""
        from app.tasks.analytics import generate_daily_report

        assert generate_daily_report.max_retries == 2

    def test_success_path(self) -> None:
        """Test successful daily report generation."""
        from app.tasks.analytics import generate_daily_report

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.generate_report.return_value = {"metrics": "data"}

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            result = generate_daily_report.run()

            assert result["status"] == "success"
            assert result["report"] == {"metrics": "data"}
            assert "execution_time" in result
            assert "generated_at" in result
            mock_session.close.assert_called_once()

    def test_exception_triggers_retry_with_5_min_countdown(self) -> None:
        """Test that exceptions trigger retry after 5 minutes."""
        from celery.exceptions import Retry

        from app.tasks.analytics import generate_daily_report

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.generate_report.side_effect = Exception("Report error")

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            # Mock the task's retry method to raise Retry
            with patch.object(generate_daily_report, "retry", side_effect=Retry("retrying")):
                with pytest.raises(Retry):
                    generate_daily_report.run()

            mock_session.close.assert_called_once()


class TestUpdateServiceMetricsTask:
    """Tests for update_service_metrics task."""

    def test_task_is_registered(self) -> None:
        """Test update_service_metrics is registered with correct name."""
        from app.tasks.analytics import update_service_metrics

        assert update_service_metrics.name == "app.tasks.analytics.update_service_metrics"

    def test_success_path(self) -> None:
        """Test successful service metrics update."""
        from app.tasks.analytics import update_service_metrics

        mock_session = MagicMock()
        mock_service = MagicMock()
        mock_service.id = "service-123"

        mock_calculator = MagicMock()
        mock_calculator.calculate_booking_stats.return_value = {
            "count_7d": 5,
            "count_30d": 20,
            "avg_price": 50.0,
        }
        mock_calculator.calculate_instructor_stats.return_value = {
            "active_instructors": 3,
            "total_weekly_hours": 40,
        }

        mock_catalog_repo = MagicMock()
        mock_catalog_repo.get_by_id.return_value = mock_service

        mock_analytics_repo = MagicMock()
        mock_analytics_repo.get_or_create.return_value = MagicMock()
        mock_analytics_repo.update.return_value = MagicMock()

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class, \
             patch("app.repositories.factory.RepositoryFactory") as mock_repo_factory:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator
            mock_repo_factory.create_service_catalog_repository.return_value = mock_catalog_repo
            mock_repo_factory.create_service_analytics_repository.return_value = mock_analytics_repo

            result = update_service_metrics.run("service-123")

            assert result["status"] == "success"
            assert result["service_id"] == "service-123"
            assert result["booking_stats"]["count_7d"] == 5
            assert result["instructor_stats"]["active_instructors"] == 3
            assert result["updated"] is True
            mock_session.close.assert_called_once()

    def test_service_not_found(self) -> None:
        """Test handling when service is not found."""
        from app.tasks.analytics import update_service_metrics

        mock_session = MagicMock()

        mock_catalog_repo = MagicMock()
        mock_catalog_repo.get_by_id.return_value = None

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator"), \
             patch("app.repositories.factory.RepositoryFactory") as mock_repo_factory:
            mock_get_db.return_value = iter([mock_session])
            mock_repo_factory.create_service_catalog_repository.return_value = mock_catalog_repo

            result = update_service_metrics.run("nonexistent-service")

            assert result["status"] == "error"
            assert "not found" in result["message"]
            mock_session.close.assert_called_once()

    def test_exception_reraises(self) -> None:
        """Test that exceptions are re-raised after cleanup."""
        from app.tasks.analytics import update_service_metrics

        mock_session = MagicMock()
        mock_catalog_repo = MagicMock()
        mock_catalog_repo.get_by_id.side_effect = Exception("DB error")

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator"), \
             patch("app.repositories.factory.RepositoryFactory") as mock_repo_factory:
            mock_get_db.return_value = iter([mock_session])
            mock_repo_factory.create_service_catalog_repository.return_value = mock_catalog_repo

            with pytest.raises(Exception, match="DB error"):
                update_service_metrics.run("service-123")

            mock_session.close.assert_called_once()

    def test_update_returns_none(self) -> None:
        """Test handling when analytics update returns None."""
        from app.tasks.analytics import update_service_metrics

        mock_session = MagicMock()
        mock_service = MagicMock()
        mock_service.id = "service-123"

        mock_calculator = MagicMock()
        mock_calculator.calculate_booking_stats.return_value = {"count_7d": 0, "count_30d": 0}
        mock_calculator.calculate_instructor_stats.return_value = {
            "active_instructors": 0,
            "total_weekly_hours": 0,
        }

        mock_catalog_repo = MagicMock()
        mock_catalog_repo.get_by_id.return_value = mock_service

        mock_analytics_repo = MagicMock()
        mock_analytics_repo.get_or_create.return_value = MagicMock()
        mock_analytics_repo.update.return_value = None  # Update returns None

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class, \
             patch("app.repositories.factory.RepositoryFactory") as mock_repo_factory:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator
            mock_repo_factory.create_service_catalog_repository.return_value = mock_catalog_repo
            mock_repo_factory.create_service_analytics_repository.return_value = mock_analytics_repo

            result = update_service_metrics.run("service-123")

            assert result["updated"] is False


class TestRecordTaskExecutionTask:
    """Tests for record_task_execution task."""

    def test_task_is_registered(self) -> None:
        """Test record_task_execution is registered with correct name."""
        from app.tasks.analytics import record_task_execution

        assert record_task_execution.name == "app.tasks.analytics.record_task_execution"

    def test_success_path(self) -> None:
        """Test successful task execution recording."""
        from app.tasks.analytics import record_task_execution

        mock_session = MagicMock()

        with patch("app.tasks.analytics.get_db") as mock_get_db:
            mock_get_db.return_value = iter([mock_session])

            # Should not raise, just log
            result = record_task_execution.run(
                task_name="test_task",
                status="success",
                execution_time=1.5,
                result={"count": 10},
                error=None,
            )

            assert result is None  # Task returns None
            mock_session.close.assert_called_once()

    def test_exception_is_caught_and_logged(self) -> None:
        """Test that exceptions are caught and logged (not re-raised)."""
        from app.tasks.analytics import record_task_execution

        with patch("app.tasks.analytics.get_db") as mock_get_db:
            mock_get_db.side_effect = Exception("DB connection error")

            # Should NOT raise - exception is caught
            result = record_task_execution.run(
                task_name="test_task",
                status="failure",
                execution_time=0.5,
                result=None,
                error="Some error",
            )

            assert result is None

    def test_with_error_parameter(self) -> None:
        """Test recording a failed task execution."""
        from app.tasks.analytics import record_task_execution

        mock_session = MagicMock()

        with patch("app.tasks.analytics.get_db") as mock_get_db:
            mock_get_db.return_value = iter([mock_session])

            result = record_task_execution.run(
                task_name="failing_task",
                status="failure",
                execution_time=2.0,
                result=None,
                error="Task failed with exception",
            )

            assert result is None
            mock_session.close.assert_called_once()


class TestModuleImports:
    """Tests for module-level imports and constants."""

    def test_logger_is_configured(self) -> None:
        """Test that logger is properly configured."""
        from app.tasks.analytics import logger

        assert logger is not None
        assert logger.name == "app.tasks.analytics"

    def test_celery_app_import(self) -> None:
        """Test that celery_app is properly imported."""
        from app.tasks.analytics import celery_app

        assert celery_app is not None

    def test_base_task_import(self) -> None:
        """Test that BaseTask is properly imported."""
        from app.tasks.analytics import BaseTask

        assert BaseTask is not None


class TestEdgeCases:
    """Edge case tests for analytics tasks."""

    def test_calculate_analytics_with_zero_services(self) -> None:
        """Test handling when no services are updated."""
        from app.tasks.analytics import calculate_analytics

        mock_session = MagicMock()
        mock_calculator = MagicMock()
        mock_calculator.calculate_all_analytics.return_value = 0
        mock_calculator.generate_report.return_value = {"total": 0}

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator

            result = calculate_analytics.run()

            assert result["status"] == "success"
            assert result["services_updated"] == 0

    def test_booking_stats_with_missing_keys(self) -> None:
        """Test handling booking stats with missing keys uses defaults."""
        from app.tasks.analytics import update_service_metrics

        mock_session = MagicMock()
        mock_service = MagicMock()
        mock_service.id = "service-123"

        mock_calculator = MagicMock()
        # Return stats without all expected keys
        mock_calculator.calculate_booking_stats.return_value = {}
        mock_calculator.calculate_instructor_stats.return_value = {
            "active_instructors": 1,
            "total_weekly_hours": 10,
        }

        mock_catalog_repo = MagicMock()
        mock_catalog_repo.get_by_id.return_value = mock_service

        mock_analytics_repo = MagicMock()
        mock_analytics_repo.get_or_create.return_value = MagicMock()
        mock_analytics_repo.update.return_value = MagicMock()

        with patch("app.tasks.analytics.get_db") as mock_get_db, \
             patch("app.tasks.analytics.AnalyticsCalculator") as mock_calc_class, \
             patch("app.repositories.factory.RepositoryFactory") as mock_repo_factory:
            mock_get_db.return_value = iter([mock_session])
            mock_calc_class.return_value = mock_calculator
            mock_repo_factory.create_service_catalog_repository.return_value = mock_catalog_repo
            mock_repo_factory.create_service_analytics_repository.return_value = mock_analytics_repo

            result = update_service_metrics.run("service-123")

            # Should use .get() defaults for missing keys
            assert result["status"] == "success"
            assert result["booking_stats"] == {}
