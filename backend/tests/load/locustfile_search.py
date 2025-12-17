"""
Load test for Search & Discovery flow (unauthenticated).
Simulates users searching for instructors and viewing profiles.

This tests the core unauthenticated user journey - the highest traffic flow
that doesn't require login. This is the first impression and must be fast.

User Journey Simulated:
1. Load homepage (services catalog)
2. Click category pill OR type natural language search
3. View search results
4. Click on instructor profile (from search results)
5. View availability calendar
6. (Optional) View reviews

Design: Instructor IDs are dynamically extracted from search results, not
hardcoded. This ensures tests work regardless of database state/seeding.

Usage:
    cd backend/tests/load
    locust -f locustfile_search.py --headless \
        --host=https://preview-api.instainstru.com \
        -u 100 -r 10 -t 3m
"""

from datetime import date, timedelta
import logging
import os
import random
from typing import List, Set

from locust import HttpUser, between, events, tag, task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Sample search queries (realistic user searches) - these will hit cache
CACHED_QUERIES = [
    "piano lessons",
    "guitar teacher near me",
    "math tutor",
    "spanish lessons",
    "yoga instructor",
    "swimming coach",
    "violin lessons for beginners",
    "SAT prep tutor",
    "tennis lessons",
    "photography classes",
    "drums",
    "voice lessons",
    "chess teacher",
    "coding tutor",
    "art classes",
]

# Components for generating unique uncached queries
SERVICES = ["piano", "guitar", "violin", "drums", "voice", "yoga", "tennis", "swimming"]
LOCATIONS = ["ues", "brooklyn", "manhattan", "queens", "harlem", "soho", "tribeca", "astoria"]
AUDIENCES = ["kids", "adults", "beginners", "advanced", "teens", "seniors"]
TIME_CONSTRAINTS = ["tomorrow", "this weekend", "next week", "evenings", "mornings"]
PRICE_CONSTRAINTS = ["under $50", "under $75", "under $100", "under $150"]

CATEGORIES = [
    "music",
    "tutoring",
    "sports-fitness",
    "language",
    "arts",
    "technology",
    "lifestyle",
]


def generate_unique_query() -> str:
    """Generate a truly unique query that won't be cached (includes random suffix)."""
    import time as time_module

    service = random.choice(SERVICES)
    pattern = random.randint(1, 4)
    # Add unique suffix to guarantee cache miss
    suffix = f"{int(time_module.time() * 1000) % 100000}{random.randint(0, 999)}"

    if pattern == 1:
        # Service + location: "piano in brooklyn"
        location = random.choice(LOCATIONS)
        return f"{service} in {location} {suffix}"
    elif pattern == 2:
        # Service + audience: "guitar for kids"
        audience = random.choice(AUDIENCES)
        return f"{service} for {audience} {suffix}"
    elif pattern == 3:
        # Service + time: "yoga tomorrow"
        time_val = random.choice(TIME_CONSTRAINTS)
        return f"{service} {time_val} {suffix}"
    else:
        # Service + location + audience: "violin in manhattan for beginners"
        location = random.choice(LOCATIONS)
        audience = random.choice(AUDIENCES)
        return f"{service} in {location} for {audience} {suffix}"

# Shared pool of discovered instructor IDs (populated from search results)
# This is thread-safe because locust uses gevent greenlets
discovered_instructor_ids: Set[str] = set()


class Config:
    """Load test configuration loaded from environment variables."""

    BASE_URL: str = os.getenv("LOADTEST_BASE_URL", "https://preview-api.instainstru.com")
    FRONTEND_ORIGIN: str = os.getenv(
        "LOADTEST_FRONTEND_ORIGIN", "https://preview.instainstru.com"
    )
    RATE_LIMIT_BYPASS_TOKEN: str = os.getenv("LOADTEST_BYPASS_TOKEN", "")


def extract_instructor_ids(data: dict | list) -> List[str]:
    """Extract instructor IDs from search response data."""
    ids: List[str] = []

    # Handle different response structures
    items = []
    if isinstance(data, dict):
        items = data.get("items", []) or data.get("results", []) or []
    elif isinstance(data, list):
        items = data

    for item in items:
        if isinstance(item, dict):
            # Try common ID field names
            for key in ["instructor_id", "id", "user_id"]:
                if key in item and item[key]:
                    ids.append(str(item[key]))
                    break

    return ids


def get_random_instructor_id() -> str | None:
    """Get a random instructor ID from the discovered pool."""
    if discovered_instructor_ids:
        return random.choice(list(discovered_instructor_ids))
    return None


