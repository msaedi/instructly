#!/usr/bin/env python3
"""Test Instructly production cache performance."""

import statistics
import time

import httpx


def test_catalog_endpoint():
    """Test the catalog endpoint performance."""
    url = "https://api.instainstru.com/services/catalog"
    times = []

    print("Testing Instructly catalog endpoint performance...")
    print("=" * 50)

    # Make 5 requests
    for i in range(5):
        start = time.time()
        response = httpx.get(url, timeout=10)
        duration = (time.time() - start) * 1000  # Convert to ms
        times.append(duration)

        status = "✅" if response.status_code == 200 else f"❌ {response.status_code}"
        print(f"Request {i+1}: {duration:.0f}ms (Status: {status})")

        # Short delay between requests
        if i < 4:
            time.sleep(0.5)

    print("=" * 50)
    print(f"Average: {statistics.mean(times):.0f}ms")
    print(f"Median: {statistics.median(times):.0f}ms")
    print(f"Min: {min(times):.0f}ms")
    print(f"Max: {max(times):.0f}ms")

    # Analysis
    print("\n📊 Analysis:")
    avg_time = statistics.mean(times)

    if avg_time < 200:
        print("✅ Excellent! Caching is working perfectly.")
        print("   Average response time is under 200ms.")
    elif avg_time < 500:
        print("✅ Good performance! Cache is likely working.")
        print("   Average response time is under 500ms.")
    elif avg_time < 1000:
        print("⚠️  Moderate performance.")
        print("   Cache might be working but could be optimized.")
    else:
        print("❌ Slow responses detected (>1s average).")
        print("   Cache might not be working properly.")

    # Check if first request is significantly slower (cold cache)
    if len(times) > 1 and times[0] > times[1] * 1.5:
        print("\n💡 First request was slower (cold cache), subsequent requests were faster.")
        print("   This indicates caching is working correctly!")

    # Compare to the 1.5s baseline
    print("\n📈 Compared to 1.5s baseline:")
    improvement = 1500 / avg_time
    print(f"   Current performance is {improvement:.1f}x faster!")


if __name__ == "__main__":
    test_catalog_endpoint()
