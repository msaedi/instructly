"""
Simple cache performance test - tests the public endpoints without authentication.
Run with: python -m scripts.test_cache_simple
"""

import asyncio
import time
from datetime import date, timedelta

import httpx

# Configuration
BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api"

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


async def test_basic_cache():
    """Test basic caching of public availability endpoint."""
    print(f"\n{BLUE}=== Testing Public Availability Cache ==={RESET}\n")

    async with httpx.AsyncClient() as client:
        # Use instructor ID 1 (assuming it exists from seed data)
        instructor_id = 1
        start_date = date.today()
        end_date = start_date + timedelta(days=7)
        url = f"{API_URL}/public/instructors/{instructor_id}/availability"
        params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

        print(f"Testing endpoint: {url}")
        print(f"Parameters: {params}\n")

        response_times = []

        # Make 5 consecutive requests
        print("Making 5 consecutive requests to test caching:\n")
        for i in range(5):
            start_time = time.time()
            response = await client.get(url, params=params)
            end_time = time.time()

            # Add small delay to avoid rate limiting
            if i < 4:
                await asyncio.sleep(0.5)

            response_time = (end_time - start_time) * 1000  # Convert to ms
            response_times.append(response_time)

            if response.status_code == 200:
                status = f"{GREEN}✓{RESET}"
            elif response.status_code == 404:
                status = f"{RED}✗ (404){RESET}"
            elif response.status_code == 429:
                status = f"{YELLOW}⚠ (429){RESET}"
            else:
                status = f"{RED}✗ ({response.status_code}){RESET}"

            cache_status = "MISS (cold)" if i == 0 else "HIT (warm)"

            print(f"Request {i+1}: {status} {response_time:6.1f}ms - Cache {cache_status}")

            # Show error details on first failure
            if i == 0 and response.status_code != 200:
                print(f"  Error: {response.text.strip()}")

            # Check for cache headers
            if i == 0 and response.status_code == 200:
                print(f"\nResponse headers:")
                print(f"  Cache-Control: {response.headers.get('cache-control', 'Not present')}")
                print(
                    f"  ETag: {response.headers.get('etag', 'Not present')[:20]}..."
                    if response.headers.get("etag")
                    else "  ETag: Not present"
                )
                print()

        # Calculate statistics
        if len(response_times) >= 2:
            first_request = response_times[0]
            avg_cached = sum(response_times[1:]) / (len(response_times) - 1)
            improvement = ((first_request - avg_cached) / first_request * 100) if first_request > 0 else 0

            print(f"\n{BLUE}Performance Summary:{RESET}")
            print(f"  First request (cold cache): {first_request:.1f}ms")
            print(f"  Average cached requests: {avg_cached:.1f}ms")
            print(f"  Cache improvement: {improvement:.1f}%")

            if improvement > 30:
                print(f"\n{GREEN}✓ Cache is working! Seeing {improvement:.0f}% improvement{RESET}")
            else:
                print(f"\n{YELLOW}⚠ Cache improvement is low ({improvement:.0f}%). May need optimization.{RESET}")

        # Test ETag functionality
        print(f"\n{BLUE}Testing ETag (Conditional Requests):{RESET}\n")

        # Get ETag from response
        response = await client.get(url, params=params)
        etag = response.headers.get("etag")

        if etag:
            print(f"ETag received: {etag[:30]}...")

            # Make conditional request
            headers = {"If-None-Match": etag}
            cond_response = await client.get(url, params=params, headers=headers)

            if cond_response.status_code == 304:
                print(f"{GREEN}✓ Conditional request returned 304 Not Modified{RESET}")
                print(f"  Body size: {len(cond_response.content)} bytes (should be 0)")
            else:
                print(f"{RED}✗ Expected 304 but got {cond_response.status_code}{RESET}")
        else:
            print(f"{RED}✗ No ETag header found in response{RESET}")


async def test_cache_across_instructors():
    """Test caching works for multiple instructors."""
    print(f"\n{BLUE}=== Testing Cache Across Multiple Instructors ==={RESET}\n")

    async with httpx.AsyncClient() as client:
        instructor_ids = [1, 2, 3, 4, 5]  # Test with first 5 instructors
        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        # First round - populate cache
        print("First round - populating cache:")
        for instructor_id in instructor_ids:
            url = f"{API_URL}/public/instructors/{instructor_id}/availability"
            params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

            start_time = time.time()
            response = await client.get(url, params=params)
            response_time = (time.time() - start_time) * 1000

            status = f"{GREEN}✓{RESET}" if response.status_code == 200 else f"{RED}✗{RESET}"
            print(f"  Instructor {instructor_id}: {status} {response_time:6.1f}ms")

            # Delay to avoid rate limiting
            await asyncio.sleep(0.5)

        print("\nSecond round - should hit cache:")
        cache_times = []
        for instructor_id in instructor_ids:
            url = f"{API_URL}/public/instructors/{instructor_id}/availability"
            params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

            start_time = time.time()
            response = await client.get(url, params=params)
            response_time = (time.time() - start_time) * 1000
            cache_times.append(response_time)

            status = f"{GREEN}✓{RESET}" if response.status_code == 200 else f"{RED}✗{RESET}"
            print(f"  Instructor {instructor_id}: {status} {response_time:6.1f}ms")

            # Delay to avoid rate limiting
            await asyncio.sleep(0.5)

        if cache_times:
            avg_cache_time = sum(cache_times) / len(cache_times)
            print(f"\n{GREEN}Average cache hit time: {avg_cache_time:.1f}ms{RESET}")


async def test_cache_metrics_endpoint():
    """Test the cache metrics endpoint if accessible."""
    print(f"\n{BLUE}=== Testing Cache Metrics Endpoint ==={RESET}\n")

    async with httpx.AsyncClient() as client:
        # Try to access metrics endpoint (may require auth)
        url = f"{API_URL}/metrics/health"
        response = await client.get(url)

        if response.status_code == 200:
            print(f"{GREEN}✓ Health endpoint accessible{RESET}")
            data = response.json()
            print(f"  Status: {data.get('status')}")
            print(f"  Service: {data.get('service')}")
        else:
            print(f"{YELLOW}Health endpoint returned {response.status_code}{RESET}")


async def main():
    """Run all tests."""
    try:
        await test_basic_cache()
        await test_cache_across_instructors()
        await test_cache_metrics_endpoint()

        print(f"\n{BLUE}=== Test Complete ==={RESET}")
        print(f"\n{GREEN}✓ Cache testing completed successfully{RESET}")
        print("\nRecommendations:")
        print("- Monitor cache hit rates using /metrics/cache endpoint")
        print("- Consider increasing TTL if hit rate is low")
        print("- Use cache warming for frequently accessed data")
        print("- Monitor Redis memory usage for capacity planning")

    except Exception as e:
        print(f"\n{RED}Error during testing: {str(e)}{RESET}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
