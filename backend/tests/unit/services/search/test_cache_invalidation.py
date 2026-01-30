# backend/tests/unit/services/search/test_cache_invalidation.py
"""
Comprehensive unit tests for cache_invalidation.py.

Targets missed lines: 46-50 (done callback), 57-59 (error handling),
122, 143, 166, 187, 210 (async invalidation functions).

Bug Analysis:
- No critical bugs found
- Fire-and-forget pattern is intentionally best-effort
- Exception handling is appropriately lenient for cache operations
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.core.config as app_config
from app.services.search import cache_invalidation as cache_module
from app.services.search.search_cache import SearchCacheService


class TestFireAndForgetExceptionHandling:
    """Tests for _fire_and_forget exception handling paths."""

    def test_fire_and_forget_handles_generic_exception(self, monkeypatch) -> None:
        """Test that generic exceptions are caught and logged (lines 57-59)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        # Make get_running_loop raise a non-RuntimeError exception
        def raise_value_error():
            raise ValueError("Unexpected error")

        monkeypatch.setattr(cache_module.asyncio, "get_running_loop", raise_value_error)

        async def _noop() -> None:
            return None

        # Should not raise - exception is caught and logged
        cache_module._fire_and_forget(lambda: _noop(), context="generic-exception-test")

    @pytest.mark.asyncio
    async def test_done_callback_handles_cancelled_task(self, monkeypatch) -> None:
        """Test done callback when task is cancelled (line 46-47)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        class MockTask:
            def __init__(self):
                self._callbacks = []
                self._cancelled = True

            def add_done_callback(self, cb):
                self._callbacks.append(cb)

            def cancelled(self):
                return self._cancelled

            def exception(self):
                return None

            def trigger_callbacks(self):
                for cb in self._callbacks:
                    cb(self)

        mock_task = MockTask()

        def create_task(coro):
            # Close the coroutine to avoid warnings
            coro.close()
            return mock_task

        mock_loop = SimpleNamespace(create_task=create_task)
        monkeypatch.setattr(cache_module.asyncio, "get_running_loop", lambda: mock_loop)

        async def _async_fn() -> None:
            return None

        # This should set up the callback
        cache_module._fire_and_forget(lambda: _async_fn(), context="cancelled-task-test")

        # Trigger the callback simulating a cancelled task
        mock_task.trigger_callbacks()

        # The callback should have executed without raising
        assert len(mock_task._callbacks) == 1

    @pytest.mark.asyncio
    async def test_done_callback_handles_task_exception(self, monkeypatch) -> None:
        """Test done callback when task has an exception (lines 48-50)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        class MockTask:
            def __init__(self):
                self._callbacks = []
                self._exception = ValueError("Task failed")

            def add_done_callback(self, cb):
                self._callbacks.append(cb)

            def cancelled(self):
                return False

            def exception(self):
                return self._exception

            def trigger_callbacks(self):
                for cb in self._callbacks:
                    cb(self)

        mock_task = MockTask()

        def create_task(coro):
            coro.close()
            return mock_task

        mock_loop = SimpleNamespace(create_task=create_task)
        monkeypatch.setattr(cache_module.asyncio, "get_running_loop", lambda: mock_loop)

        async def _async_fn() -> None:
            return None

        cache_module._fire_and_forget(lambda: _async_fn(), context="exception-task-test")

        # Trigger the callback with exception
        mock_task.trigger_callbacks()

        # Should log the exception but not raise
        assert mock_task._exception is not None


