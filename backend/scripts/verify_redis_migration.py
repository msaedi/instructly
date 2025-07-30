#!/usr/bin/env python3
"""
Verify Redis migration deployment.

This script checks that the Redis migration was successful by:
1. Testing Redis connectivity
2. Checking Celery queue status
3. Verifying Redis operation counts
4. Ensuring all services are connected

Usage:
    python scripts/verify_redis_migration.py [--api-url https://api.instainstru.com]
"""

import argparse
import sys
import time
from typing import Any, Dict

import requests


class RedisVerification:
    """Verify Redis migration was successful."""

    def __init__(self, api_url: str, auth_token: str = None):
        self.api_url = api_url.rstrip("/")
        self.headers = {}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"
        self.results = []

    def check_health(self) -> bool:
        """Check basic Redis health."""
        print("\n🔍 Checking Redis Health...")
        try:
            response = requests.get(f"{self.api_url}/api/redis/health", headers=self.headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy" and data.get("connected"):
                    print("✅ Redis is healthy and connected")
                    return True
                else:
                    print(f"❌ Redis unhealthy: {data}")
                    return False
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False

    def check_stats(self) -> Dict[str, Any]:
        """Check Redis statistics (requires admin auth)."""
        print("\n📊 Checking Redis Statistics...")
        try:
            response = requests.get(f"{self.api_url}/api/redis/stats", headers=self.headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Redis Stats Retrieved:")
                print(f"   - Version: {data['server']['redis_version']}")
                print(f"   - Memory Used: {data['memory']['used_memory_human']}")
                print(f"   - Connected Clients: {data['clients']['connected_clients']}")
                print(f"   - Current Ops/sec: {data['operations']['current_ops_per_sec']}")
                print(f"   - Estimated Daily Ops: {data['operations']['estimated_daily_ops']:,}")

                # Check if operations are within expected range
                daily_ops = data["operations"]["estimated_daily_ops"]
                if daily_ops < 100000:  # Less than 100K ops/day is good
                    print(f"   ✅ Operation count is optimized ({daily_ops:,} < 100,000)")
                else:
                    print(f"   ⚠️  Operation count seems high ({daily_ops:,} > 100,000)")

                return data
            elif response.status_code == 401:
                print("⚠️  Stats endpoint requires admin authentication")
                return {}
            else:
                print(f"❌ Stats check failed: {response.status_code}")
                return {}

        except Exception as e:
            print(f"❌ Stats check error: {e}")
            return {}

    def check_celery_queues(self) -> Dict[str, int]:
        """Check Celery queue status."""
        print("\n📬 Checking Celery Queues...")
        try:
            response = requests.get(f"{self.api_url}/api/redis/celery-queues", headers=self.headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                queues = data.get("queues", {})
                total = data.get("total_pending", 0)

                print(f"✅ Celery Queues Status:")
                if not queues or all(v == 0 for v in queues.values() if v >= 0):
                    print("   - All queues are empty (expected for fresh deployment)")
                else:
                    for queue, length in queues.items():
                        if length > 0:
                            print(f"   - {queue}: {length} pending tasks")

                print(f"   - Total pending tasks: {total}")
                return queues

            elif response.status_code == 401:
                print("⚠️  Queue status requires admin authentication")
                return {}
            else:
                print(f"❌ Queue check failed: {response.status_code}")
                return {}

        except Exception as e:
            print(f"❌ Queue check error: {e}")
            return {}

    def verify_services(self) -> bool:
        """Verify all services are running."""
        print("\n🔧 Verifying Service Connectivity...")

        # Check main API
        try:
            response = requests.get(f"{self.api_url}/health", timeout=10)
            if response.status_code == 200:
                print("✅ Main API is responding")
            else:
                print(f"❌ Main API returned: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Main API error: {e}")
            return False

        # Check if Flower is accessible (if configured)
        # Note: Flower URL would be different, this is just an example
        print("ℹ️  Note: Check Flower dashboard manually for Celery worker status")

        return True

    def run_verification(self) -> bool:
        """Run all verification checks."""
        print(f"\n🚀 Redis Migration Verification")
        print(f"   API URL: {self.api_url}")
        print("=" * 50)

        # Run checks
        health_ok = self.check_health()
        stats = self.check_stats()
        self.check_celery_queues()
        services_ok = self.verify_services()

        # Summary
        print("\n" + "=" * 50)
        print("📋 VERIFICATION SUMMARY:")

        if health_ok and services_ok:
            print("✅ Redis migration appears successful!")

            # Check operation count if we have stats
            if stats and "operations" in stats:
                daily_ops = stats["operations"]["estimated_daily_ops"]
                if daily_ops < 100000:
                    print(f"✅ Redis operations optimized (~{daily_ops:,}/day)")
                else:
                    print(f"⚠️  Redis operations may need further optimization ({daily_ops:,}/day)")

            return True
        else:
            print("❌ Redis migration verification failed")
            print("\nTroubleshooting steps:")
            print("1. Check Redis service is running on Render")
            print("2. Verify all services have REDIS_URL set to redis://instainstru-redis:6379")
            print("3. Check Celery worker and beat are running")
            print("4. Review service logs for connection errors")

            return False


def main():
    """Main verification script."""
    parser = argparse.ArgumentParser(description="Verify Redis migration deployment")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="API URL to verify (default: http://localhost:8000)"
    )
    parser.add_argument("--auth-token", help="Admin auth token for detailed stats (optional)")
    parser.add_argument(
        "--wait", type=int, default=0, help="Wait N seconds before verification (for deployment warmup)"
    )

    args = parser.parse_args()

    if args.wait > 0:
        print(f"⏳ Waiting {args.wait} seconds for services to warm up...")
        time.sleep(args.wait)

    verifier = RedisVerification(args.api_url, args.auth_token)
    success = verifier.run_verification()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
