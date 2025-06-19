# backend/tests/test_cache.py
"""
Test cache implementation with DragonflyDB.
"""

import pytest
from sqlalchemy.orm import Session
from app.services.cache_service import CacheService, get_cache_service
from app.database import SessionLocal

def test_cache_connection():
    """Test that we can connect to cache."""
    db = SessionLocal()
    cache = get_cache_service(db)
    assert cache is not None
    
    # Check if we have Redis connection
    if cache.redis:
        print("✅ Connected to DragonflyDB!")
        stats = cache.get_stats()
        print(f"   Hit rate: {stats.get('hit_rate')}")
        print(f"   Total requests: {stats.get('total_requests')}")
    else:
        print("⚠️  Using InMemoryCache (DragonflyDB not available)")
    
    db.close()


def test_cache_operations():
    """Test basic cache operations."""
    db = SessionLocal()
    cache = get_cache_service(db)
    
    # Test set/get
    cache.set("test_key", {"data": "test_value"}, ttl=60)
    result = cache.get("test_key")
    assert result == {"data": "test_value"}
    
    # Test delete
    cache.delete("test_key")
    result = cache.get("test_key")
    assert result is None
    
    # Test pattern operations
    cache.set("user:1", {"name": "John"}, ttl=60)
    cache.set("user:2", {"name": "Jane"}, ttl=60)
    cache.set("booking:1", {"id": 1}, ttl=60)
    
    # Delete pattern
    deleted = cache.delete_pattern("user:*")
    assert deleted >= 2  # At least 2 deleted
    
    # Verify only booking remains
    assert cache.get("user:1") is None
    assert cache.get("user:2") is None
    assert cache.get("booking:1") is not None
    
    # Cleanup
    cache.delete("booking:1")
    db.close()


def test_cache_performance():
    """Test cache performance."""
    db = SessionLocal()
    cache = get_cache_service(db)
    import time
    
    # Test write performance
    start = time.time()
    for i in range(100):  # Reduced from 1000 for faster tests
        cache.set(f"perf_test:{i}", {"value": i}, ttl=60)
    write_time = time.time() - start
    
    # Test read performance
    start = time.time()
    for i in range(100):
        cache.get(f"perf_test:{i}")
    read_time = time.time() - start
    
    print(f"\n📊 Cache Performance:")
    print(f"   100 writes: {write_time:.3f}s ({100/write_time:.0f} ops/sec)")
    print(f"   100 reads: {read_time:.3f}s ({100/read_time:.0f} ops/sec)")
    
    # Cleanup
    cache.delete_pattern("perf_test:*")
    db.close()


def test_cache_invalidation():
    """Test cache invalidation for availability."""
    db = SessionLocal()
    cache = get_cache_service(db)
    
    # Test instructor availability invalidation
    instructor_id = 123
    cache.set("avail:week:123:2025-06-16", {"slots": []}, ttl=300)
    cache.set("avail:day:123:2025-06-16", {"slots": []}, ttl=300)
    
    # Invalidate instructor availability
    cache.invalidate_instructor_availability(instructor_id, [])
    
    # Should have cleared pattern
    assert cache.get("avail:week:123:2025-06-16") is None
    
    db.close()


if __name__ == "__main__":
    # Run directly for detailed output
    print("Running cache tests...")
    test_cache_connection()
    test_cache_operations()
    test_cache_performance()
    test_cache_invalidation()
    print("\n✅ All cache tests completed!")