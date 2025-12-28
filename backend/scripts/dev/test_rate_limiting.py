# backend/scripts/test_rate_limiting.py
"""
Diagnostic script to test rate limiting setup.

Run this to verify:
1. DragonflyDB connection
2. Rate limiting logic
3. Endpoint protection
"""

import asyncio
from pathlib import Path
import sys

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.middleware.rate_limiter import RateLimiter
from app.services.cache_service import get_cache_service


def test_cache_connection():
    """Test if cache service is working."""
    print("Testing cache connection...")
    cache = get_cache_service()

    if not cache.redis:
        print("❌ Cache not available - DragonflyDB not running?")
        return False

    try:
        cache.redis.ping()
        print("✅ Cache connection successful")
        return True
    except Exception as e:
        print(f"❌ Cache connection failed: {e}")
        return False


def test_rate_limiter():
    """Test rate limiter functionality."""
    print("\nTesting rate limiter...")

    if not settings.rate_limit_enabled:
        print("⚠️  Rate limiting is disabled in settings")
        return

    limiter = RateLimiter()

    # Test rate limiting
    identifier = "test_user_123"
    limit = 3
    window = 60

    print(f"\nTesting {limit} requests per {window} seconds for '{identifier}':")

    for i in range(5):
        allowed, count, retry_after = limiter.check_rate_limit(
            identifier=identifier, limit=limit, window_seconds=window, window_name="test"
        )

        if allowed:
            print(f"  Request {i+1}: ✅ Allowed (count: {count})")
        else:
            print(f"  Request {i+1}: ❌ Blocked (retry after: {retry_after}s)")

    # Clean up
    limiter.reset_limit(identifier, "test")
    print("\n✅ Rate limiter test complete")


def test_settings():
    """Display current rate limit settings."""
    print("\nCurrent rate limit settings:")
    print(f"  Enabled: {settings.rate_limit_enabled}")
    print(f"  General per minute: {settings.rate_limit_general_per_minute}")
    print(f"  Auth per minute: {settings.rate_limit_auth_per_minute}")
    print(f"  Password reset per hour: {settings.rate_limit_password_reset_per_hour}")
    print(f"  Password reset IP per hour: {settings.rate_limit_password_reset_ip_per_hour}")
    print(f"  Booking per minute: {settings.rate_limit_booking_per_minute}")


async def test_endpoints():
    """Test actual endpoints."""
    import aiohttp

    print("\nTesting actual endpoints...")

    async with aiohttp.ClientSession() as session:
        # Test the rate limit test endpoint
        print("\n1. Testing /metrics/rate-limits/test (limit: 3/minute):")
        for i in range(5):
            try:
                async with session.get("http://localhost:8000/metrics/rate-limits/test") as resp:
                    status = resp.status
                    if status == 200:
                        print(f"   Request {i+1}: ✅ {status}")
                    else:
                        print(f"   Request {i+1}: ❌ {status}")
                        if status == 429:
                            data = await resp.json()
                            print(f"     {data.get('detail', {}).get('message', 'Rate limited')}")
            except Exception as e:
                print(f"   Request {i+1}: ❌ Error: {e}")

        # Test password reset endpoint
        print("\n2. Testing /auth/password-reset/request:")
        try:
            async with session.post(
                "http://localhost:8000/auth/password-reset/request", json={"email": "test@example.com"}
            ) as resp:
                status = resp.status
                data = await resp.json()
                print(f"   Status: {status}")
                print(f"   Response: {data}")
        except Exception as e:
            print(f"   ❌ Error: {e}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Rate Limiting Diagnostic Tool")
    print("=" * 60)

    # Test cache connection
    if not test_cache_connection():
        print("\n⚠️  Please ensure DragonflyDB is running:")
        print(
            "  docker run -d --name instainstru_dragonfly -p 6379:6379 docker.dragonflydb.io/dragonflydb/dragonfly:latest"
        )
        return

    # Test rate limiter
    test_rate_limiter()

    # Show settings
    test_settings()

    # Test endpoints if server is running
    try:
        import requests

        resp = requests.get("http://localhost:8000/api/v1/health", timeout=1)
        if resp.status_code == 200:
            asyncio.run(test_endpoints())
        else:
            print("\n⚠️  Server not responding properly")
    except:
        print("\n⚠️  Server not running. Start it with: uvicorn app.main:app --reload")

    print("\n" + "=" * 60)
    print("Diagnostic complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