class SearchDiscoveryUser(HttpUser):
    """Simulates unauthenticated user browsing for instructors."""

    host = Config.BASE_URL
    wait_time = between(1, 3)  # 1-3 seconds between actions
    weight = 10  # Higher weight than aggressive user

    def on_start(self) -> None:
        """Set up headers for all requests."""
        headers = {
            "Origin": Config.FRONTEND_ORIGIN,
            "Referer": f"{Config.FRONTEND_ORIGIN}/",
            "Content-Type": "application/json",
        }
        if Config.RATE_LIMIT_BYPASS_TOKEN:
            headers["X-Rate-Limit-Bypass"] = Config.RATE_LIMIT_BYPASS_TOKEN
        self.client.headers.update(headers)

    @tag("homepage")
    @task(3)  # Higher weight - most users start here
    def load_homepage(self) -> None:
        """Load the homepage (service categories)."""
        with self.client.get(
            "/api/v1/services/categories", name="homepage_categories", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @tag("search")
    @task(7)  # 70% - cached queries (repeat searches)
    def search_cached(self) -> None:
        """Search using cached query (simulates repeat/common searches)."""
        query = random.choice(CACHED_QUERIES)
        with self.client.get(
            f"/api/v1/search?q={query}",
            name="search_cached",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "items" in data or "results" in data or isinstance(data, list):
                        ids = extract_instructor_ids(data)
                        if ids:
                            discovered_instructor_ids.update(ids)
                        response.success()
                    else:
                        response.failure("Missing results in response")
                except Exception as e:
                    response.failure(f"JSON parse error: {e}")
            else:
                response.failure(f"Status {response.status_code}")

    @tag("search")
    @task(3)  # 30% - unique queries (cache misses)
    def search_uncached(self) -> None:
        """Search using unique query (guaranteed cache miss)."""
        query = generate_unique_query()
        with self.client.get(
            f"/api/v1/search?q={query}",
            name="search_uncached",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "items" in data or "results" in data or isinstance(data, list):
                        ids = extract_instructor_ids(data)
                        if ids:
                            discovered_instructor_ids.update(ids)
                        response.success()
                    else:
                        response.failure("Missing results in response")
                except Exception as e:
                    response.failure(f"JSON parse error: {e}")
            else:
                response.failure(f"Status {response.status_code}")

    @tag("search")
    @task(3)
    def category_search(self) -> None:
        """Search by category name and extract instructor IDs."""
        # Use category names as search queries (the API requires q param)
        category_queries = ["music lessons", "tutoring", "fitness", "art classes", "language"]
        query = random.choice(category_queries)
        with self.client.get(
            f"/api/v1/search?q={query}",
            name="search_category",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    # Extract and cache instructor IDs
                    ids = extract_instructor_ids(data)
                    if ids:
                        discovered_instructor_ids.update(ids)
                    response.success()
                except Exception:
                    response.success()  # Still count as success even if parsing fails
            else:
                response.failure(f"Status {response.status_code}")

    @tag("profile")
    @task(4)  # High weight - users view profiles
    def view_instructor_profile(self) -> None:
        """View an instructor's profile page (from search results)."""
        instructor_id = get_random_instructor_id()
        if not instructor_id:
            # No instructors discovered yet - skip this task
            return

        with self.client.get(
            f"/api/v1/instructors/{instructor_id}",
            name="instructor_profile",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Remove stale ID from pool
                discovered_instructor_ids.discard(instructor_id)
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @tag("profile")
    @task(3)
    def view_instructor_ratings(self) -> None:
        """View instructor's ratings/reviews."""
        instructor_id = get_random_instructor_id()
        if not instructor_id:
            return

        with self.client.get(
            f"/api/v1/reviews/instructor/{instructor_id}/ratings",
            name="instructor_ratings",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.success()  # Instructor may not have reviews
            else:
                response.failure(f"Status {response.status_code}")

    @tag("availability")
    @task(3)
    def view_availability(self) -> None:
        """View instructor's availability calendar."""
        instructor_id = get_random_instructor_id()
        if not instructor_id:
            return

        # Availability endpoint requires date range parameters
        start_date = date.today().isoformat()
        end_date = (date.today() + timedelta(days=7)).isoformat()
        with self.client.get(
            f"/api/v1/public/instructors/{instructor_id}/availability?start_date={start_date}&end_date={end_date}",
            name="instructor_availability",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.success()  # Instructor may not exist
            else:
                response.failure(f"Status {response.status_code}")


# Event listeners for test lifecycle logging
@events.test_start.add_listener
def on_test_start(**_kwargs) -> None:
    """Log test configuration when starting."""
    logger.info("=" * 60)
    logger.info("Search & Discovery Load Test Starting")
    logger.info(f"  API Base URL: {Config.BASE_URL}")
    logger.info(f"  Frontend Origin: {Config.FRONTEND_ORIGIN}")
    logger.info(f"  Cached queries: {len(CACHED_QUERIES)} (70% of searches)")
    logger.info("  Uncached queries: Generated dynamically (30% of searches)")
    logger.info("  Instructor IDs: Dynamic (extracted from search results)")
    bypass_status = "ENABLED" if Config.RATE_LIMIT_BYPASS_TOKEN else "disabled"
    logger.info(f"  Rate limit bypass: {bypass_status}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(**_kwargs) -> None:
    """Log summary when test stops."""
    logger.info("=" * 60)
    logger.info("Search & Discovery Load Test Complete")
    logger.info(f"  Discovered {len(discovered_instructor_ids)} unique instructor IDs")
    logger.info("=" * 60)