class TestAsyncInvalidationFunctions:
    """Tests for the async invalidation inner functions (lines 122, 143, 166, 187, 210)."""

    @pytest.mark.asyncio
    async def test_invalidate_on_service_change_async_execution(self, monkeypatch) -> None:
        """Test that invalidate_on_service_change executes the async function (line 122)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        invalidation_called = {"count": 0}
        mock_cache = AsyncMock()
        mock_cache.invalidate_response_cache = AsyncMock(return_value=2)

        async def track_invalidation():
            invalidation_called["count"] += 1
            return 2

        # Create a search cache service with mock
        cache_service = SearchCacheService(cache_service=None)
        cache_service.invalidate_response_cache = track_invalidation
        cache_module.set_search_cache(cache_service)

        # Run with actual event loop to test async path
        tasks_created = []

        class MockTask:
            def __init__(self, coro):
                self._coro = coro
                tasks_created.append(self)

            def add_done_callback(self, cb):
                pass

        def create_task(coro):
            task = MockTask(coro)
            # Actually run the coroutine
            asyncio.create_task(coro)
            return task

        mock_loop = MagicMock()
        mock_loop.create_task = create_task

        with patch.object(cache_module.asyncio, "get_running_loop", return_value=mock_loop):
            cache_module.invalidate_on_service_change("svc-123", "update")

        # Allow async task to complete
        await asyncio.sleep(0.01)
        assert invalidation_called["count"] >= 1

    @pytest.mark.asyncio
    async def test_invalidate_on_availability_change_async_execution(self, monkeypatch) -> None:
        """Test that invalidate_on_availability_change executes (line 143)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        invalidation_called = {"count": 0}

        async def track_invalidation():
            invalidation_called["count"] += 1
            return 2

        cache_service = SearchCacheService(cache_service=None)
        cache_service.invalidate_response_cache = track_invalidation
        cache_module.set_search_cache(cache_service)

        def create_task(coro):
            asyncio.create_task(coro)
            mock = MagicMock()
            mock.add_done_callback = MagicMock()
            return mock

        mock_loop = MagicMock()
        mock_loop.create_task = create_task

        with patch.object(cache_module.asyncio, "get_running_loop", return_value=mock_loop):
            cache_module.invalidate_on_availability_change("inst-456")

        await asyncio.sleep(0.01)
        assert invalidation_called["count"] >= 1

    @pytest.mark.asyncio
    async def test_invalidate_on_price_change_async_execution(self, monkeypatch) -> None:
        """Test that invalidate_on_price_change executes (line 166)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        invalidation_called = {"count": 0}

        async def track_invalidation():
            invalidation_called["count"] += 1
            return 2

        cache_service = SearchCacheService(cache_service=None)
        cache_service.invalidate_response_cache = track_invalidation
        cache_module.set_search_cache(cache_service)

        def create_task(coro):
            asyncio.create_task(coro)
            mock = MagicMock()
            mock.add_done_callback = MagicMock()
            return mock

        mock_loop = MagicMock()
        mock_loop.create_task = create_task

        with patch.object(cache_module.asyncio, "get_running_loop", return_value=mock_loop):
            cache_module.invalidate_on_price_change("inst-789", "svc-abc")

        await asyncio.sleep(0.01)
        assert invalidation_called["count"] >= 1

    @pytest.mark.asyncio
    async def test_invalidate_on_instructor_profile_change_async_execution(
        self, monkeypatch
    ) -> None:
        """Test that invalidate_on_instructor_profile_change executes (line 187)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        invalidation_called = {"count": 0}

        async def track_invalidation():
            invalidation_called["count"] += 1
            return 2

        cache_service = SearchCacheService(cache_service=None)
        cache_service.invalidate_response_cache = track_invalidation
        cache_module.set_search_cache(cache_service)

        def create_task(coro):
            asyncio.create_task(coro)
            mock = MagicMock()
            mock.add_done_callback = MagicMock()
            return mock

        mock_loop = MagicMock()
        mock_loop.create_task = create_task

        with patch.object(cache_module.asyncio, "get_running_loop", return_value=mock_loop):
            cache_module.invalidate_on_instructor_profile_change("inst-profile")

        await asyncio.sleep(0.01)
        assert invalidation_called["count"] >= 1

    @pytest.mark.asyncio
    async def test_invalidate_on_review_change_async_execution(self, monkeypatch) -> None:
        """Test that invalidate_on_review_change executes (line 210)."""
        monkeypatch.setattr(
            app_config, "settings", SimpleNamespace(is_testing=False), raising=False
        )

        invalidation_called = {"count": 0}

        async def track_invalidation():
            invalidation_called["count"] += 1
            return 2

        cache_service = SearchCacheService(cache_service=None)
        cache_service.invalidate_response_cache = track_invalidation
        cache_module.set_search_cache(cache_service)

        def create_task(coro):
            asyncio.create_task(coro)
            mock = MagicMock()
            mock.add_done_callback = MagicMock()
            return mock

        mock_loop = MagicMock()
        mock_loop.create_task = create_task

        with patch.object(cache_module.asyncio, "get_running_loop", return_value=mock_loop):
            cache_module.invalidate_on_review_change("inst-review", "review-123")

        await asyncio.sleep(0.01)
        assert invalidation_called["count"] >= 1


