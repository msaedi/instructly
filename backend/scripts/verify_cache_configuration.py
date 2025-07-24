#!/usr/bin/env python3
"""
Verify cache configuration and help diagnose cache issues.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from app.core.config import settings
from app.database import SessionLocal
from app.services.cache_service import CacheService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Check cache configuration and connectivity."""
    print("=== Cache Configuration Verification ===\n")

    # Check environment variables
    print("1. Environment Variables:")
    redis_url = os.getenv("REDIS_URL", "Not set")
    print(f"   REDIS_URL: {redis_url}")
    print(f"   ENVIRONMENT: {settings.environment}")
    print(f"   CACHE_ENABLED: {settings.cache_enabled}")
    print()

    # Check if Redis URL is configured
    if redis_url == "Not set" or redis_url.startswith("redis://localhost"):
        print("⚠️  WARNING: REDIS_URL not configured for production!")
        print("   The application is falling back to in-memory cache.")
        print("   In-memory cache doesn't persist between requests in production.")
        print()
        print("   To fix this:")
        print("   1. Set up Upstash Redis (recommended for Render)")
        print("   2. Add REDIS_URL environment variable in Render dashboard")
        print("   3. Format: rediss://default:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379")
        print()

    # Try to initialize cache service
    print("2. Cache Service Initialization:")
    try:
        db = SessionLocal()
        cache_service = CacheService(db)

        # Check cache type
        cache_type = type(cache_service.cache).__name__
        print(f"   Cache Type: {cache_type}")

        # Test cache operations
        print("\n3. Testing Cache Operations:")

        # Test set
        test_key = "test:cache:verification"
        test_value = {"test": "data", "timestamp": "now"}

        try:
            cache_service.set(test_key, test_value, ttl=60)
            print("   ✅ Cache SET operation successful")
        except Exception as e:
            print(f"   ❌ Cache SET failed: {str(e)}")

        # Test get
        try:
            retrieved = cache_service.get(test_key)
            if retrieved == test_value:
                print("   ✅ Cache GET operation successful")
                print(f"      Retrieved: {retrieved}")
            else:
                print("   ⚠️  Cache GET returned different value")
                print(f"      Expected: {test_value}")
                print(f"      Got: {retrieved}")
        except Exception as e:
            print(f"   ❌ Cache GET failed: {str(e)}")

        # Test delete
        try:
            cache_service.delete(test_key)
            print("   ✅ Cache DELETE operation successful")
        except Exception as e:
            print(f"   ❌ Cache DELETE failed: {str(e)}")

        # Check cache stats
        print("\n4. Cache Statistics:")
        try:
            stats = cache_service.get_stats()
            for key, value in stats.items():
                print(f"   {key}: {value}")
        except Exception as e:
            print(f"   ❌ Failed to get cache stats: {str(e)}")

        db.close()

    except Exception as e:
        print(f"   ❌ Failed to initialize cache service: {str(e)}")

    print("\n=== Recommendations ===")

    if redis_url == "Not set" or redis_url.startswith("redis://localhost"):
        print("\n🔧 To enable proper caching in production:")
        print("1. Sign up for Upstash Redis (free tier available)")
        print("2. Create a Redis database in Upstash")
        print("3. Copy the Redis URL from Upstash dashboard")
        print("4. In Render dashboard:")
        print("   - Go to Environment")
        print("   - Add REDIS_URL with the Upstash URL")
        print("   - Redeploy the service")
        print("\nThis will fix the slow /services/catalog endpoint!")
    else:
        print("\n✅ Redis appears to be configured.")
        print("If you're still experiencing cache issues:")
        print("1. Check the Redis connection in logs")
        print("2. Verify the Redis instance is running")
        print("3. Check for any firewall/network issues")


if __name__ == "__main__":
    main()
