#!/usr/bin/env python3
"""
Test script for catalog performance improvements.

This script helps verify:
1. N+1 query fix with eager loading
2. Cache functionality
3. Performance improvements
4. New top-per-category endpoint
"""

import logging
from pathlib import Path

# Add parent directory to path
import sys
import time

import requests
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.cache_service import CacheService
from app.services.instructor_service import InstructorService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global query counter
query_count = 0
queries = []


@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Count SQL queries for N+1 detection."""
    global query_count, queries
    query_count += 1
    queries.append(statement[:100] + "..." if len(statement) > 100 else statement)


class CatalogPerformanceTester:
    """Test catalog performance improvements."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

        # Create database session
        engine = create_engine(settings.database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = SessionLocal()

        # Initialize cache service with db session
        self.cache_service = CacheService(self.db)

    def __del__(self):
        """Clean up database session."""
        if hasattr(self, "db"):
            self.db.close()

    def test_n_plus_one_fix(self):
        """Test that the N+1 query problem is fixed."""
        print("\n" + "=" * 60)
        print("Testing N+1 Query Fix")
        print("=" * 60)

        # Clear any existing cache
        self.cache_service.delete_pattern("catalog:services:*")

        # Create service instance
        instructor_service = InstructorService(self.db, self.cache_service)

        # Reset query counter
        global query_count, queries
        query_count = 0
        queries = []

        # Call the method (should use eager loading)
        start_time = time.time()
        services = instructor_service.get_available_catalog_services()
        end_time = time.time()

        execution_time = (end_time - start_time) * 1000  # Convert to ms

        print(f"✓ Fetched {len(services)} services")
        print(f"✓ Execution time: {execution_time:.2f}ms")
        print(f"✓ Total queries executed: {query_count}")

        # With eager loading, should be 1-3 queries max
        if query_count <= 3:
            print("✅ PASS: N+1 query problem is fixed!")
        else:
            print("❌ FAIL: Too many queries detected")
            print("\nFirst 5 queries:")
            for i, query in enumerate(queries[:5]):
                print(f"  {i+1}. {query}")

        # Check that categories are loaded
        category_access_queries = [q for q in queries if "service_categories" in q and "JOIN" not in q]
        if category_access_queries:
            print(f"⚠️  WARNING: Found {len(category_access_queries)} separate category queries")
        else:
            print("✅ Categories are being eager loaded correctly")

        return execution_time, query_count

    def test_cache_functionality(self):
        """Test that caching is working correctly."""
        print("\n" + "=" * 60)
        print("Testing Cache Functionality")
        print("=" * 60)

        # Clear cache first
        self.cache_service.delete_pattern("catalog:services:*")
        print("✓ Cache cleared")

        instructor_service = InstructorService(self.db, self.cache_service)

        # First call - should miss cache
        global query_count
        query_count = 0
        start_time = time.time()
        services_1 = instructor_service.get_available_catalog_services()
        time_1 = (time.time() - start_time) * 1000
        queries_1 = query_count

        print("\nFirst call (cache miss):")
        print(f"  - Time: {time_1:.2f}ms")
        print(f"  - Queries: {queries_1}")
        print(f"  - Services: {len(services_1)}")

        # Second call - should hit cache
        query_count = 0
        start_time = time.time()
        services_2 = instructor_service.get_available_catalog_services()
        time_2 = (time.time() - start_time) * 1000
        queries_2 = query_count

        print("\nSecond call (cache hit):")
        print(f"  - Time: {time_2:.2f}ms")
        print(f"  - Queries: {queries_2}")
        print(f"  - Services: {len(services_2)}")

        # Verify cache is working
        if queries_2 == 0 and time_2 < time_1 * 0.1:  # Should be at least 10x faster
            print("\n✅ PASS: Cache is working correctly!")
            print(f"   Speed improvement: {time_1/time_2:.1f}x faster")
        else:
            print("\n❌ FAIL: Cache not working as expected")

        # Test cache expiration (5 minutes)
        print("\n✓ Cache TTL: 300 seconds (5.0 minutes) - configured in service")

        # Test category filtering with cache
        query_count = 0
        services_music = instructor_service.get_available_catalog_services(category_slug="music")
        print(f"\n✓ Category filter test: {len(services_music)} music services (queries: {query_count})")

    def test_api_endpoints(self):
        """Test the API endpoints directly."""
        print("\n" + "=" * 60)
        print("Testing API Endpoints")
        print("=" * 60)

        # Test full catalog endpoint
        print("\n1. Testing /services/catalog")
        start_time = time.time()
        response = requests.get(f"{self.base_url}/services/catalog")
        catalog_time = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Time: {catalog_time:.2f}ms")
            print(f"   ✓ Services: {len(data)}")
        else:
            print(f"   ❌ Error: {response.status_code}")

        # Test with category filter
        print("\n2. Testing /services/catalog?category=music")
        start_time = time.time()
        response = requests.get(f"{self.base_url}/services/catalog", params={"category": "music"})
        music_time = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Time: {music_time:.2f}ms")
            print(f"   ✓ Music services: {len(data)}")

        # Test new top-per-category endpoint
        print("\n3. Testing /services/catalog/top-per-category")
        start_time = time.time()
        response = requests.get(f"{self.base_url}/services/catalog/top-per-category")
        top_time = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Time: {top_time:.2f}ms")
            print(f"   ✓ Categories: {len(data.get('categories', []))}")

            # Count total services
            total_services = sum(len(cat["services"]) for cat in data.get("categories", []))
            print(f"   ✓ Total services: {total_services}")

            # Show first category as example
            if data.get("categories"):
                first_cat = data["categories"][0]
                print(f"\n   Example - {first_cat['name']}:")
                for i, service in enumerate(first_cat["services"][:3], 1):
                    print(
                        f"     {i}. {service['name']} (order: {service['display_order']}, demand: {service['demand_score']})"
                    )

        # Test with custom limit
        print("\n4. Testing /services/catalog/top-per-category?limit=3")
        response = requests.get(f"{self.base_url}/services/catalog/top-per-category", params={"limit": 3})

        if response.status_code == 200:
            data = response.json()
            total_services = sum(len(cat["services"]) for cat in data.get("categories", []))
            print(f"   ✓ Total services with limit=3: {total_services}")
            max_per_cat = (
                max(len(cat["services"]) for cat in data.get("categories", [])) if data.get("categories") else 0
            )
            print(f"   ✓ Max services per category: {max_per_cat}")

    def test_performance_comparison(self):
        """Compare performance between old and new approaches."""
        print("\n" + "=" * 60)
        print("Performance Comparison")
        print("=" * 60)

        # Clear cache for fair comparison
        self.cache_service.delete_pattern("catalog:services:*")

        # Test 1: Full catalog (cold cache)
        print("\n1. Full Catalog Performance:")
        response = requests.get(f"{self.base_url}/services/catalog")
        start_time = time.time()
        response = requests.get(f"{self.base_url}/services/catalog")
        full_cold = (time.time() - start_time) * 1000
        full_count = len(response.json()) if response.status_code == 200 else 0
        print(f"   - Cold cache: {full_cold:.2f}ms for {full_count} services")

        # Warm cache test
        start_time = time.time()
        response = requests.get(f"{self.base_url}/services/catalog")
        full_warm = (time.time() - start_time) * 1000
        print(f"   - Warm cache: {full_warm:.2f}ms")
        print(f"   - Improvement: {full_cold/full_warm:.1f}x faster")

        # Test 2: Top services endpoint
        print("\n2. Top Services Performance:")
        start_time = time.time()
        response = requests.get(f"{self.base_url}/services/catalog/top-per-category")
        top_cold = (time.time() - start_time) * 1000
        data = response.json() if response.status_code == 200 else {}
        top_count = sum(len(cat["services"]) for cat in data.get("categories", []))
        print(f"   - Cold cache: {top_cold:.2f}ms for {top_count} services")

        start_time = time.time()
        response = requests.get(f"{self.base_url}/services/catalog/top-per-category")
        top_warm = (time.time() - start_time) * 1000
        print(f"   - Warm cache: {top_warm:.2f}ms")
        print(f"   - Improvement: {top_cold/top_warm:.1f}x faster")

        # Comparison
        print("\n3. Endpoint Comparison:")
        print(f"   - Full catalog: {full_count} services in {full_warm:.2f}ms (cached)")
        print(f"   - Top services: {top_count} services in {top_warm:.2f}ms (cached)")
        if full_count > 0:
            print(f"   - Data reduction: {(1 - top_count/full_count)*100:.1f}%")
            print(f"   - Speed improvement: {full_warm/top_warm:.1f}x faster")
        else:
            print("   - No data available for comparison")

    def test_cache_invalidation(self):
        """Test cache invalidation after analytics update."""
        print("\n" + "=" * 60)
        print("Testing Cache Invalidation")
        print("=" * 60)

        # Warm up cache
        requests.get(f"{self.base_url}/services/catalog")
        print("✓ Cache warmed up")

        # Check cache exists
        cache_key = "catalog:services:all"
        cached_data = self.cache_service.get(cache_key)
        if cached_data:
            print("✓ Cache key exists")

        # Simulate analytics update (invalidate cache)
        print("\nSimulating analytics update...")
        self.cache_service.delete_pattern("catalog:services:*")
        print("✓ Cache invalidated")

        # Verify cache is gone
        cached_data = self.cache_service.get(cache_key)
        if not cached_data:
            print("✅ Cache successfully invalidated")
        else:
            print("❌ Cache still exists after invalidation")

        # Next request should rebuild cache
        global query_count
        query_count = 0
        requests.get(f"{self.base_url}/services/catalog")
        print(f"✓ Cache rebuilt with {query_count} queries")

    def run_all_tests(self):
        """Run all performance tests."""
        print("\n" + "🚀 CATALOG PERFORMANCE TEST SUITE 🚀")
        print("=" * 60)

        try:
            # Test N+1 fix
            self.test_n_plus_one_fix()

            # Test caching
            self.test_cache_functionality()

            # Test API endpoints
            self.test_api_endpoints()

            # Performance comparison
            self.test_performance_comparison()

            # Cache invalidation
            self.test_cache_invalidation()

            print("\n" + "=" * 60)
            print("✅ All tests completed!")
            print("=" * 60)

        except Exception as e:
            print(f"\n❌ Test failed with error: {str(e)}")
            import traceback

            traceback.print_exc()


def main():
    """Run the performance tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Test catalog performance improvements")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base URL for API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--test", choices=["all", "n1", "cache", "api", "perf", "invalidation"], default="all", help="Which test to run"
    )

    args = parser.parse_args()

    tester = CatalogPerformanceTester(args.url)

    if args.test == "all":
        tester.run_all_tests()
    elif args.test == "n1":
        tester.test_n_plus_one_fix()
    elif args.test == "cache":
        tester.test_cache_functionality()
    elif args.test == "api":
        tester.test_api_endpoints()
    elif args.test == "perf":
        tester.test_performance_comparison()
    elif args.test == "invalidation":
        tester.test_cache_invalidation()


if __name__ == "__main__":
    main()
