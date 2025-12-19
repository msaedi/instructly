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

NL Search Tier Coverage:
- Tier 1-2: Exact/fuzzy ZIP/neighborhood match (50% of weighted searches)
- Tier 3: Multi-region/borough-level queries (20%)
- Tier 4: Embedding-based similarity (15%)
- Tier 5: LLM-based landmark resolution (15%)

Design: Instructor IDs are dynamically extracted from search results, not
hardcoded. This ensures tests work regardless of database state/seeding.

Usage:
    cd backend/tests/load
    locust -f locustfile_search.py --headless \
        --host=https://preview-api.instainstru.com \
        -u 100 -r 10 -t 3m
"""

from collections import defaultdict
from datetime import date, timedelta
import logging
import os
import random
import time as time_module
from typing import Dict, List, Set, Tuple

from locust import HttpUser, between, events, tag, task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# NL SEARCH TIER-SPECIFIC QUERY POOLS
# =============================================================================
#
# Tier 1-2: Exact ZIP or neighborhood match (fastest, <20ms typical)
# These queries resolve immediately via exact or fuzzy text match
TIER_1_2_QUERIES = [
    # ZIP codes - exact match
    "10001",
    "10016",
    "10019",
    "10021",
    "10028",
    "11201",
    "11215",
    "11217",
    # Common neighborhoods - fuzzy match
    "upper east side",
    "upper west side",
    "chelsea",
    "midtown",
    "tribeca",
    "soho",
    "williamsburg",
    "park slope",
    "astoria",
    "harlem",
    "greenwich village",
    "east village",
    "west village",
    "murray hill",
    "gramercy",
]

# Tier 3: Multi-region or borough-level queries (moderate, 20-50ms typical)
# These require looking up multiple regions or broader geographic areas
TIER_3_QUERIES = [
    "manhattan",
    "brooklyn",
    "queens",
    "bronx",
    "downtown manhattan",
    "uptown manhattan",
    "north brooklyn",
    "south brooklyn",
    "central park area",
    "financial district area",
    "times square area",
]

# Tier 4: Embedding-based similarity (slower, 50-200ms typical)
# These have no direct text match and require vector similarity search
TIER_4_QUERIES = [
    "artsy neighborhood",
    "quiet residential area",
    "trendy area",
    "family friendly neighborhood",
    "hipster area",
    "upscale neighborhood",
    "affordable area",
    "walkable neighborhood",
    "near good restaurants",
    "cultural district",
    "near the water",
    "historic neighborhood",
]

# Tier 5: LLM-based landmark resolution (slowest, 200-500ms typical)
# These require LLM to resolve landmark/venue to a location
TIER_5_QUERIES = [
    "near central park",
    "close to empire state building",
    "near times square",
    "around brooklyn bridge",
    "near grand central",
    "close to lincoln center",
    "near columbia university",
    "around nyu",
    "near madison square garden",
    "close to moma",
    "near the met museum",
    "around yankee stadium",
    "near citi field",
    "close to jfk airport",
    "near prospect park",
    "around barclays center",
]

# Query modifiers to create realistic combinations
SERVICE_MODIFIERS = [
    "piano lessons",
    "guitar teacher",
    "math tutor",
    "yoga instructor",
    "swimming coach",
    "violin teacher",
    "voice lessons",
    "tennis coach",
]

PRICE_MODIFIERS = [
    "under $50",
    "under $75",
    "under $100",
    "cheap",
    "affordable",
]

AUDIENCE_MODIFIERS = [
    "for kids",
    "for adults",
    "for beginners",
    "for advanced",
]

TIME_MODIFIERS = [
    "tomorrow",
    "this weekend",
    "evenings",
    "mornings",
    "weekends",
]


def get_weighted_query() -> Tuple[str, str]:
    """
    Select a query based on tier distribution weights.

    Distribution:
    - 50% Tier 1-2 (exact/fuzzy match)
    - 20% Tier 3 (multi-region)
    - 15% Tier 4 (embedding)
    - 15% Tier 5 (LLM)

    Returns:
        Tuple of (query, tier_name) for tracking
    """
    roll = random.random()

    if roll < 0.50:
        # Tier 1-2: Exact/fuzzy match (50%)
        base_query = random.choice(TIER_1_2_QUERIES)
        tier = "tier_1_2"
    elif roll < 0.70:
        # Tier 3: Multi-region (20%)
        base_query = random.choice(TIER_3_QUERIES)
        tier = "tier_3"
    elif roll < 0.85:
        # Tier 4: Embedding similarity (15%)
        base_query = random.choice(TIER_4_QUERIES)
        tier = "tier_4"
    else:
        # Tier 5: LLM resolution (15%)
        base_query = random.choice(TIER_5_QUERIES)
        tier = "tier_5"

    # Optionally add modifiers to make queries more realistic
    if random.random() < 0.6:  # 60% chance to add service
        service = random.choice(SERVICE_MODIFIERS)
        base_query = f"{service} in {base_query}" if tier in ("tier_1_2", "tier_3") else f"{service} {base_query}"

    if random.random() < 0.2:  # 20% chance to add price
        price = random.choice(PRICE_MODIFIERS)
        base_query = f"{base_query} {price}"

    if random.random() < 0.15:  # 15% chance to add audience
        audience = random.choice(AUDIENCE_MODIFIERS)
        base_query = f"{base_query} {audience}"

    if random.random() < 0.1:  # 10% chance to add time
        time_mod = random.choice(TIME_MODIFIERS)
        base_query = f"{base_query} {time_mod}"

    return base_query, tier


# Global tier metrics tracking
tier_metrics: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "success": 0, "timeout": 0, "total_ms": 0})


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

    @tag("search", "tier-coverage")
    @task(10)  # High weight - primary tier coverage test
    def search_weighted(self) -> None:
        """
        Search using tier-weighted query distribution.

        Exercises all NL Search location resolution tiers:
        - 50% Tier 1-2 (exact/fuzzy ZIP/neighborhood)
        - 20% Tier 3 (multi-region/borough)
        - 15% Tier 4 (embedding similarity)
        - 15% Tier 5 (LLM landmark resolution)
        """
        query, tier = get_weighted_query()
        start_time = time_module.time()

        with self.client.get(
            f"/api/v1/search?q={query}",
            name=f"search_{tier}",
            catch_response=True,
        ) as response:
            elapsed_ms = int((time_module.time() - start_time) * 1000)

            # Track tier metrics
            tier_metrics[tier]["count"] += 1
            tier_metrics[tier]["total_ms"] += elapsed_ms

            if response.status_code == 200:
                tier_metrics[tier]["success"] += 1
                try:
                    data = response.json()
                    ids = extract_instructor_ids(data)
                    if ids:
                        discovered_instructor_ids.update(ids)
                    response.success()
                except Exception as e:
                    response.failure(f"JSON parse error: {e}")
            elif response.status_code in (503, 504):
                # Timeout or overload - track separately
                tier_metrics[tier]["timeout"] += 1
                response.failure(f"Timeout/overload: {response.status_code}")
            else:
                response.failure(f"Status {response.status_code}")

    @tag("search", "tier-coverage", "tier5")
    @task(3)  # Lower weight - stress test LLM tier specifically
    def search_tier5_only(self) -> None:
        """
        Stress test Tier 5 (LLM-based) location resolution.

        These queries require the most expensive processing path
        (LLM call to resolve landmarks to coordinates).
        """
        base_query = random.choice(TIER_5_QUERIES)

        # Always add a service to make it a realistic search
        service = random.choice(SERVICE_MODIFIERS)
        query = f"{service} {base_query}"

        start_time = time_module.time()

        with self.client.get(
            f"/api/v1/search?q={query}",
            name="search_tier_5",
            catch_response=True,
        ) as response:
            elapsed_ms = int((time_module.time() - start_time) * 1000)

            # Track Tier 5 metrics
            tier_metrics["tier_5_stress"]["count"] += 1
            tier_metrics["tier_5_stress"]["total_ms"] += elapsed_ms

            if response.status_code == 200:
                tier_metrics["tier_5_stress"]["success"] += 1
                try:
                    data = response.json()
                    ids = extract_instructor_ids(data)
                    if ids:
                        discovered_instructor_ids.update(ids)
                    response.success()
                except Exception as e:
                    response.failure(f"JSON parse error: {e}")
            elif response.status_code in (503, 504):
                tier_metrics["tier_5_stress"]["timeout"] += 1
                response.failure(f"Timeout/overload: {response.status_code}")
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
    logger.info("=" * 70)
    logger.info("Search & Discovery Load Test Starting")
    logger.info("-" * 70)
    logger.info(f"  API Base URL: {Config.BASE_URL}")
    logger.info(f"  Frontend Origin: {Config.FRONTEND_ORIGIN}")
    bypass_status = "ENABLED" if Config.RATE_LIMIT_BYPASS_TOKEN else "disabled"
    logger.info(f"  Rate limit bypass: {bypass_status}")
    logger.info("-" * 70)
    logger.info("  Query Pools:")
    logger.info(f"    Tier 1-2 (ZIP/neighborhood): {len(TIER_1_2_QUERIES)} queries (50%)")
    logger.info(f"    Tier 3 (borough/region): {len(TIER_3_QUERIES)} queries (20%)")
    logger.info(f"    Tier 4 (embedding): {len(TIER_4_QUERIES)} queries (15%)")
    logger.info(f"    Tier 5 (LLM landmark): {len(TIER_5_QUERIES)} queries (15%)")
    logger.info(f"    Cached queries: {len(CACHED_QUERIES)}")
    logger.info("-" * 70)
    logger.info("  Expected Latency Targets:")
    logger.info("    Tier 1-2: <20ms (exact/fuzzy match)")
    logger.info("    Tier 3: 20-50ms (multi-region)")
    logger.info("    Tier 4: 50-200ms (embedding search)")
    logger.info("    Tier 5: 200-500ms (LLM resolution)")
    logger.info("=" * 70)


@events.test_stop.add_listener
def on_test_stop(**_kwargs) -> None:
    """Log summary with tier distribution and latency stats."""
    logger.info("=" * 70)
    logger.info("Search & Discovery Load Test Complete")
    logger.info("-" * 70)
    logger.info(f"  Discovered {len(discovered_instructor_ids)} unique instructor IDs")
    logger.info("-" * 70)

    # Log tier metrics
    if tier_metrics:
        logger.info("  NL Search Tier Distribution & Latency:")
        logger.info("  " + "-" * 66)
        logger.info(f"  {'Tier':<15} {'Count':>8} {'Success':>8} {'Timeout':>8} {'Avg ms':>10} {'Success%':>10}")
        logger.info("  " + "-" * 66)

        total_count = 0
        total_success = 0
        total_timeout = 0

        for tier in ["tier_1_2", "tier_3", "tier_4", "tier_5", "tier_5_stress"]:
            metrics = tier_metrics.get(tier, {"count": 0, "success": 0, "timeout": 0, "total_ms": 0})
            count = metrics["count"]
            success = metrics["success"]
            timeout = metrics["timeout"]
            avg_ms = metrics["total_ms"] / count if count > 0 else 0
            success_pct = (success / count * 100) if count > 0 else 0

            total_count += count
            total_success += success
            total_timeout += timeout

            if count > 0:
                tier_display = tier.replace("_", " ").title()
                logger.info(f"  {tier_display:<15} {count:>8} {success:>8} {timeout:>8} {avg_ms:>10.1f} {success_pct:>9.1f}%")

        logger.info("  " + "-" * 66)
        total_success_pct = (total_success / total_count * 100) if total_count > 0 else 0
        logger.info(f"  {'TOTAL':<15} {total_count:>8} {total_success:>8} {total_timeout:>8} {'':>10} {total_success_pct:>9.1f}%")
    else:
        logger.info("  No tier metrics collected (search_weighted task not executed?)")

    logger.info("=" * 70)