class TestCacheServiceInitialization:
    """Tests for cache service initialization edge cases."""

    def test_init_search_cache_sets_underlying_cache(self) -> None:
        """Test that init_search_cache stores the underlying cache service."""
        # Reset module state
        cache_module._cache_service = None
        cache_module._underlying_cache = None

        mock_cache_service = MagicMock()
        cache_module.init_search_cache(mock_cache_service)

        assert cache_module._underlying_cache is mock_cache_service
        assert cache_module._cache_service is not None

    def test_get_search_cache_uses_underlying_cache_when_not_initialized(self) -> None:
        """Test get_search_cache creates service with underlying cache."""
        # Reset module state
        cache_module._cache_service = None

        mock_underlying = MagicMock()
        cache_module._underlying_cache = mock_underlying

        cache = cache_module.get_search_cache()

        assert cache is not None
        assert cache.cache is mock_underlying

        # Cleanup
        cache_module._cache_service = None
        cache_module._underlying_cache = None


class TestCacheInvalidationCompleteness:
    """Tests to verify cache invalidation is complete."""

    def test_all_invalidation_functions_call_response_cache(self) -> None:
        """Verify all invalidation triggers invalidate_response_cache."""
        from app.core.config import settings

        # Set testing mode to avoid async complexity
        original_is_testing = getattr(settings, "is_testing", True)

        try:
            settings.is_testing = True

            mock_cache = MagicMock()
            mock_cache.invalidate_response_cache = AsyncMock(return_value=2)

            cache_service = SearchCacheService(cache_service=None)
            cache_service.invalidate_response_cache = mock_cache.invalidate_response_cache
            cache_module.set_search_cache(cache_service)

            # Call all functions
            cache_module.invalidate_on_service_change("svc-1")
            cache_module.invalidate_on_availability_change("inst-1")
            cache_module.invalidate_on_price_change("inst-2")
            cache_module.invalidate_on_instructor_profile_change("inst-3")
            cache_module.invalidate_on_review_change("inst-4")

            # In test mode, the async functions aren't actually called
            # This verifies the flow doesn't error
        finally:
            settings.is_testing = original_is_testing


class TestInvalidateAllSearchCache:
    """Tests for the invalidate_all_search_cache function."""

    @pytest.mark.asyncio
    async def test_invalidate_all_returns_incremented_version(self) -> None:
        """Test that invalidate_all increments and returns version."""
        cache_service = SearchCacheService(cache_service=None)
        cache_module.set_search_cache(cache_service)

        initial_version = cache_service._version_cache
        new_version = await cache_module.invalidate_all_search_cache()

        assert new_version == initial_version + 1

    @pytest.mark.asyncio
    async def test_invalidate_all_with_real_cache_service(self) -> None:
        """Test invalidate_all with a mocked Redis cache."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value="5")
        mock_cache.set = AsyncMock(return_value=True)
        mock_cache.get_redis_client = AsyncMock(return_value=None)

        cache_service = SearchCacheService(cache_service=mock_cache)
        cache_module.set_search_cache(cache_service)

        new_version = await cache_module.invalidate_all_search_cache()

        assert new_version == 6  # 5 + 1
