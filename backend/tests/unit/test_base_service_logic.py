# backend/tests/unit/test_base_service_logic.py
"""
Unit tests for BaseService business logic.

These tests isolate the business logic from database and external dependencies
using mocks to ensure we're testing only the service logic.
"""

import time
from unittest.mock import AsyncMock, Mock, call, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationException
from app.services.base import BaseRepositoryService, BaseService, ServiceException


class TestBaseServiceInitialization:
    """Test BaseService initialization and properties."""

    def test_initialization_with_db_only(self):
        """Test basic initialization with just database."""
        mock_db = Mock(spec=Session)

        service = BaseService(mock_db)

        assert service.db == mock_db
        assert service.cache is None
        assert service.logger is not None
        assert service._metrics == {}

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


class TestCacheDecorator:
    """Test cache decorator functionality."""

    @pytest.mark.asyncio
    async def test_async_cache_decorator_hit(self):
        """Test async cache decorator with cache hit."""
        mock_db = Mock(spec=Session)
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value={"cached": "data"})

        service = BaseService(mock_db, mock_cache)

        # Create async function
        async def get_data(self, user_id: int):
            return {"user_id": user_id, "data": "fresh"}

        # Apply decorator
        decorated = service.with_cache("users", ttl=300)(get_data)

        # Execute - should return cached data
        result = await decorated(service, 123)

        assert result == {"cached": "data"}
        mock_cache.get.assert_called_once_with("users:123")
        mock_cache.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_cache_decorator_miss(self):
        """Test async cache decorator with cache miss."""
        mock_db = Mock(spec=Session)
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        service = BaseService(mock_db, mock_cache)

        # Create async function
        async def get_data(self, user_id: int):
            return {"user_id": user_id, "data": "fresh"}

        # Apply decorator
        decorated = service.with_cache("users", ttl=600)(get_data)

        # Execute - should call function and cache result
        result = await decorated(service, 123)

        assert result == {"user_id": 123, "data": "fresh"}
        mock_cache.get.assert_called_once_with("users:123")
        mock_cache.set.assert_called_once_with("users:123", {"user_id": 123, "data": "fresh"}, ttl=600)

    def test_sync_cache_decorator(self):
        """Test sync function with cache decorator."""
        mock_db = Mock(spec=Session)
        mock_cache = Mock()

        service = BaseService(mock_db, mock_cache)

        # Create sync function
        def get_data(self, user_id: int):
            return {"user_id": user_id, "data": "sync"}

        # Apply decorator - should return sync wrapper
        decorated = service.with_cache("users")(get_data)

        # Execute - for now just calls original function
        result = decorated(service, 123)

        assert result == {"user_id": 123, "data": "sync"}

    @pytest.mark.asyncio
    async def test_cache_decorator_with_custom_key_generator(self):
        """Test cache decorator with custom key generator."""
        mock_db = Mock(spec=Session)
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        service = BaseService(mock_db, mock_cache)

        # Custom key generator
        def custom_key(self, user_id: int, include_deleted: bool = False):
            return f"custom:user:{user_id}:deleted_{include_deleted}"

        # Create async function
        async def get_user(self, user_id: int, include_deleted: bool = False):
            return {"user_id": user_id, "include_deleted": include_deleted}

        # Apply decorator with custom key generator
        decorated = service.with_cache("users", ttl=300, key_generator=custom_key)(get_user)

        # Execute
        result = await decorated(service, 456, include_deleted=True)

        # Verify custom key was used
        mock_cache.get.assert_called_once_with("custom:user:456:deleted_True")

    @pytest.mark.asyncio
    async def test_cache_decorator_without_cache_service(self):
        """Test cache decorator when no cache service is available."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db, cache=None)

        # Create async function
        call_count = 0

        async def get_data(self, user_id: int):
            nonlocal call_count
            call_count += 1
            return {"user_id": user_id}

        # Apply decorator
        decorated = service.with_cache("users")(get_data)

        # Execute multiple times - should always call function
        result1 = await decorated(service, 123)
        result2 = await decorated(service, 123)

        assert call_count == 2
        assert result1 == {"user_id": 123}
        assert result2 == {"user_id": 123}


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
        expected_calls = [call("user:123"), call("user:profile:123"), call("user:bookings:123")]
        mock_cache.delete.assert_has_calls(expected_calls)

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
        """Test slow operation warning."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Patch logger to check warning
        with patch.object(service.logger, "warning") as mock_warning:
            service._record_metric("slow_query", 1.5, success=True)

            mock_warning.assert_called_once()
            args = mock_warning.call_args[0][0]
            assert "Slow operation detected" in args
            assert "slow_query took 1.50s" in args

    def test_measure_performance_decorator(self):
        """Test performance measurement decorator."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Function to measure
        def process_data(data):
            time.sleep(0.05)  # Simulate work
            return f"processed_{data}"

        # Apply decorator
        decorated = service.measure_performance("process_data")(process_data)

        # Execute
        result = decorated("test")

        # Verify result and metrics
        assert result == "processed_test"

        metrics = service.get_metrics()
        assert "process_data" in metrics
        assert metrics["process_data"]["count"] == 1
        assert metrics["process_data"]["avg_time"] >= 0.05
        assert metrics["process_data"]["success_rate"] == 1.0

    def test_measure_performance_with_exception(self):
        """Test performance measurement with exception."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Function that raises exception
        def failing_operation():
            time.sleep(0.01)
            raise ValueError("Operation failed")

        # Apply decorator
        decorated = service.measure_performance("failing_op")(failing_operation)

        # Execute and expect exception
        with pytest.raises(ValueError):
            decorated()

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


