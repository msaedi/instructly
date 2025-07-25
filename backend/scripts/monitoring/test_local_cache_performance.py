#!/usr/bin/env python3
"""Test cache performance locally."""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.services.cache_service import CacheService
from app.services.instructor_service import InstructorService


def test_catalog_performance():
    """Test catalog service performance with and without cache."""
    db = SessionLocal()
    cache_service = CacheService(db)
    instructor_service = InstructorService(db, cache_service)

    print("=== Cache Performance Test ===\n")

    # Clear cache first
    cache_service.delete("catalog:services:all")
    print("✓ Cache cleared\n")

    # Test 1: First call (cache miss)
    start = time.time()
    result1 = instructor_service.get_available_catalog_services()
    time1 = (time.time() - start) * 1000
    print(f"Call 1 (cache MISS): {time1:.1f}ms - Found {len(result1)} services")

    # Test 2: Second call (cache hit)
    start = time.time()
    result2 = instructor_service.get_available_catalog_services()
    time2 = (time.time() - start) * 1000
    print(f"Call 2 (cache HIT):  {time2:.1f}ms - Found {len(result2)} services")

    # Test 3: Third call (cache hit)
    start = time.time()
    result3 = instructor_service.get_available_catalog_services()
    time3 = (time.time() - start) * 1000
    print(f"Call 3 (cache HIT):  {time3:.1f}ms - Found {len(result3)} services")

    # Calculate improvement
    improvement = time1 / time2 if time2 > 0 else 0
    print(f"\n📊 Performance Improvement: {improvement:.1f}x faster with cache!")
    print(f"   Database query: {time1:.1f}ms")
    print(f"   Cached response: {time2:.1f}ms")
    print(f"   Time saved per request: {time1 - time2:.1f}ms")

    # Check cache stats
    stats = cache_service.get_stats()
    print(f"\n📈 Cache Stats:")
    print(f"   Type: {type(cache_service.cache).__name__}")
    print(f"   Hit Rate: {stats.get('hit_rate', 'N/A')}")

    db.close()


if __name__ == "__main__":
    test_catalog_performance()
