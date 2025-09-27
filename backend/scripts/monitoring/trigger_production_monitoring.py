#!/usr/bin/env python3
"""
Trigger production monitoring to create alerts.

This script makes requests to the production API that should trigger
the monitoring system to create alerts.
"""

from datetime import datetime, timezone
import time

import httpx

PRODUCTION_URL = "https://api.instainstru.com"


def trigger_slow_requests():
    """Make requests designed to be slow and trigger monitoring alerts."""
    print("=== Triggering Slow Request Monitoring ===")
    print(f"Target: {PRODUCTION_URL}")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("\nNote: Production monitoring triggers alerts for:")
    print("- Slow queries (>100ms)")
    print("- Slow requests (>500ms)")
    print("- Extremely slow requests (>5s)")
    print()

    # Create a session for connection reuse
    with httpx.Client(timeout=30.0) as client:
        # 1. Try to trigger slow query with complex operations
        print("1. Making complex availability requests...")
        for i in range(1, 4):
            try:
                # Request a full year of availability (heavy query)
                response = client.get(
                    f"{PRODUCTION_URL}/api/public/instructors/{i}/availability",
                    params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
                )
                elapsed = response.elapsed.total_seconds()
                print(f"   Instructor {i} (full year): {response.status_code} in {elapsed:.2f}s")

                # If it was slow, it might trigger an alert
                if elapsed > 0.5:
                    print(f"     → Slow request detected ({elapsed:.2f}s > 0.5s)")

            except Exception as e:
                print(f"   Instructor {i}: Error - {str(e)}")

        # 2. Try catalog endpoint with heavy filters
        print("\n2. Making heavy catalog requests...")
        try:
            response = client.get(
                f"{PRODUCTION_URL}/services/catalog", params={"limit": 1000, "offset": 0}  # Large limit
            )
            elapsed = response.elapsed.total_seconds()
            print(f"   Large catalog request: {response.status_code} in {elapsed:.2f}s")

            if elapsed > 0.5:
                print(f"     → Slow request detected ({elapsed:.2f}s > 0.5s)")

        except Exception as e:
            print(f"   Catalog error: {str(e)}")

        # 3. Make concurrent requests to stress the system
        print("\n3. Making concurrent requests...")
        import concurrent.futures

        def make_request(endpoint):
            try:
                start = time.time()
                response = client.get(f"{PRODUCTION_URL}{endpoint}")
                elapsed = time.time() - start
                return f"{endpoint}: {response.status_code} in {elapsed:.2f}s"
            except Exception as e:
                return f"{endpoint}: Error - {str(e)}"

        endpoints = [
            "/health",
            "/services/catalog",
            "/api/public/instructors/01J5TESTINSTR0000000000001/availability?start_date=2025-01-25&end_date=2025-02-01",
            "/api/public/instructors/01J5TESTINSTR0000000000002/availability?start_date=2025-01-25&end_date=2025-02-01",
            "/api/public/instructors/01J5TESTINSTR0000000000003/availability?start_date=2025-01-25&end_date=2025-02-01",
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, ep) for ep in endpoints]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                print(f"   {result}")

        # 4. Try to make a request that times out (extremely slow)
        print("\n4. Making potentially very slow request...")
        try:
            # Multiple heavy operations in parallel
            very_slow_start = time.time()
            responses = []

            # Make 10 heavy requests rapidly
            for i in range(10):
                response = client.get(
                    f"{PRODUCTION_URL}/api/public/instructors/{i+1}/availability",
                    params={"start_date": "2020-01-01", "end_date": "2025-12-31"},  # 5+ years of data
                )
                responses.append(response)

            total_elapsed = time.time() - very_slow_start
            print(f"   Batch of 10 heavy requests completed in {total_elapsed:.2f}s")

            if total_elapsed > 5.0:
                print(f"     → EXTREMELY slow batch detected ({total_elapsed:.2f}s > 5s)!")

        except Exception as e:
            print(f"   Very slow request error: {str(e)}")


def main():
    """Run the monitoring trigger."""
    print("=== Production Monitoring Trigger ===")
    print("This script makes requests to production that should trigger monitoring alerts.")
    print("Alerts are created when the production monitoring detects slow operations.\n")

    trigger_slow_requests()

    print("\n=== Summary ===")
    print("Requests have been made to the production API.")
    print("\nIf any were slow enough, the monitoring system should create alerts:")
    print("- Slow requests (>500ms) → warning alerts")
    print("- Extremely slow requests (>5s) → critical alerts")
    print("\nThe Celery workers on Render will process these and save to Supabase.")
    print("\nWait a few minutes, then check with:")
    print("  python scripts/check_production_monitoring.py")


if __name__ == "__main__":
    main()
