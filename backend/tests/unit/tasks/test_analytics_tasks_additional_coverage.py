"""
Additional tests for analytics tasks - targeting remaining CI coverage gaps.

Focus on edge cases and error paths not covered by existing tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.tasks.analytics as analytics


def _set_task_request(task, task_id: str = "task-analytics-123", retries: int = 0) -> None:
    """Set up task request attributes."""
    task.request.id = task_id
    task.request.retries = retries


@contextmanager
def _db_session_ctx(db):
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _patch_get_db(monkeypatch, db) -> None:
    """Patch get_db to return our test db session."""
    monkeypatch.setattr(analytics, "get_db_session", lambda: _db_session_ctx(db))


class TestTypedTaskDecorator:
    """Tests for the typed_task helper decorator."""

    def test_typed_task_returns_callable(self) -> None:
        """Test that typed_task returns a callable that can be used as a decorator."""
        # The typed_task function is a helper to provide type hints for Celery tasks
        # It should return a callable
        assert callable(analytics.typed_task)

    def test_task_has_delay_method(self) -> None:
        """Test that tasks created with typed_task have delay method."""
        assert hasattr(analytics.calculate_analytics, "delay")
        assert callable(analytics.calculate_analytics.delay)

    def test_task_has_apply_async_method(self) -> None:
        """Test that tasks created with typed_task have apply_async method."""
        assert hasattr(analytics.calculate_analytics, "apply_async")
        assert callable(analytics.calculate_analytics.apply_async)


class TestCalculateAnalyticsEdgeCases:
    """Edge case tests for calculate_analytics task."""

    def test_default_days_back_is_90(self, db, monkeypatch) -> None:
        """Test that default days_back is 90."""
        _set_task_request(analytics.calculate_analytics)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        calculator.calculate_all_analytics.return_value = 0
        calculator.generate_report.return_value = {}
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        analytics.calculate_analytics.run()  # No days_back argument

        calculator.calculate_all_analytics.assert_called_once_with(days_back=90)

    def test_db_session_closes_on_success(self, monkeypatch) -> None:
        """Test that database session is closed after successful completion."""
        _set_task_request(analytics.calculate_analytics)

        mock_db = MagicMock()
        mock_db.close = MagicMock()
        monkeypatch.setattr(analytics, "get_db_session", lambda: _db_session_ctx(mock_db))

        calculator = MagicMock()
        calculator.calculate_all_analytics.return_value = 0
        calculator.generate_report.return_value = {}
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        analytics.calculate_analytics.run()

        mock_db.close.assert_called_once()

    def test_db_session_closes_on_error(self, monkeypatch) -> None:
        """Test that database session is closed even when an error occurs."""
        _set_task_request(analytics.calculate_analytics)

        mock_db = MagicMock()
        mock_db.close = MagicMock()
        monkeypatch.setattr(analytics, "get_db_session", lambda: _db_session_ctx(mock_db))

        calculator = MagicMock()
        calculator.calculate_all_analytics.side_effect = RuntimeError("Test error")
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        with patch.object(analytics.calculate_analytics, "retry", side_effect=RuntimeError("retry")):
            with pytest.raises(RuntimeError, match="retry"):
                analytics.calculate_analytics.run()

        mock_db.close.assert_called_once()

    def test_result_includes_task_id(self, db, monkeypatch) -> None:
        """Test that result includes the task ID."""
        task_id = "unique-task-id-123"
        _set_task_request(analytics.calculate_analytics, task_id=task_id)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        calculator.calculate_all_analytics.return_value = 5
        calculator.generate_report.return_value = {}
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        result = analytics.calculate_analytics.run()

        assert result["task_id"] == task_id

    def test_result_includes_execution_time(self, db, monkeypatch) -> None:
        """Test that result includes execution time."""
        _set_task_request(analytics.calculate_analytics)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        calculator.calculate_all_analytics.return_value = 0
        calculator.generate_report.return_value = {}
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        result = analytics.calculate_analytics.run()

        assert "execution_time" in result
        assert isinstance(result["execution_time"], float)
        assert result["execution_time"] >= 0

    def test_result_includes_completed_at_timestamp(self, db, monkeypatch) -> None:
        """Test that result includes completed_at ISO timestamp."""
        _set_task_request(analytics.calculate_analytics)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        calculator.calculate_all_analytics.return_value = 0
        calculator.generate_report.return_value = {}
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        result = analytics.calculate_analytics.run()

        assert "completed_at" in result
        # Should be a valid ISO format timestamp
        datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00"))


class TestGenerateDailyReportEdgeCases:
    """Edge case tests for generate_daily_report task."""

    def test_db_session_closes_on_success(self, monkeypatch) -> None:
        """Test that database session is closed after successful completion."""
        _set_task_request(analytics.generate_daily_report)

        mock_db = MagicMock()
        mock_db.close = MagicMock()
        monkeypatch.setattr(analytics, "get_db_session", lambda: _db_session_ctx(mock_db))

        calculator = MagicMock()
        calculator.generate_report.return_value = {}
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        analytics.generate_daily_report.run()

        mock_db.close.assert_called_once()

    def test_db_session_closes_on_error(self, monkeypatch) -> None:
        """Test that database session is closed even when an error occurs."""
        _set_task_request(analytics.generate_daily_report)

        mock_db = MagicMock()
        mock_db.close = MagicMock()
        monkeypatch.setattr(analytics, "get_db_session", lambda: _db_session_ctx(mock_db))

        calculator = MagicMock()
        calculator.generate_report.side_effect = RuntimeError("Test error")
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        with patch.object(analytics.generate_daily_report, "retry", side_effect=RuntimeError("retry")):
            with pytest.raises(RuntimeError, match="retry"):
                analytics.generate_daily_report.run()

        mock_db.close.assert_called_once()

    def test_result_includes_generated_at_timestamp(self, db, monkeypatch) -> None:
        """Test that result includes generated_at ISO timestamp."""
        _set_task_request(analytics.generate_daily_report)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        calculator.generate_report.return_value = {"items": []}
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        result = analytics.generate_daily_report.run()

        assert "generated_at" in result
        # Should be a valid ISO format timestamp
        datetime.fromisoformat(result["generated_at"].replace("Z", "+00:00"))


class TestUpdateServiceMetricsEdgeCases:
    """Edge case tests for update_service_metrics task."""

    def test_handles_exception_and_reraises(self, db, monkeypatch) -> None:
        """Test that exceptions are logged and re-raised."""
        _set_task_request(analytics.update_service_metrics)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        catalog_repo = MagicMock()
        catalog_repo.get_by_id.side_effect = RuntimeError("Database connection error")

        with patch(
            "app.repositories.factory.RepositoryFactory.create_service_catalog_repository",
            return_value=catalog_repo,
        ):
            with pytest.raises(RuntimeError, match="Database connection error"):
                analytics.update_service_metrics.run("test-service")

    def test_db_session_closes_on_success(self, monkeypatch) -> None:
        """Test that database session is closed after successful completion."""
        _set_task_request(analytics.update_service_metrics)

        mock_db = MagicMock()
        mock_db.close = MagicMock()
        monkeypatch.setattr(analytics, "get_db_session", lambda: _db_session_ctx(mock_db))

        calculator = MagicMock()
        calculator.calculate_booking_stats.return_value = {"count_7d": 0, "count_30d": 0}
        calculator.calculate_instructor_stats.return_value = {
            "active_instructors": 0,
            "total_weekly_hours": 0,
        }
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        catalog_repo = MagicMock()
        catalog_repo.get_by_id.return_value = SimpleNamespace(id="svc-1")
        analytics_repo = MagicMock()
        analytics_repo.get_or_create.return_value = MagicMock()
        analytics_repo.update.return_value = SimpleNamespace(id="svc-1")

        with patch(
            "app.repositories.factory.RepositoryFactory.create_service_catalog_repository",
            return_value=catalog_repo,
        ), patch(
            "app.repositories.factory.RepositoryFactory.create_service_analytics_repository",
            return_value=analytics_repo,
        ):
            analytics.update_service_metrics.run("svc-1")

        mock_db.close.assert_called_once()

    def test_db_session_closes_on_error(self, monkeypatch) -> None:
        """Test that database session is closed even when an error occurs."""
        _set_task_request(analytics.update_service_metrics)

        mock_db = MagicMock()
        mock_db.close = MagicMock()
        monkeypatch.setattr(analytics, "get_db_session", lambda: _db_session_ctx(mock_db))

        calculator = MagicMock()
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        catalog_repo = MagicMock()
        catalog_repo.get_by_id.side_effect = RuntimeError("Test error")

        with patch(
            "app.repositories.factory.RepositoryFactory.create_service_catalog_repository",
            return_value=catalog_repo,
        ):
            with pytest.raises(RuntimeError, match="Test error"):
                analytics.update_service_metrics.run("test-service")

        mock_db.close.assert_called_once()

    def test_result_includes_updated_at_timestamp(self, db, monkeypatch) -> None:
        """Test that result includes updated_at ISO timestamp."""
        _set_task_request(analytics.update_service_metrics)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        calculator.calculate_booking_stats.return_value = {"count_7d": 1, "count_30d": 5}
        calculator.calculate_instructor_stats.return_value = {
            "active_instructors": 2,
            "total_weekly_hours": 10,
        }
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        catalog_repo = MagicMock()
        catalog_repo.get_by_id.return_value = SimpleNamespace(id="svc-1")
        analytics_repo = MagicMock()
        analytics_repo.get_or_create.return_value = MagicMock()
        analytics_repo.update.return_value = SimpleNamespace(id="svc-1")

        with patch(
            "app.repositories.factory.RepositoryFactory.create_service_catalog_repository",
            return_value=catalog_repo,
        ), patch(
            "app.repositories.factory.RepositoryFactory.create_service_analytics_repository",
            return_value=analytics_repo,
        ):
            result = analytics.update_service_metrics.run("svc-1")

        assert "updated_at" in result
        # Should be a valid ISO format timestamp
        datetime.fromisoformat(result["updated_at"].replace("Z", "+00:00"))

    def test_handles_update_returning_none(self, db, monkeypatch) -> None:
        """Test handling when update returns None."""
        _set_task_request(analytics.update_service_metrics)
        _patch_get_db(monkeypatch, db)

        calculator = MagicMock()
        calculator.calculate_booking_stats.return_value = {"count_7d": 0, "count_30d": 0}
        calculator.calculate_instructor_stats.return_value = {
            "active_instructors": 0,
            "total_weekly_hours": 0,
        }
        monkeypatch.setattr(analytics, "AnalyticsCalculator", lambda _db: calculator)

        catalog_repo = MagicMock()
        catalog_repo.get_by_id.return_value = SimpleNamespace(id="svc-1")
        analytics_repo = MagicMock()
        analytics_repo.get_or_create.return_value = MagicMock()
        analytics_repo.update.return_value = None  # Update returns None

        with patch(
            "app.repositories.factory.RepositoryFactory.create_service_catalog_repository",
            return_value=catalog_repo,
        ), patch(
            "app.repositories.factory.RepositoryFactory.create_service_analytics_repository",
            return_value=analytics_repo,
        ):
            result = analytics.update_service_metrics.run("svc-1")

        assert result["status"] == "success"
        assert result["updated"] is False  # Should be False when update returns None
