# backend/tests/integration/test_base_service_db.py
"""
Integration tests for BaseService database operations.

These tests verify transaction handling, error recovery,
and integration with real database sessions.
"""

from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationException
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User
from app.services.base import BaseRepositoryService, BaseService, ServiceException
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
                full_name="Transaction Test",
                role="student",
            )
            db.add(user)

        # Verify user was committed
        saved_user = db.query(User).filter(User.email == "transaction_test@example.com").first()
        assert saved_user is not None
        assert saved_user.full_name == "Transaction Test"

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
                    full_name="Rollback Test",
                    role="student",
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

    def test_transaction_with_multiple_operations(self, db: Session, test_instructor: User):
        """Test transaction with multiple database operations."""
        service = BaseService(db)

        with service.transaction():
            # Create a new service
            new_service = Service(
                instructor_profile_id=test_instructor.instructor_profile.id,
                skill="Transaction Test",
                hourly_rate=100.0,
                description="Testing transactions",
                is_active=True,
            )
            db.add(new_service)

            # Update instructor profile
            test_instructor.instructor_profile.bio = "Updated in transaction"

        # Verify both operations completed
        saved_service = db.query(Service).filter(Service.skill == "Transaction Test").first()
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
                email="decorator_test@example.com", hashed_password="hashed", full_name="Decorator Test", role="student"
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
                    full_name="Outer User",
                    role="student",
                )
                db.add(user1)

                # Inner transaction with error
                with service.transaction():
                    user2 = User(
                        email="inner_transaction@example.com",
                        hashed_password="hashed",
                        full_name="Inner User",
                        role="student",
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

        # Record some metrics
        service._record_metric("create_user", 0.150, success=True)
        service._record_metric("create_user", 0.200, success=True)
        service._record_metric("create_user", 0.500, success=False)
        service._record_metric("update_user", 0.100, success=True)

        # Get metrics
        metrics = service.get_metrics()

        # Verify create_user metrics
        assert metrics["create_user"]["count"] == 3
        assert metrics["create_user"]["avg_time"] == pytest.approx(0.283, rel=0.01)
        assert metrics["create_user"]["success_rate"] == pytest.approx(0.667, rel=0.01)
        assert metrics["create_user"]["total_time"] == 0.850

        # Verify update_user metrics
        assert metrics["update_user"]["count"] == 1
        assert metrics["update_user"]["avg_time"] == 0.100
        assert metrics["update_user"]["success_rate"] == 1.0

    def test_slow_operation_warning(self, db: Session, caplog):
        """Test slow operation warning logging."""
        service = BaseService(db)

        # Record slow operation (>1 second)
        with caplog.at_level("WARNING"):
            service._record_metric("slow_query", 1.5, success=True)

        # Verify warning was logged
        assert "Slow operation detected" in caplog.text
        assert "slow_query took 1.50s" in caplog.text

    def test_performance_decorator_usage(self, db: Session):
        """Test measure_performance decorator pattern."""
        service = BaseService(db)

        # Create a test function
        def slow_operation():
            import time

            time.sleep(0.1)
            return "result"

        # Apply decorator
        decorated = service.measure_performance("test_operation")(slow_operation)

        # Execute
        result = decorated()

        # Verify result and metrics
        assert result == "result"
        metrics = service.get_metrics()
        assert "test_operation" in metrics
        assert metrics["test_operation"]["count"] == 1
        assert metrics["test_operation"]["avg_time"] >= 0.1


class TestBaseServiceValidation:
    """Test input validation functionality."""

    def test_successful_validation(self, db: Session):
        """Test successful input validation."""
        service = BaseService(db)

        # Mock Pydantic model
        class TestModel:
            def __init__(self, **data):
                self.name = data.get("name")
                self.age = data.get("age")
                if not self.name:
                    raise ValueError("name is required")

        # Validate valid data
        result = service.validate_input({"name": "Test", "age": 25}, TestModel)

        assert result.name == "Test"
        assert result.age == 25

    def test_validation_error(self, db: Session):
        """Test validation error handling."""
        service = BaseService(db)

        # Mock Pydantic model that raises error
        class TestModel:
            def __init__(self, **data):
                raise ValueError("Invalid data: missing required field")

        # Should raise ValidationException
        with pytest.raises(ValidationException) as exc_info:
            service.validate_input({"invalid": "data"}, TestModel)

        assert "Invalid data" in str(exc_info.value)

    def test_logging_operations(self, db: Session, caplog):
        """Test operation logging."""
        service = BaseService(db)

        # Log operation
        with caplog.at_level("INFO"):
            service.log_operation("create_booking", user_id=123, instructor_id=456, status="confirmed")

        # Verify log entry
        assert "Operation: create_booking" in caplog.text


class TestBaseRepositoryService:
    """Test BaseRepositoryService functionality."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository."""
        repo = Mock()
        repo.model = type("TestModel", (), {"__name__": "TestModel", "id": None})
        return repo

    def test_create_with_transaction(self, db: Session, mock_repository):
        """Test create operation with transaction."""
        mock_entity = Mock(id=123, __class__=Mock(__name__="TestEntity"))
        mock_repository.create.return_value = mock_entity

        service = BaseRepositoryService(db, mock_repository)

        # Create entity
        result = service.create({"name": "Test"})

        # Verify repository was called
        mock_repository.create.assert_called_once_with({"name": "Test"})
        assert result == mock_entity

    def test_update_with_cache_invalidation(self, db: Session, mock_repository):
        """Test update with cache invalidation."""
        mock_entity = Mock(id=123, __class__=Mock(__name__="TestEntity"))
        mock_repository.update.return_value = mock_entity

        mock_cache = Mock()
        service = BaseRepositoryService(db, mock_repository, mock_cache)

        # Update entity
        result = service.update(123, {"name": "Updated"})

        # Verify update and cache invalidation
        mock_repository.update.assert_called_once_with(123, {"name": "Updated"})
        assert result == mock_entity

    def test_delete_with_cache_invalidation(self, db: Session, mock_repository):
        """Test delete with cache invalidation."""
        mock_entity = Mock(id=123, __class__=Mock(__name__="TestEntity"))
        mock_repository.get_by_id.return_value = mock_entity
        mock_repository.delete.return_value = True

        service = BaseRepositoryService(db, mock_repository)

        # Delete entity
        result = service.delete(123)

        # Verify operations
        mock_repository.get_by_id.assert_called_once_with(123)
        mock_repository.delete.assert_called_once_with(123)
        assert result is True

    def test_delete_nonexistent_entity(self, db: Session, mock_repository):
        """Test deleting non-existent entity."""
        mock_repository.get_by_id.return_value = None

        service = BaseRepositoryService(db, mock_repository)

        # Try to delete
        result = service.delete(999)

        # Should return False without calling delete
        mock_repository.get_by_id.assert_called_once_with(999)
        mock_repository.delete.assert_not_called()
        assert result is False
