"""
Test script to verify availability caching performance.
Run with: python -m scripts.test_cache_performance
"""

import asyncio
from datetime import date, timedelta
import time

import httpx

# Configuration
BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api"
TEST_USER_EMAIL = "sarah.chen@example.com"  # Instructor email for testing
TEST_USER_PASSWORD = "TestPass123!"
TEST_STUDENT_EMAIL = "michael.brown@example.com"  # Student email for booking tests
TEST_STUDENT_PASSWORD = "TestPass123!"

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


class CachePerformanceTester:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.auth_token = None
        self.student_auth_token = None
        self.instructor_id = None

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def setup(self):
        """Login and get instructor ID."""
        # Login as instructor to get ID
        login_data = {"username": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
        response = await self.client.post(f"{API_URL}/auth/token", data=login_data)
        if response.status_code == 200:
            auth_data = response.json()
            self.auth_token = auth_data["access_token"]
            self.client.headers["Authorization"] = f"Bearer {self.auth_token}"

            # Get current user info
            user_response = await self.client.get(f"{API_URL}/auth/current-user")
            if user_response.status_code == 200:
                self.instructor_id = user_response.json()["id"]

        # Login as student for booking tests
        student_login = {"username": TEST_STUDENT_EMAIL, "password": TEST_STUDENT_PASSWORD}
        student_response = await self.client.post(f"{API_URL}/auth/token", data=student_login)
        if student_response.status_code == 200:
            self.student_auth_token = student_response.json()["access_token"]

    def print_header(self, title: str):
        """Print a formatted header."""
        print(f"\n{BLUE}{'=' * 60}{RESET}")
        print(f"{BLUE}{title}{RESET}")
        print(f"{BLUE}{'=' * 60}{RESET}\n")

    def print_result(self, test_name: str, passed: bool, message: str = ""):
        """Print test result with color."""
        status = f"{GREEN}✓ PASSED{RESET}" if passed else f"{RED}✗ FAILED{RESET}"
        print(f"{test_name}: {status} {message}")

    async def test_basic_cache_functionality(self):
        """Test 1: Basic Cache Functionality"""
        self.print_header("Test 1: Basic Cache Test")

        if not self.instructor_id:
            print(f"{RED}Setup failed - no instructor ID{RESET}")
            return False

        # Prepare test parameters
        start_date = date.today()
        end_date = start_date + timedelta(days=7)
        url = f"{API_URL}/public/instructors/{self.instructor_id}/availability"
        params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

        response_times = []

        # Make 5 consecutive requests
        for i in range(5):
            start_time = time.time()
            response = await self.client.get(url, params=params)
            end_time = time.time()

            if response.status_code != 200:
                print(f"{RED}Request {i+1} failed with status {response.status_code}{RESET}")
                return False

            response_time = (end_time - start_time) * 1000  # Convert to ms
            response_times.append(response_time)
            print(f"Request {i+1} ({'cold' if i == 0 else 'warm'}): {response_time:.1f}ms")

        # Calculate improvement
        avg_warm = sum(response_times[1:]) / 4
        improvement = ((response_times[0] - avg_warm) / response_times[0]) * 100

        print(f"\nAverage improvement: {improvement:.1f}%")

        # Check if cache is working (subsequent requests should be faster)
        passed = response_times[0] > avg_warm * 1.5  # First request should be at least 50% slower
        self.print_result("Basic cache functionality", passed)

        return passed

    async def test_cache_metrics(self):
        """Test 2: Cache Metrics Verification"""
        self.print_header("Test 2: Cache Metrics")

        # Reset cache stats
        reset_response = await self.client.post(f"{API_URL}/metrics/cache/reset-stats")
        if reset_response.status_code != 200:
            print(f"{YELLOW}Warning: Could not reset cache stats{RESET}")

        # Make 10 requests to different instructors
        instructor_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # Assuming these exist
        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        print("Making first round of requests (cache misses)...")
        for instructor_id in instructor_ids:
            url = f"{API_URL}/public/instructors/{instructor_id}/availability"
            params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
            await self.client.get(url, params=params)

        # Make same requests again (should be cache hits)
        print("Making second round of requests (cache hits)...")
        for instructor_id in instructor_ids:
            url = f"{API_URL}/public/instructors/{instructor_id}/availability"
            params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
            await self.client.get(url, params=params)

        # Check metrics
        metrics_response = await self.client.get(f"{API_URL}/metrics/cache")
        if metrics_response.status_code != 200:
            print(f"{RED}Could not retrieve cache metrics{RESET}")
            return False

        metrics = metrics_response.json()

        # Check availability-specific metrics
        if "availability_metrics" in metrics:
            avail_metrics = metrics["availability_metrics"]
            print(f"\nTotal requests: {avail_metrics.get('total_requests', 0)}")
            print(f"Cache hits: {avail_metrics.get('hits', 0)}")
            print(f"Cache misses: {avail_metrics.get('misses', 0)}")
            print(f"Hit rate: {avail_metrics.get('hit_rate', '0%')}")

            # Verify expected metrics
            expected_total = 20
            expected_hits = 10
            expected_misses = 10

            passed = (
                avail_metrics.get("total_requests", 0) >= expected_total
                and avail_metrics.get("hits", 0) >= expected_hits
                and avail_metrics.get("misses", 0) >= expected_misses
            )

            self.print_result("Cache metrics verification", passed)
            return passed
        else:
            print(f"{RED}No availability metrics found{RESET}")
            return False

    async def test_cache_invalidation(self):
        """Test 3: Cache Invalidation Test"""
        self.print_header("Test 3: Cache Invalidation")

        if not self.instructor_id:
            print(f"{RED}Setup failed - no instructor ID{RESET}")
            return False

        # Step 1: Request availability to populate cache
        start_date = date.today() + timedelta(days=1)  # Tomorrow
        end_date = start_date
        url = f"{API_URL}/public/instructors/{self.instructor_id}/availability"
        params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

        print("1. Populating cache with availability request...")
        response1 = await self.client.get(url, params=params)
        if response1.status_code != 200:
            print(f"{RED}Failed to get availability{RESET}")
            return False

        # Step 2: Check it's cached by making another request and checking metrics
        print("2. Verifying cache hit...")
        metrics_before = await self.client.get(f"{API_URL}/metrics/cache")
        hits_before = metrics_before.json().get("availability_hits", 0)

        await self.client.get(url, params=params)  # Should be a cache hit

        metrics_after = await self.client.get(f"{API_URL}/metrics/cache")
        hits_after = metrics_after.json().get("availability_hits", 0)

        cache_populated = hits_after > hits_before
        self.print_result("Cache populated", cache_populated)

        # Step 3: Create a booking (need to switch to student auth)
        print("3. Creating booking to trigger invalidation...")

        # Find an available slot
        availability_data = response1.json()
        available_slot = None
        if "availability_by_date" in availability_data:
            for date_str, day_data in availability_data["availability_by_date"].items():
                if day_data["available_slots"]:
                    available_slot = day_data["available_slots"][0]
                    booking_date = date_str
                    break

        if not available_slot:
            print(f"{YELLOW}No available slots found for booking test{RESET}")
            return False

        # Create booking as student
        self.client.headers["Authorization"] = f"Bearer {self.student_auth_token}"

        # First, get a service ID for this instructor
        services_response = await self.client.get(f"{API_URL}/instructors/{self.instructor_id}")
        if services_response.status_code == 200:
            instructor_data = services_response.json()
            if instructor_data.get("services"):
                service_id = instructor_data["services"][0]["id"]

                booking_data = {
                    "instructor_id": self.instructor_id,
                    "service_id": service_id,
                    "booking_date": booking_date,
                    "start_time": available_slot["start_time"],
                    "end_time": available_slot["end_time"],
                    "meeting_location": "Test Location",
                    "location_type": "public",
                }

                booking_response = await self.client.post(f"{API_URL}/bookings", json=booking_data)
                booking_created = booking_response.status_code == 200
                self.print_result("Booking created", booking_created)

                if not booking_created:
                    print(f"{YELLOW}Booking creation failed: {booking_response.text}{RESET}")

        # Step 4: Request availability again (should be cache miss due to invalidation)
        print("4. Checking cache invalidation...")

        # Switch back to public request (no auth needed)
        self.client.headers.pop("Authorization", None)

        misses_before = metrics_after.json().get("availability_misses", 0)
        await self.client.get(url, params=params)

        metrics_final = await self.client.get(f"{API_URL}/metrics/cache")
        misses_after = metrics_final.json().get("availability_misses", 0)

        cache_invalidated = misses_after > misses_before
        self.print_result("Cache invalidated", cache_invalidated)

        # Restore instructor auth for other tests
        self.client.headers["Authorization"] = f"Bearer {self.auth_token}"

        return cache_populated and cache_invalidated

    async def test_performance_benchmark(self):
        """Test 4: Performance Benchmark"""
        self.print_header("Test 4: Performance Benchmark")

        # Test parameters
        num_requests = 50
        instructor_ids = list(range(1, 11))  # Test with 10 different instructors
        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        # Test without cache (clear cache first)
        print("Clearing cache...")
        await self.client.post(f"{API_URL}/metrics/cache/reset-stats")

        # Make requests that should mostly miss cache
        print(f"\nTesting {num_requests} requests without cache...")
        no_cache_times = []

        for i in range(num_requests):
            # Use different date ranges to avoid cache hits
            test_start = start_date + timedelta(days=i % 30)
            test_end = test_start + timedelta(days=7)
            instructor_id = instructor_ids[i % len(instructor_ids)]

            url = f"{API_URL}/public/instructors/{instructor_id}/availability"
            params = {"start_date": test_start.isoformat(), "end_date": test_end.isoformat()}

            start_time = time.time()
            response = await self.client.get(url, params=params)
            end_time = time.time()

            if response.status_code == 200:
                no_cache_times.append((end_time - start_time) * 1000)

        # Now test with cache (make same requests twice)
        print("\nWarming cache...")
        # First round to populate cache
        for i in range(num_requests):
            instructor_id = instructor_ids[i % len(instructor_ids)]
            url = f"{API_URL}/public/instructors/{instructor_id}/availability"
            params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
            await self.client.get(url, params=params)

        print(f"Testing {num_requests} requests with cache...")
        cache_times = []

        # Second round should hit cache
        for i in range(num_requests):
            instructor_id = instructor_ids[i % len(instructor_ids)]
            url = f"{API_URL}/public/instructors/{instructor_id}/availability"
            params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

            start_time = time.time()
            response = await self.client.get(url, params=params)
            end_time = time.time()

            if response.status_code == 200:
                cache_times.append((end_time - start_time) * 1000)

        # Calculate statistics
        avg_no_cache = sum(no_cache_times) / len(no_cache_times) if no_cache_times else 0
        avg_cache = sum(cache_times) / len(cache_times) if cache_times else 0

        improvement_pct = ((avg_no_cache - avg_cache) / avg_no_cache * 100) if avg_no_cache > 0 else 0
        req_per_sec_no_cache = 1000 / avg_no_cache if avg_no_cache > 0 else 0
        req_per_sec_cache = 1000 / avg_cache if avg_cache > 0 else 0
        improvement_factor = req_per_sec_cache / req_per_sec_no_cache if req_per_sec_no_cache > 0 else 0

        print(f"\nWithout cache: {avg_no_cache:.1f}ms average ({req_per_sec_no_cache:.1f} req/s)")
        print(f"With cache: {avg_cache:.1f}ms average ({req_per_sec_cache:.1f} req/s)")
        print(f"Improvement: {improvement_pct:.1f}% faster, {improvement_factor:.1f}x more req/s")

        passed = improvement_pct > 50  # Expect at least 50% improvement
        self.print_result("Performance benchmark", passed)

        return passed

    async def test_etag_caching(self):
        """Test 5: ETag Browser Cache Test"""
        self.print_header("Test 5: ETag Test")

        if not self.instructor_id:
            print(f"{RED}Setup failed - no instructor ID{RESET}")
            return False

        # Make initial request and capture ETag
        start_date = date.today()
        end_date = start_date + timedelta(days=7)
        url = f"{API_URL}/public/instructors/{self.instructor_id}/availability"
        params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

        print("1. Making initial request to get ETag...")
        response1 = await self.client.get(url, params=params)

        if response1.status_code != 200:
            print(f"{RED}Initial request failed{RESET}")
            return False

        etag = response1.headers.get("etag")
        etag_present = etag is not None
        self.print_result("ETag header present", etag_present)

        if not etag_present:
            print(f"{YELLOW}No ETag header found: {dict(response1.headers)}{RESET}")
            return False

        print(f"ETag received: {etag}")

        # Make request with If-None-Match header
        print("\n2. Making request with If-None-Match header...")
        headers = {"If-None-Match": etag}
        response2 = await self.client.get(url, params=params, headers=headers)

        not_modified = response2.status_code == 304
        self.print_result("304 response with If-None-Match", not_modified)

        # Check no body content
        no_body = len(response2.content) == 0
        self.print_result("No body content in 304 response", no_body)

        return etag_present and not_modified and no_body

    async def check_redis_status(self):
        """Additional check: Redis status and memory usage"""
        self.print_header("Additional Checks")

        # Get cache metrics including Redis info
        metrics_response = await self.client.get(f"{API_URL}/metrics/cache")
        if metrics_response.status_code != 200:
            print(f"{YELLOW}Could not retrieve cache metrics{RESET}")
            return

        metrics = metrics_response.json()

        # Check Redis info
        if "redis_info" in metrics:
            redis_info = metrics["redis_info"]
            print(f"Redis memory usage: {redis_info.get('used_memory_human', 'Unknown')}")
            print(f"Keyspace hits: {redis_info.get('keyspace_hits', 0)}")
            print(f"Keyspace misses: {redis_info.get('keyspace_misses', 0)}")
            print(f"Evicted keys: {redis_info.get('evicted_keys', 0)}")
        else:
            print(f"{YELLOW}Redis info not available{RESET}")

        # Get availability-specific metrics
        availability_response = await self.client.get(f"{API_URL}/metrics/cache/availability")
        if availability_response.status_code == 200:
            avail_data = availability_response.json()

            print("\nCached keys sample:")
            for key in avail_data.get("top_cached_keys_sample", [])[:5]:
                print(f"  - {key}")

            print("\nRecommendations:")
            for rec in avail_data.get("recommendations", []):
                print(f"  - {rec}")

    async def run_all_tests(self):
        """Run all tests and generate report."""
        print(f"\n{BLUE}=== Availability Cache Performance Test Results ==={RESET}")

        results = {
            "basic_cache": False,
            "cache_metrics": False,
            "invalidation": False,
            "performance": False,
            "etag": False,
        }

        try:
            # Run all tests
            results["basic_cache"] = await self.test_basic_cache_functionality()
            results["cache_metrics"] = await self.test_cache_metrics()
            results["invalidation"] = await self.test_cache_invalidation()
            results["performance"] = await self.test_performance_benchmark()
            results["etag"] = await self.test_etag_caching()

            # Additional checks
            await self.check_redis_status()

            # Summary
            self.print_header("Test Summary")

            total_tests = len(results)
            passed_tests = sum(1 for passed in results.values() if passed)

            print(f"Tests passed: {passed_tests}/{total_tests}")

            if passed_tests == total_tests:
                print(f"\n{GREEN}Overall: PASSED - Caching system working as expected{RESET}")
            else:
                print(f"\n{RED}Overall: FAILED - Some tests did not pass{RESET}")

            # Print failed tests
            failed = [name for name, passed in results.items() if not passed]
            if failed:
                print(f"\nFailed tests: {', '.join(failed)}")

        except Exception as e:
            print(f"\n{RED}Error during testing: {str(e)}{RESET}")
            import traceback

            traceback.print_exc()


async def main():
    """Main entry point."""
    async with CachePerformanceTester() as tester:
        await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