class TestValidation:
    """Test input validation functionality."""

    def test_validate_input_success(self):
        """Test successful validation."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Mock validator class
        class UserValidator:
            def __init__(self, **data):
                self.email = data["email"]
                self.name = data["name"]

        # Validate
        result = service.validate_input({"email": "test@example.com", "name": "Test User"}, UserValidator)

        assert result.email == "test@example.com"
        assert result.name == "Test User"

    def test_validate_input_failure(self):
        """Test validation failure."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Mock validator that raises exception
        class StrictValidator:
            def __init__(self, **data):
                if "required_field" not in data:
                    raise ValueError("required_field is missing")

        # Should raise ValidationException
        with pytest.raises(ValidationException) as exc_info:
            service.validate_input({"other_field": "value"}, StrictValidator)

        assert "required_field is missing" in str(exc_info.value)

    def test_validate_input_with_pydantic_error(self):
        """Test validation with Pydantic-style error."""
        mock_db = Mock(spec=Session)
        service = BaseService(mock_db)

        # Mock Pydantic validation error
        class PydanticValidator:
            def __init__(self, **data):
                error = type("ValidationError", (Exception,), {"__str__": lambda self: "field required"})()
                raise error

        with pytest.raises(ValidationException) as exc_info:
            service.validate_input({}, PydanticValidator)

        assert "field required" in str(exc_info.value)


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


