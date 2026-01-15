# backend/tests/test_cache.py
"""
Test cache implementation with DragonflyDB.
"""

import asyncio
import time

import pytest

from app.database import SessionLocal
from app.services.cache_service import get_cache_service


async def _close_cache(cache) -> None:
    redis_client = await cache.get_redis_client()
    if redis_client is None:
        return
    await redis_client.close()
    await redis_client.connection_pool.disconnect()


@pytest.mark.asyncio
async def test_cache_connection():
    """Test that we can connect to cache."""
    db = SessionLocal()
    cache = None
    try:
        cache = get_cache_service(db)
        assert cache is not None

        # Check if we have Redis connection
        redis_client = await cache.get_redis_client()
        if redis_client:
            print("✅ Connected to DragonflyDB!")
            stats = await cache.get_stats()
            print(f"   Hit rate: {stats.get('hit_rate')}")
            print(f"   Total requests: {stats.get('total_requests')}")
        else:
            print("⚠️  Using InMemoryCache (DragonflyDB not available)")
    finally:
        if cache is not None:
            await _close_cache(cache)
        db.close()


@pytest.mark.asyncio
async def test_cache_operations():
    """Test basic cache operations."""
    db = SessionLocal()
    cache = None
    try:
        cache = get_cache_service(db)

        # Test set/get
        await cache.set("test_key", {"data": "test_value"}, ttl=60)
        result = await cache.get("test_key")
        assert result == {"data": "test_value"}

        # Test delete
        await cache.delete("test_key")
        result = await cache.get("test_key")
        assert result is None

        # Test pattern operations
        await cache.set("user:1", {"name": "John"}, ttl=60)
        await cache.set("user:2", {"name": "Jane"}, ttl=60)
        await cache.set("booking:1", {"id": 1}, ttl=60)

        # Delete pattern
        deleted = await cache.delete_pattern("user:*")
        assert deleted >= 2  # At least 2 deleted

        # Verify only booking remains
        assert await cache.get("user:1") is None
        assert await cache.get("user:2") is None
        assert await cache.get("booking:1") is not None

        # Cleanup
        await cache.delete("booking:1")
    finally:
        if cache is not None:
            await _close_cache(cache)
        db.close()


@pytest.mark.asyncio
async def test_cache_performance():
    """Test cache performance."""
    db = SessionLocal()
    cache = None
    try:
        cache = get_cache_service(db)

        # Test write performance
        start = time.time()
        for i in range(100):  # Reduced from 1000 for faster tests
            await cache.set(f"perf_test:{i}", {"value": i}, ttl=60)
        write_time = time.time() - start

        # Test read performance
        start = time.time()
        for i in range(100):
            await cache.get(f"perf_test:{i}")
        read_time = time.time() - start

        print("\n📊 Cache Performance:")
        print(f"   100 writes: {write_time:.3f}s ({100/write_time:.0f} ops/sec)")
        print(f"   100 reads: {read_time:.3f}s ({100/read_time:.0f} ops/sec)")

        # Cleanup
        await cache.delete_pattern("perf_test:*")
    finally:
        if cache is not None:
            await _close_cache(cache)
        db.close()


@pytest.mark.asyncio
async def test_cache_invalidation():
    """Test cache invalidation for availability."""
    db = SessionLocal()
    cache = None
    try:
        cache = get_cache_service(db)

        # Test instructor availability invalidation
        instructor_id = 123
        await cache.set("avail:week:123:2025-06-16", {"slots": []}, ttl=300)
        await cache.set("avail:day:123:2025-06-16", {"slots": []}, ttl=300)

        # Invalidate instructor availability
        await cache.invalidate_instructor_availability(instructor_id, [])

        # Should have cleared pattern
        assert await cache.get("avail:week:123:2025-06-16") is None
    finally:
        if cache is not None:
            await _close_cache(cache)
        db.close()


async def _main() -> None:  # pragma: no cover
    # Run directly for detailed output
    print("Running cache tests...")
    await test_cache_connection()
    await test_cache_operations()
    await test_cache_performance()
    await test_cache_invalidation()
    print("\n✅ All cache tests completed!")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
