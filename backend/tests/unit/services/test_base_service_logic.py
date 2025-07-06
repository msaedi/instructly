# backend/tests/unit/services/test_base_service_logic.py
"""
Unit tests for BaseService business logic.

These tests isolate the business logic from database and external dependencies
using mocks to ensure we're testing only the service logic.

FIXED: Updated to match actual BaseService implementation
"""

import time
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.base import BaseService, ServiceException


class TestBaseServiceInitialization:
    """Test BaseService initialization and properties."""

    def test_initialization_with_db_only(self):
        """Test basic initialization with just database."""
        mock_db = Mock(spec=Session)

        service = BaseService(mock_db)

        assert service.db == mock_db
        assert service.cache is None
        assert service.logger is not None
        # Note: _metrics doesn't exist at instance level, it's class-level

    def test_initialization_with_cache(self):
        """Test initialization with cache service."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock()

        service = BaseService(mock_db, mock_cache)

        assert service.db == mock_db
        assert service.cache == mock_cache
        assert service.logger is not None

    def test_logger_uses_class_name(self):
        """Test logger is named after the service class."""
        mock_db = Mock(spec=Session)

        # Create a custom service class
        class CustomService(BaseService):
            pass

        service = CustomService(mock_db)

        # Logger should use class name
        assert service.logger.name == "CustomService"


class TestTransactionManagement:
    """Test transaction management logic."""

    def test_transaction_context_success(self):
        """Test successful transaction context."""
        mock_db = Mock(spec=Session)
        mock_db.commit = Mock()
        mock_db.rollback = Mock()

        service = BaseService(mock_db)

        # Use transaction context
        with service.transaction() as session:
            assert session == mock_db

        # Verify commit was called
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    def test_transaction_context_with_sqlalchemy_error(self):
        """Test transaction rollback on SQLAlchemy error."""
        mock_db = Mock(spec=Session)
        mock_db.commit = Mock()
        mock_db.rollback = Mock()

        service = BaseService(mock_db)

        # Force SQLAlchemy error
        with pytest.raises(ServiceException) as exc_info:
            with service.transaction():
                raise SQLAlchemyError("Database connection lost")

        # Verify rollback was called
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
        assert "Database operation failed" in str(exc_info.value)

    def test_transaction_context_with_generic_error(self):
        """Test transaction rollback on generic error."""
        mock_db = Mock(spec=Session)
        mock_db.commit = Mock()
        mock_db.rollback = Mock()

        service = BaseService(mock_db)

        # Force generic error
        with pytest.raises(ValueError) as exc_info:
            with service.transaction():
                raise ValueError("Business logic error")

        # Verify rollback was called
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()
        assert "Business logic error" in str(exc_info.value)

    def test_with_transaction_decorator(self):
        """Test with_transaction decorator wrapping."""
        mock_db = Mock(spec=Session)
        mock_db.commit = Mock()
        mock_db.rollback = Mock()

        service = BaseService(mock_db)

        # Create a function to decorate
        call_count = 0

        def test_function(self, value):
            nonlocal call_count
            call_count += 1
            return f"processed_{value}"

        # Apply decorator
        decorated = service.with_transaction(test_function)

        # Execute decorated function
        result = decorated(service, "test")

        # Verify function was called and transaction committed
        assert result == "processed_test"
        assert call_count == 1
        mock_db.commit.assert_called_once()


class TestCacheInvalidation:
    """Test cache invalidation logic."""

    def test_invalidate_single_cache_key(self):
        """Test invalidating a single cache key."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock()
        mock_cache.delete = Mock()

        service = BaseService(mock_db, mock_cache)

        # Invalidate single key
        service.invalidate_cache("user:123")

        mock_cache.delete.assert_called_once_with("user:123")

    def test_invalidate_multiple_cache_keys(self):
        """Test invalidating multiple cache keys."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock()
        mock_cache.delete = Mock()

        service = BaseService(mock_db, mock_cache)

        # Invalidate multiple keys
        service.invalidate_cache("user:123", "user:profile:123", "user:bookings:123")

        assert mock_cache.delete.call_count == 3
        mock_cache.delete.assert_any_call("user:123")
        mock_cache.delete.assert_any_call("user:profile:123")
        mock_cache.delete.assert_any_call("user:bookings:123")

    def test_invalidate_cache_with_error(self):
        """Test cache invalidation continues on error."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock()
        mock_cache.delete = Mock(side_effect=Exception("Redis connection error"))

        service = BaseService(mock_db, mock_cache)

        # Should not raise exception
        service.invalidate_cache("user:123")

        # Should have attempted deletion
        mock_cache.delete.assert_called_once_with("user:123")

    def test_invalidate_pattern(self):
        """Test pattern-based cache invalidation."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock()
        mock_cache.delete_pattern = Mock(return_value=10)

        service = BaseService(mock_db, mock_cache)

        # Invalidate pattern
        service.invalidate_pattern("bookings:user:123:*")

        mock_cache.delete_pattern.assert_called_once_with("bookings:user:123:*")

    def test_invalidate_pattern_with_error(self):
        """Test pattern invalidation handles errors."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock()
        mock_cache.delete_pattern = Mock(side_effect=Exception("Pattern error"))

        service = BaseService(mock_db, mock_cache)

        # Should not raise exception
        service.invalidate_pattern("user:*")

        mock_cache.delete_pattern.assert_called_once_with("user:*")

    def test_invalidation_without_cache(self):
        """Test invalidation methods work without cache service."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db, cache=None)

        # These should not raise exceptions
        service.invalidate_cache("user:123")
        service.invalidate_pattern("user:*")


class TestPerformanceMonitoring:
    """Test performance monitoring functionality."""

    def setup_method(self):
        """Reset metrics before each test."""
        # Clear all class-level metrics
        BaseService._class_metrics.clear()

    def test_record_metric_success(self):
        """Test recording successful operation metric."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Record successful operations
        service._record_metric("create_user", 0.125, success=True)
        service._record_metric("create_user", 0.175, success=True)

        metrics = service.get_metrics()

        assert "create_user" in metrics
        assert metrics["create_user"]["count"] == 2
        assert metrics["create_user"]["avg_time"] == 0.15
        assert metrics["create_user"]["success_rate"] == 1.0
        assert metrics["create_user"]["total_time"] == 0.3

    def test_record_metric_failure(self):
        """Test recording failed operation metric."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Record mixed success/failure
        service._record_metric("update_user", 0.1, success=True)
        service._record_metric("update_user", 0.2, success=False)
        service._record_metric("update_user", 0.15, success=True)

        metrics = service.get_metrics()

        assert metrics["update_user"]["count"] == 3
        assert metrics["update_user"]["avg_time"] == pytest.approx(0.15, rel=1e-9)
        assert metrics["update_user"]["success_rate"] == pytest.approx(0.667, rel=0.01)

    def test_slow_operation_logging(self):
        """Test slow operation warning (>1 second)."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Patch logger to check warning
        with patch.object(service.logger, "warning") as mock_warning:
            # Use measure_operation_context for timing
            with service.measure_operation_context("slow_query"):
                time.sleep(1.1)  # Sleep more than 1 second

            mock_warning.assert_called_once()
            args = mock_warning.call_args[0][0]
            assert "Slow operation detected" in args
            assert "slow_query took" in args

    def test_measure_operation_decorator(self):
        """Test measure_operation decorator."""
        mock_db = Mock(spec=Session)

        # Create a test service class
        class TestService(BaseService):
            @BaseService.measure_operation("process_data")
            def process_data(self, data):
                time.sleep(0.05)  # Simulate work
                return f"processed_{data}"

        service = TestService(mock_db)

        # Execute
        result = service.process_data("test")

        # Verify result and metrics
        assert result == "processed_test"

        metrics = service.get_metrics()
        assert "process_data" in metrics
        assert metrics["process_data"]["count"] == 1
        assert metrics["process_data"]["avg_time"] >= 0.05
        assert metrics["process_data"]["success_rate"] == 1.0

    def test_measure_operation_with_exception(self):
        """Test measure_operation with exception."""
        mock_db = Mock(spec=Session)

        # Create a test service class
        class TestService(BaseService):
            @BaseService.measure_operation("failing_op")
            def failing_operation(self):
                time.sleep(0.01)
                raise ValueError("Operation failed")

        service = TestService(mock_db)

        # Execute and expect exception
        with pytest.raises(ValueError):
            service.failing_operation()

        # Verify failure was recorded
        metrics = service.get_metrics()
        assert "failing_op" in metrics
        assert metrics["failing_op"]["count"] == 1
        assert metrics["failing_op"]["success_rate"] == 0.0

    def test_empty_metrics(self):
        """Test get_metrics with no recorded metrics."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        metrics = service.get_metrics()

        assert metrics == {}

    def test_reset_metrics(self):
        """Test resetting metrics."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Record some metrics
        service._record_metric("test_op", 0.1, success=True)

        # Verify metrics exist
        assert len(service.get_metrics()) > 0

        # Reset metrics
        service.reset_metrics()

        # Verify metrics are cleared
        assert service.get_metrics() == {}

    def test_measure_operation_context(self):
        """Test measure_operation_context context manager."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Use context manager
        with service.measure_operation_context("context_operation"):
            time.sleep(0.05)

        # Check metrics were recorded
        metrics = service.get_metrics()
        assert "context_operation" in metrics
        assert metrics["context_operation"]["count"] == 1
        assert metrics["context_operation"]["avg_time"] >= 0.05


class TestLogging:
    """Test logging functionality."""

    def test_log_operation(self):
        """Test operation logging."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Patch logger
        with patch.object(service.logger, "info") as mock_info:
            service.log_operation("create_booking", user_id=123, instructor_id=456, amount=100.0)

            mock_info.assert_called_once()
            args, kwargs = mock_info.call_args
            assert "Operation: create_booking" in args[0]

            # Check extra context
            extra = kwargs.get("extra", {})
            assert extra.get("operation") == "create_booking"
            assert extra.get("user_id") == 123
            assert extra.get("instructor_id") == 456
            assert extra.get("amount") == 100.0