class TestBaseRepositoryServiceLogic:
    """Test BaseRepositoryService business logic."""

    @pytest.fixture
    def mock_repository(self):
        """Create a mock repository."""
        repo = Mock()
        repo.model = type("TestModel", (), {"__name__": "TestModel", "id": None})
        return repo

    @pytest.mark.asyncio
    async def test_get_by_id_with_cache_hit(self, mock_repository):
        """Test get_by_id with cache hit."""
        mock_db = Mock(spec=Session)
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value={"id": 123, "name": "Cached"})

        service = BaseRepositoryService(mock_db, mock_repository, mock_cache)

        result = await service.get_by_id(123)

        assert result == {"id": 123, "name": "Cached"}
        mock_cache.get.assert_called_once_with("TestModel:123")
        mock_repository.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_by_id_with_cache_miss(self, mock_repository):
        """Test get_by_id with cache miss."""
        mock_db = Mock(spec=Session)
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        mock_entity = Mock(id=123, name="Fresh")
        mock_repository.get_by_id.return_value = mock_entity

        service = BaseRepositoryService(mock_db, mock_repository, mock_cache)

        result = await service.get_by_id(123)

        assert result == mock_entity
        mock_cache.get.assert_called_once_with("TestModel:123")
        mock_repository.get_by_id.assert_called_once_with(123)
        mock_cache.set.assert_called_once_with("TestModel:123", mock_entity, ttl=300)

    @pytest.mark.asyncio
    async def test_get_by_id_without_cache(self, mock_repository):
        """Test get_by_id without cache service."""
        mock_db = Mock(spec=Session)
        mock_entity = Mock(id=123)
        mock_repository.get_by_id.return_value = mock_entity

        service = BaseRepositoryService(mock_db, mock_repository, cache=None)

        result = await service.get_by_id(123)

        assert result == mock_entity
        mock_repository.get_by_id.assert_called_once_with(123)

    def test_create_with_cache_invalidation(self, mock_repository):
        """Test create operation with cache invalidation."""
        mock_db = Mock(spec=Session)
        mock_db.commit = Mock()
        mock_db.rollback = Mock()

        mock_entity = Mock(id=123, __class__=Mock(__name__="TestEntity"))
        mock_repository.create.return_value = mock_entity

        mock_cache = Mock()
        service = BaseRepositoryService(mock_db, mock_repository, mock_cache)

        # Spy on invalidate_cache
        with patch.object(service, "invalidate_cache") as mock_invalidate:
            result = service.create({"name": "New Entity"})

            assert result == mock_entity
            mock_repository.create.assert_called_once_with({"name": "New Entity"})
            mock_invalidate.assert_called_once_with("TestEntity:123")

    def test_update_entity_not_found(self, mock_repository):
        """Test update when entity doesn't exist."""
        mock_db = Mock(spec=Session)
        mock_db.commit = Mock()
        mock_repository.update.return_value = None

        service = BaseRepositoryService(mock_db, mock_repository)

        result = service.update(999, {"name": "Updated"})

        assert result is None
        mock_repository.update.assert_called_once_with(999, {"name": "Updated"})

    def test_delete_with_cache_invalidation(self, mock_repository):
        """Test delete operation with cache invalidation."""
        mock_db = Mock(spec=Session)
        mock_db.commit = Mock()
        mock_db.rollback = Mock()

        mock_entity = Mock(id=123, __class__=Mock(__name__="TestEntity"))
        mock_repository.get_by_id.return_value = mock_entity
        mock_repository.delete.return_value = True

        service = BaseRepositoryService(mock_db, mock_repository)

        with patch.object(service, "invalidate_cache") as mock_invalidate:
            result = service.delete(123)

            assert result is True
            mock_repository.get_by_id.assert_called_once_with(123)
            mock_repository.delete.assert_called_once_with(123)
            mock_invalidate.assert_called_once_with("TestEntity:123")

    def test_invalidate_related_caches_override(self, mock_repository):
        """Test that invalidate_related_caches can be overridden."""
        mock_db = Mock(spec=Session)

        # Create custom service with overridden method
        class CustomRepositoryService(BaseRepositoryService):
            def invalidate_related_caches(self, entity):
                super().invalidate_related_caches(entity)
                # Additional invalidation
                self.invalidate_pattern(f"custom:{entity.id}:*")

        mock_cache = Mock()
        service = CustomRepositoryService(mock_db, mock_repository, mock_cache)

        mock_entity = Mock(id=456, __class__=Mock(__name__="TestEntity"))

        with patch.object(service, "invalidate_cache") as mock_invalidate:
            with patch.object(service, "invalidate_pattern") as mock_pattern:
                service.invalidate_related_caches(mock_entity)

                mock_invalidate.assert_called_once_with("TestEntity:456")
                mock_pattern.assert_called_once_with("custom:456:*")
