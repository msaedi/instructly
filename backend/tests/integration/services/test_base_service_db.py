# backend/tests/integration/services/test_base_service_db.py
"""
Integration tests for BaseService database operations.

These tests verify transaction handling, error recovery,
and integration with real database sessions.
"""

from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceException
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.service_catalog import ServiceCatalog
from app.models.user import User
from app.services.base import BaseService
from app.services.cache_service import CacheService


class TestBaseServiceTransactions:
    """Test transaction handling with real database."""

    def test_successful_transaction_commit(self, db: Session):
        """Test successful transaction commits changes."""
        service = BaseService(db)

        # Create a user within transaction
        with service.transaction():
            user = User(
                email="transaction_test@example.com",
                hashed_password="hashed",
                first_name="Transaction",
                last_name="Test",
                phone="+12125550000",
                zip_code="10001",
            )
            db.add(user)

        # Verify user was committed
        saved_user = db.query(User).filter(User.email == "transaction_test@example.com").first()
        assert saved_user is not None
        assert saved_user.first_name == "Transaction"
        assert saved_user.last_name == "Test"

    def test_transaction_rollback_on_error(self, db: Session):
        """Test transaction rollback on error."""
        service = BaseService(db)

        initial_count = db.query(User).count()

        # Try to create user but force error
        with pytest.raises(ServiceException):
            with service.transaction():
                user = User(
                    email="rollback_test@example.com",
                    hashed_password="hashed",
                    first_name="Rollback",
                    last_name="Test",
                    phone="+12125550000",
                    zip_code="10001",
                )
                db.add(user)
                # Force an error
                raise SQLAlchemyError("Simulated database error")

        # Verify rollback - user count unchanged
        final_count = db.query(User).count()
        assert final_count == initial_count

        # Verify user was not saved
        user = db.query(User).filter(User.email == "rollback_test@example.com").first()
        assert user is None

    def test_transaction_with_multiple_operations(self, db: Session, test_instructor: User, catalog_data: dict):
        """Test transaction with multiple database operations."""
        service = BaseService(db)

        with service.transaction():
            # Update an existing service instead of creating a new one
            existing_service = (
                db.query(Service)
                .filter(
                    Service.instructor_profile_id == test_instructor.instructor_profile.id, Service.is_active == True
                )
                .first()
            )

            if existing_service:
                # Update the existing service
                existing_service.hourly_rate = 100.0
                existing_service.description = "Testing transactions"
            else:
                # Only create if no service exists (shouldn't happen with fixtures)
                catalog_service = db.query(ServiceCatalog).first()
                if not catalog_service:
                    raise RuntimeError("No catalog services found")

                new_service = Service(
                    instructor_profile_id=test_instructor.instructor_profile.id,
                    service_catalog_id=catalog_service.id,
                    hourly_rate=100.0,
                    description="Testing transactions",
                    is_active=True,
                )
                db.add(new_service)

            # Update instructor profile
            test_instructor.instructor_profile.bio = "Updated in transaction"

        # Verify both operations completed
        saved_service = (
            db.query(Service)
            .filter(
                Service.instructor_profile_id == test_instructor.instructor_profile.id,
                Service.description == "Testing transactions",
            )
            .first()
        )
        assert saved_service is not None

        updated_profile = (
            db.query(InstructorProfile).filter(InstructorProfile.id == test_instructor.instructor_profile.id).first()
        )
        assert updated_profile.bio == "Updated in transaction"

    def test_transaction_decorator(self, db: Session):
        """Test with_transaction decorator functionality."""
        service = BaseService(db)

        # Can't use decorator syntax, so we'll test the wrapper manually
        def create_test_user(self):
            user = User(
                email="decorator_test@example.com",
                hashed_password="hashed",
                first_name="Decorator",
                last_name="Test",
                phone="+12125550000",
                zip_code="10001",
            )
            self.db.add(user)
            return user

        # Apply decorator
        wrapped_func = service.with_transaction(create_test_user)

        # Execute wrapped function
        wrapped_func(service)

        # Verify user was created and committed
        saved_user = db.query(User).filter(User.email == "decorator_test@example.com").first()
        assert saved_user is not None

    def test_nested_transaction_error_handling(self, db: Session):
        """Test nested transactions with error handling."""
        service = BaseService(db)

        initial_count = db.query(User).count()

        # Outer transaction should rollback if inner fails
        with pytest.raises(ServiceException):
            with service.transaction():
                # Add user in outer transaction
                user1 = User(
                    email="outer_transaction@example.com",
                    hashed_password="hashed",
                    first_name="Outer",
                    last_name="User",
                    phone="+12125550000",
                    zip_code="10001",
                )
                db.add(user1)

                # Inner transaction with error
                with service.transaction():
                    user2 = User(
                        email="inner_transaction@example.com",
                        hashed_password="hashed",
                        first_name="Inner",
                        last_name="User",
                        phone="+12125550000",
                        zip_code="10001",
                    )
                    db.add(user2)
                    raise SQLAlchemyError("Inner transaction error")

        # Verify complete rollback
        final_count = db.query(User).count()
        assert final_count == initial_count


