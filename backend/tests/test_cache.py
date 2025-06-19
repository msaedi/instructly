# backend/tests/test_cache.py
"""
Test cache implementation with DragonflyDB.
"""

import pytest
import asyncio
from app.infrastructure.cache.redis_cache import get_cache, RedisCache, InMemoryCache


def test_cache_connection():
    """Test that we can connect to cache."""
    cache = get_cache()
    assert cache is not None
    
    # Check if we got Redis or InMemory
    if isinstance(cache, RedisCache):
        print("✅ Connected to DragonflyDB!")
        info = cache.info()
        print(f"   Memory usage: {info.get('used_memory_human')}")
        print(f"   Version: {info.get('dragonfly_version')}")
    else:
        print("⚠️  Using InMemoryCache (DragonflyDB not available)")


@pytest.mark.asyncio
async def test_cache_operations():
    """Test basic cache operations."""
    cache = get_cache()
    
    # Test set/get
    await cache.set("test_key", {"data": "test_value"}, ttl=60)
    result = await cache.get("test_key")
    assert result == {"data": "test_value"}
    
    # Test delete
    cache.delete("test_key")
    result = await cache.get("test_key")
    assert result is None
    
    # Test pattern operations
    await cache.set("user:1", {"name": "John"}, ttl=60)
    await cache.set("user:2", {"name": "Jane"}, ttl=60)
    await cache.set("booking:1", {"id": 1}, ttl=60)
    
    # Delete pattern
    deleted = cache.delete_pattern("user:*")
    assert deleted == 2
    
    # Verify only booking remains
    assert await cache.get("user:1") is None
    assert await cache.get("user:2") is None
    assert await cache.get("booking:1") is not None


def test_sync_operations():
    """Test synchronous cache operations."""
    cache = get_cache()
    
    # Test sync methods
    cache.set_sync("sync_test", "sync_value", ttl=60)
    result = cache.get_sync("sync_test")
    assert result == "sync_value"


@pytest.mark.asyncio
async def test_cache_performance():
    """Test cache performance."""
    cache = get_cache()
    import time
    
    # Test write performance
    start = time.time()
    for i in range(1000):
        await cache.set(f"perf_test:{i}", {"value": i}, ttl=60)
    write_time = time.time() - start
    
    # Test read performance
    start = time.time()
    for i in range(1000):
        await cache.get(f"perf_test:{i}")
    read_time = time.time() - start
    
    print(f"\n📊 Cache Performance:")
    print(f"   1000 writes: {write_time:.3f}s ({1000/write_time:.0f} ops/sec)")
    print(f"   1000 reads: {read_time:.3f}s ({1000/read_time:.0f} ops/sec)")
    
    # Cleanup
    cache.delete_pattern("perf_test:*")


if __name__ == "__main__":
    # Run directly for detailed output
    test_cache_connection()
    asyncio.run(test_cache_operations())
    test_sync_operations()
    asyncio.run(test_cache_performance())