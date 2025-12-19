# backend/tests/test_redis_connection.py
"""
Simple test to verify Redis connection in CI environment.
"""

import os

import pytest
import redis
from redis.exceptions import ConnectionError


def test_redis_connection():
    """Test that we can connect to Redis."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    try:
        # Create Redis client
        client = redis.from_url(redis_url)

        # Test basic operations
        test_key = "test:connection"
        test_value = "hello"

        # SET
        client.set(test_key, test_value)

        # GET
        result = client.get(test_key)
        assert result.decode() == test_value

        # DELETE
        client.delete(test_key)

        # PING
        assert client.ping() is True

        print(f"✅ Redis connection successful at {redis_url}")

    except ConnectionError as e:
        pytest.fail(f"❌ Failed to connect to Redis at {redis_url}: {str(e)}")
    except Exception as e:
        pytest.fail(f"❌ Redis operation failed: {str(e)}")


def test_redis_performance():
    """Test Redis performance for cache operations."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.from_url(redis_url)

    import time

    # Test write speed
    start = time.time()
    for i in range(100):
        client.set(f"perf:test:{i}", f"value_{i}")
    write_time = time.time() - start

    # Test read speed
    start = time.time()
    for i in range(100):
        client.get(f"perf:test:{i}")
    read_time = time.time() - start

    # Cleanup
    for i in range(100):
        client.delete(f"perf:test:{i}")

    print(f"✅ Redis Performance: 100 writes in {write_time:.3f}s, 100 reads in {read_time:.3f}s")

    # Assert reasonable performance (default < 100ms in CI; allow slower local runs).
    threshold_s = float(
        os.getenv("REDIS_PERF_THRESHOLD_S", "0.1" if os.getenv("CI") else "0.2")
    )
    assert write_time < threshold_s
    assert read_time < threshold_s


if __name__ == "__main__":
    # Allow running directly
    test_redis_connection()
    test_redis_performance()
