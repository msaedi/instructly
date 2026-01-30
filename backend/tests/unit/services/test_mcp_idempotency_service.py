"""Comprehensive tests for MCPIdempotencyService.

Tests cover idempotency key tracking, concurrent request handling, and Redis integration.
Focus areas based on coverage gaps:
- check_and_store method behavior (lines 32-65)
- store_result method (lines 67-80)
- Concurrent pending status handling (line 55-57)
- _safe_load error handling (lines 92-100)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from app.core.exceptions import ServiceException
from app.services.mcp_idempotency_service import MCPIdempotencyService


class TestMCPIdempotencyService:
    """Tests for MCPIdempotencyService."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.setex = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def service(self, db: Any, mock_redis: AsyncMock) -> MCPIdempotencyService:
        """Create service instance with mocked Redis."""
        return MCPIdempotencyService(db, redis_client=mock_redis)

    class TestCheckAndStore:
        """Tests for check_and_store method (lines 32-65)."""

        @pytest.mark.asyncio
        async def test_new_key_returns_false_none(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """New idempotency key should return (False, None)."""
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True

            is_duplicate, cached_result = await service.check_and_store("key-123", "create_user")

            assert is_duplicate is False
            assert cached_result is None

        @pytest.mark.asyncio
        async def test_new_key_stores_pending_status(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """New key should be stored with pending status."""
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True

            await service.check_and_store("key-123", "create_user")

            # Verify set was called with pending payload
            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            stored_payload = json.loads(call_args[0][1])
            assert stored_payload["status"] == "pending"

        @pytest.mark.asyncio
        async def test_existing_completed_key_returns_cached_result(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Existing key with completed result should return (True, result) (line 48)."""
            cached_result = {"success": True, "user_id": "01HUSERID"}
            mock_redis.get.return_value = json.dumps(cached_result)

            is_duplicate, result = await service.check_and_store("key-123", "create_user")

            assert is_duplicate is True
            assert result == cached_result

        @pytest.mark.asyncio
        async def test_existing_pending_key_returns_true_none(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Existing key with pending status should return (True, None) (lines 46-47)."""
            pending_payload = {"status": "pending"}
            mock_redis.get.return_value = json.dumps(pending_payload)

            is_duplicate, result = await service.check_and_store("key-123", "create_user")

            assert is_duplicate is True
            assert result is None

        @pytest.mark.asyncio
        async def test_race_condition_set_fails_returns_cached(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """When set fails (race condition), should return existing value (lines 52-57)."""
            # First get returns None (key doesn't exist)
            # set returns False (NX condition failed - another process set it)
            # Second get returns the cached result
            cached_result = {"success": True, "data": "from_other_process"}

            mock_redis.get.side_effect = [None, json.dumps(cached_result)]
            mock_redis.set.return_value = False  # NX failed

            is_duplicate, result = await service.check_and_store("key-123", "create_user")

            assert is_duplicate is True
            assert result == cached_result

        @pytest.mark.asyncio
        async def test_race_condition_set_fails_pending_returns_none(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """When set fails and cached is pending, should return (True, None) (lines 55-56)."""
            pending_payload = {"status": "pending"}

            mock_redis.get.side_effect = [None, json.dumps(pending_payload)]
            mock_redis.set.return_value = False

            is_duplicate, result = await service.check_and_store("key-123", "create_user")

            assert is_duplicate is True
            assert result is None

        @pytest.mark.asyncio
        async def test_race_condition_set_fails_no_cached_value(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """When set fails and no cached value, should return (True, None)."""
            mock_redis.get.side_effect = [None, None]
            mock_redis.set.return_value = False

            is_duplicate, result = await service.check_and_store("key-123", "create_user")

            assert is_duplicate is True
            assert result is None

        @pytest.mark.asyncio
        async def test_redis_error_raises_service_exception(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Redis error should raise ServiceException (lines 60-65)."""
            mock_redis.get.side_effect = RedisError("Connection failed")

            with pytest.raises(ServiceException) as exc_info:
                await service.check_and_store("key-123", "create_user")

            assert "temporarily unavailable" in str(exc_info.value.message).lower()
            assert exc_info.value.code == "idempotency_unavailable"

        @pytest.mark.asyncio
        async def test_sets_operation_context(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """check_and_store should set operation context for store_result (line 39)."""
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True

            await service.check_and_store("key-123", "delete_user")

            assert service._operation_context == "delete_user"

        @pytest.mark.asyncio
        async def test_uses_correct_key_format(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Should use correct Redis key format (line 82-83)."""
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True

            await service.check_and_store("my-key", "my-operation")

            expected_key = "mcp:idempotency:my-operation:my-key"
            mock_redis.get.assert_called_with(expected_key)

        @pytest.mark.asyncio
        async def test_sets_ttl_24_hours(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Should set TTL to 24 hours (line 51)."""
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True

            await service.check_and_store("key-123", "create_user")

            call_args = mock_redis.set.call_args
            assert call_args.kwargs["ex"] == 60 * 60 * 24  # 24 hours in seconds

    class TestStoreResult:
        """Tests for store_result method (lines 67-80)."""

        @pytest.mark.asyncio
        async def test_stores_result_with_ttl(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Should store result with correct TTL."""
            # First call check_and_store to set context
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True
            await service.check_and_store("key-123", "create_user")

            # Now store result
            result = {"success": True, "user_id": "01HUSERID"}
            await service.store_result("key-123", result)

            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "mcp:idempotency:create_user:key-123"
            assert call_args[0][1] == 60 * 60 * 24
            assert json.loads(call_args[0][2]) == result

        @pytest.mark.asyncio
        async def test_missing_operation_context_raises(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Should raise if operation context not set (lines 70-74)."""
            # Don't call check_and_store first, so context is None
            service._operation_context = None

            with pytest.raises(ServiceException) as exc_info:
                await service.store_result("key-123", {"result": "data"})

            assert exc_info.value.code == "mcp_idem_operation_missing"

        @pytest.mark.asyncio
        async def test_redis_error_logged_not_raised(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Redis error in store_result should be logged but not raised (lines 79-80)."""
            # Set up context
            mock_redis.get.return_value = None
            mock_redis.set.return_value = True
            await service.check_and_store("key-123", "create_user")

            # Make setex fail
            mock_redis.setex.side_effect = RedisError("Connection lost")

            # Should not raise - just logs the error
            await service.store_result("key-123", {"result": "data"})

            mock_redis.setex.assert_called_once()

    class TestKeyGeneration:
        """Tests for _key method (line 82-83)."""

        def test_key_format(self, service: MCPIdempotencyService) -> None:
            """_key should generate correct format."""
            key = service._key("my_operation", "user-key-123")
            assert key == "mcp:idempotency:my_operation:user-key-123"

        def test_key_with_special_characters(self, service: MCPIdempotencyService) -> None:
            """_key should handle special characters."""
            key = service._key("op:with:colons", "key/with/slashes")
            assert key == "mcp:idempotency:op:with:colons:key/with/slashes"

    class TestGetRedis:
        """Tests for _get_redis method (lines 85-90)."""

        @pytest.mark.asyncio
        async def test_returns_injected_redis(
            self, service: MCPIdempotencyService, mock_redis: AsyncMock
        ) -> None:
            """Should return injected Redis client if available (line 86-87)."""
            redis = await service._get_redis()
            assert redis is mock_redis

        @pytest.mark.asyncio
        async def test_falls_back_to_global_redis(self, db: Any) -> None:
            """Should fall back to global Redis if none injected (lines 88-90)."""
            service = MCPIdempotencyService(db, redis_client=None)

            # Patch get_redis where it's imported from (the redis_backend module)
            with patch(
                "app.ratelimit.redis_backend.get_redis"
            ) as mock_get_redis:
                mock_global_redis = AsyncMock()
                mock_get_redis.return_value = mock_global_redis

                redis = await service._get_redis()

                assert redis is mock_global_redis
                mock_get_redis.assert_called_once()

    class TestSafeLoad:
        """Tests for _safe_load static method (lines 92-100)."""

        def test_valid_json_dict(self) -> None:
            """Valid JSON dict should be returned."""
            raw = json.dumps({"key": "value"})
            result = MCPIdempotencyService._safe_load(raw)
            assert result == {"key": "value"}

        def test_invalid_json_returns_none(self) -> None:
            """Invalid JSON should return None (lines 96-97)."""
            result = MCPIdempotencyService._safe_load("not valid json {{{")
            assert result is None

        def test_non_dict_json_returns_none(self) -> None:
            """Non-dict JSON should return None (lines 98-99)."""
            raw = json.dumps(["list", "not", "dict"])
            result = MCPIdempotencyService._safe_load(raw)
            assert result is None

        def test_json_string_returns_none(self) -> None:
            """JSON string should return None."""
            raw = json.dumps("just a string")
            result = MCPIdempotencyService._safe_load(raw)
            assert result is None

        def test_json_number_returns_none(self) -> None:
            """JSON number should return None."""
            raw = json.dumps(12345)
            result = MCPIdempotencyService._safe_load(raw)
            assert result is None

        def test_json_null_returns_none(self) -> None:
            """JSON null should return None."""
            raw = json.dumps(None)
            result = MCPIdempotencyService._safe_load(raw)
            assert result is None

        def test_empty_string_returns_none(self) -> None:
            """Empty string should return None."""
            result = MCPIdempotencyService._safe_load("")
            assert result is None

        def test_bytes_input(self) -> None:
            """Bytes input should work (Redis returns bytes sometimes)."""
            raw = b'{"key": "value"}'
            result = MCPIdempotencyService._safe_load(raw)
            assert result == {"key": "value"}

        def test_nested_dict(self) -> None:
            """Nested dict should be returned."""
            nested = {"outer": {"inner": {"deep": "value"}}}
            raw = json.dumps(nested)
            result = MCPIdempotencyService._safe_load(raw)
            assert result == nested


class TestIdempotencyServiceIntegration:
    """Integration-style tests for idempotency scenarios."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create a mock Redis that simulates real behavior."""
        storage: dict[str, str] = {}

        async def mock_get(key: str) -> str | None:
            return storage.get(key)

        async def mock_set(key: str, value: str, ex: int = 0, nx: bool = False) -> bool:
            if nx and key in storage:
                return False
            storage[key] = value
            return True

        async def mock_setex(key: str, ttl: int, value: str) -> bool:
            storage[key] = value
            return True

        redis = AsyncMock()
        redis.get = mock_get
        redis.set = mock_set
        redis.setex = mock_setex
        return redis

    @pytest.fixture
    def service(self, db: Any, mock_redis: AsyncMock) -> MCPIdempotencyService:
        """Create service instance."""
        return MCPIdempotencyService(db, redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_full_idempotency_flow(self, service: MCPIdempotencyService) -> None:
        """Test complete idempotency flow: check -> process -> store -> retry."""
        operation = "create_user"
        idem_key = "unique-request-123"

        # First request - should be allowed
        is_dup, cached = await service.check_and_store(idem_key, operation)
        assert is_dup is False
        assert cached is None

        # Simulate processing and store result
        result = {"user_id": "01HUSERID", "success": True}
        await service.store_result(idem_key, result)

        # Reset context for second request simulation
        service._operation_context = None

        # Second request with same key - should return cached
        is_dup2, cached2 = await service.check_and_store(idem_key, operation)
        assert is_dup2 is True
        assert cached2 == result

    @pytest.mark.asyncio
    async def test_different_operations_independent(self, service: MCPIdempotencyService) -> None:
        """Same key for different operations should be independent."""
        idem_key = "shared-key-123"

        # Operation 1
        is_dup1, _ = await service.check_and_store(idem_key, "create_user")
        await service.store_result(idem_key, {"operation": "create_user"})

        # Operation 2 with same key but different operation
        is_dup2, cached = await service.check_and_store(idem_key, "delete_user")

        # Should NOT be duplicate because different operation
        assert is_dup2 is False

    @pytest.mark.asyncio
    async def test_different_keys_same_operation_independent(
        self, service: MCPIdempotencyService
    ) -> None:
        """Different keys for same operation should be independent."""
        operation = "create_user"

        # Key 1
        is_dup1, _ = await service.check_and_store("key-1", operation)
        await service.store_result("key-1", {"result": 1})

        # Key 2 - should NOT be duplicate
        is_dup2, cached = await service.check_and_store("key-2", operation)
        assert is_dup2 is False


class TestConcurrentRequests:
    """Tests for concurrent request handling."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_only_one_processes(self, db: Any) -> None:
        """Only one of concurrent requests should process, others get cached."""
        # This test simulates the race condition scenario

        # Track which request won
        processed_requests: list[int] = []

        # Create a mock Redis that simulates real NX behavior
        storage: dict[str, str] = {}
        lock = asyncio.Lock()

        async def mock_get(key: str) -> str | None:
            return storage.get(key)

        async def mock_set(key: str, value: str, ex: int = 0, nx: bool = False) -> bool:
            async with lock:
                if nx and key in storage:
                    return False
                storage[key] = value
                return True

        async def mock_setex(key: str, ttl: int, value: str) -> bool:
            storage[key] = value
            return True

        redis = AsyncMock()
        redis.get = mock_get
        redis.set = mock_set
        redis.setex = mock_setex

        service = MCPIdempotencyService(db, redis_client=redis)

        async def make_request(request_id: int) -> tuple[bool, Any]:
            is_dup, cached = await service.check_and_store("same-key", "create_user")
            if not is_dup:
                processed_requests.append(request_id)
                # Store result
                service._operation_context = "create_user"
                await service.store_result("same-key", {"processed_by": request_id})
            return is_dup, cached

        # Run multiple concurrent requests
        results = await asyncio.gather(*[make_request(i) for i in range(5)])

        # Only one should have processed (is_dup=False)
        non_duplicates = [r for r in results if r[0] is False]
        assert len(non_duplicates) == 1

        # Exactly one request should have processed
        assert len(processed_requests) == 1