class TestBaseServiceWithCache:
    """Test cache integration with real cache service."""

    @pytest.fixture
    def cache_service(self):
        """Create a mock cache service."""
        cache = Mock(spec=CacheService)
        cache.get = Mock(return_value=None)
        cache.set = Mock()
        cache.delete = Mock()
        cache.delete_pattern = Mock(return_value=5)
        return cache

    def test_cache_invalidation_single_key(self, db: Session, cache_service):
        """Test single cache key invalidation."""
        service = BaseService(db, cache_service)

        # Invalidate specific keys
        service.invalidate_cache("user:123", "user:profile:123")

        # Verify cache delete was called
        assert cache_service.delete.call_count == 2
        cache_service.delete.assert_any_call("user:123")
        cache_service.delete.assert_any_call("user:profile:123")

    def test_cache_invalidation_pattern(self, db: Session, cache_service):
        """Test pattern-based cache invalidation."""
        service = BaseService(db, cache_service)

        # Invalidate pattern
        service.invalidate_pattern("bookings:user:123:*")

        # Verify pattern delete was called
        cache_service.delete_pattern.assert_called_once_with("bookings:user:123:*")

    def test_cache_invalidation_error_handling(self, db: Session, cache_service):
        """Test cache invalidation continues on errors."""
        # Make cache delete raise exception
        cache_service.delete.side_effect = Exception("Cache error")

        service = BaseService(db, cache_service)

        # Should not raise exception
        service.invalidate_cache("user:123")

        # Should have attempted delete
        cache_service.delete.assert_called_once_with("user:123")

    def test_no_cache_service(self, db: Session):
        """Test service works without cache."""
        service = BaseService(db, cache=None)

        # These should not raise errors
        service.invalidate_cache("user:123")
        service.invalidate_pattern("user:*")

        # Service should work normally
        assert service.cache is None


class TestBaseServicePerformanceMonitoring:
    """Test performance monitoring with real operations."""

    def test_metric_recording(self, db: Session):
        """Test performance metric recording."""
        service = BaseService(db)

        # Use unique operation names to avoid conflicts
        create_op = "test_create_user_metric"
        update_op = "test_update_user_metric"

        # Record some metrics
        service._record_metric(create_op, 0.150, success=True)
        service._record_metric(create_op, 0.200, success=True)
        service._record_metric(create_op, 0.500, success=False)
        service._record_metric(update_op, 0.100, success=True)

        # Get metrics
        metrics = service.get_metrics()

        # Verify create_user metrics
        assert metrics[create_op]["count"] == 3
        assert metrics[create_op]["avg_time"] == pytest.approx(0.283, rel=0.01)
        assert metrics[create_op]["success_rate"] == pytest.approx(0.667, rel=0.01)
        assert metrics[create_op]["total_time"] == 0.850

        # Verify update_user metrics
        assert metrics[update_op]["count"] == 1
        assert metrics[update_op]["avg_time"] == 0.100
        assert metrics[update_op]["success_rate"] == 1.0

    def test_slow_operation_warning(self, db: Session, caplog):
        """Test slow operation warning logging."""
        service = BaseService(db)

        # Use unique operation name
        slow_op_name = "test_slow_query_unique"

        # Use the context manager with an actual slow operation
        with caplog.at_level("WARNING"):
            with service.measure_operation_context(slow_op_name):
                import time

                time.sleep(1.1)  # Sleep for more than 1 second to trigger warning

        # Verify warning was logged with correct format
        warning_found = any(
            f"Slow operation detected: {slow_op_name} took" in record.message
            for record in caplog.records
            if record.levelname == "WARNING"
        )

        assert (
            warning_found
        ), f"Expected slow operation warning not found. Captured logs: {[(r.levelname, r.message) for r in caplog.records]}"

    def test_measure_operation_context_usage(self, db: Session):
        """Test measure_operation_context context manager."""
        service = BaseService(db)

        # Use a unique operation name to avoid conflicts with other tests
        unique_op_name = "test_context_operation_unique"

        # Use context manager for measurement
        with service.measure_operation_context(unique_op_name):
            import time

            time.sleep(0.05)

        # Verify metrics were recorded
        metrics = service.get_metrics()
        assert unique_op_name in metrics
        assert metrics[unique_op_name]["count"] == 1
        assert metrics[unique_op_name]["avg_time"] >= 0.05
        assert metrics[unique_op_name]["success_rate"] == 1.0

    def test_measure_operation_decorator(self, db: Session):
        """Test measure_operation decorator pattern."""
        service = BaseService(db)

        # Use unique operation name to avoid conflicts
        unique_decorator_op = "test_decorator_operation_unique"

        # Create a test method and bind it to the service instance
        @BaseService.measure_operation(unique_decorator_op)
        def slow_operation(self):
            import time

            time.sleep(0.1)
            return "result"

        # Bind the method to the service instance
        bound_method = slow_operation.__get__(service, BaseService)

        # Execute
        result = bound_method()

        # Verify result and metrics
        assert result == "result"
        metrics = service.get_metrics()
        assert unique_decorator_op in metrics
        assert metrics[unique_decorator_op]["count"] == 1
        assert metrics[unique_decorator_op]["avg_time"] >= 0.1


class TestBaseServiceValidation:
    """Test validation functionality has been removed from BaseService."""

    def test_validation_removed(self, db: Session):
        """Verify that validate_input method no longer exists."""
        service = BaseService(db)

        # Confirm the method doesn't exist
        assert not hasattr(service, "validate_input")

    def test_logging_operations_still_works(self, db: Session, caplog):
        """Test that operation logging still functions."""
        service = BaseService(db)

        # Log operation
        with caplog.at_level("INFO"):
            service.log_operation("create_booking", user_id=123, instructor_id=456, status="confirmed")

        # Verify log entry exists
        log_found = False
        for record in caplog.records:
            if "Operation: create_booking" in record.message:
                log_found = True
                break

        assert log_found
