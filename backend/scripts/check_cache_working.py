# backend/scripts/test_cache_working.py
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.cache_service import get_cache_service

# Test cache operations
cache = get_cache_service()

# Test basic operations
print("Testing cache...")
cache.set("test_key", {"data": "Hello from cache!"})
result = cache.get("test_key")
print(f"Cache get result: {result}")

# Get stats
stats = cache.get_stats()
print(f"\nCache stats: {stats}")

# Test the cache is actually using Redis/DragonflyDB
if cache.redis:
    print("\n✅ Using DragonflyDB!")
    info = cache.redis.info()
    print(f"DragonflyDB version: {info.get('dragonfly_version', 'unknown')}")
else:
    print("\n⚠️  Using in-memory cache fallback")
