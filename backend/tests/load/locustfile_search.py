"""
Load test for Search & Discovery flow (unauthenticated).
Simulates users searching for instructors and viewing profiles.

This tests the core unauthenticated user journey - the highest traffic flow
that doesn't require login. This is the first impression and must be fast.

User Journey Simulated:
1. Load homepage (services catalog)
2. Click category pill OR type natural language search
3. View search results
4. Click on instructor profile
5. View availability calendar
6. (Optional) View reviews

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

from locust import HttpUser, between, events, tag, task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Sample search queries (realistic user searches)
SEARCH_QUERIES = [
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

CATEGORIES = [
    "music",
    "tutoring",
    "sports-fitness",
    "language",
    "arts",
    "technology",
    "lifestyle",
]

# Known instructor IDs from production database (is_live=true)
INSTRUCTOR_IDS = [
    "01KC57H6ZJ795K25XQDAPA4Y85",  # Amanda Johnson
    "01KC57H6ZJA7EZBE1XFFS9KKK7",  # Jason Park
    "01KC57H6ZJKP543DH2M49TH5VW",  # Carlos Garcia
    "01KC57H6ZJN0M4510PXM5SAKXT",  # Michael Rodriguez
    "01KC57H6ZJS2YXD6TC680M7DVC",  # Sarah Chen
    "01KC57H6ZK0010HHV92YQ3TPPN",  # Wei Zhang
    "01KC57H6ZK0X1N0CX5291HQRFM",  # James Wilson
    "01KC57H6ZK0XXTWNTJMCG564WX",  # Sarah Mitchell
    "01KC57H6ZK112H0BKFNT4K4FBJ",  # Kevin Zhang
    "01KC57H6ZK3ZBR5ATFNQVCJMY7",  # Yuki Nakamura
    "01KC57H6ZK4QQ0NSJYAJAV94RP",  # Dwayne Jackson
    "01KC57H6ZK54D873BK1SV02T6G",  # Lucia Fernandez
    "01KC57H6ZK68Z6N2D0F7QNA8YP",  # Robert Davis
    "01KC57H6ZK7N0DE99YJ0DP7JZA",  # Carlos Mendez
    "01KC57H6ZK9B6AMASTNJ0XVDFW",  # Jin Park
]


class Config:
    """Load test configuration loaded from environment variables."""

    BASE_URL: str = os.getenv("LOADTEST_BASE_URL", "https://preview-api.instainstru.com")
    FRONTEND_ORIGIN: str = os.getenv(
        "LOADTEST_FRONTEND_ORIGIN", "https://preview.instainstru.com"
    )
    RATE_LIMIT_BYPASS_TOKEN: str = os.getenv("LOADTEST_BYPASS_TOKEN", "")


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
    @task(5)  # Highest weight - core action
    def natural_language_search(self) -> None:
        """Search using natural language query."""
        query = random.choice(SEARCH_QUERIES)
        with self.client.get(
            f"/api/v1/search/instructors?q={query}",
            name="search_nl",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    # Verify we got results structure
                    if "items" in data or "results" in data or isinstance(data, list):
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
        """Search by category name (as query)."""
        # Use category names as search queries (the API requires q param)
        category_queries = ["music lessons", "tutoring", "fitness", "art classes", "language"]
        query = random.choice(category_queries)
        with self.client.get(
            f"/api/v1/search/instructors?q={query}",
            name="search_category",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @tag("profile")
    @task(4)  # High weight - users view profiles
    def view_instructor_profile(self) -> None:
        """View an instructor's profile page."""
        instructor_id = random.choice(INSTRUCTOR_IDS)
        with self.client.get(
            f"/api/v1/instructors/{instructor_id}",
            name="instructor_profile",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Instructor may not exist, mark as success but log
                logger.debug(f"Instructor {instructor_id} not found")
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @tag("profile")
    @task(3)
    def view_instructor_ratings(self) -> None:
        """View instructor's ratings/reviews."""
        instructor_id = random.choice(INSTRUCTOR_IDS)
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
        instructor_id = random.choice(INSTRUCTOR_IDS)
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


class AggressiveSearchUser(HttpUser):
    """
    Simulates power user doing rapid searches.
    Use sparingly - represents ~10% of traffic.
    """

    host = Config.BASE_URL
    wait_time = between(0.5, 1)  # Faster browsing
    weight = 1  # Lower weight than normal users

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

    @task
    def rapid_search(self) -> None:
        """Quick successive searches (autocomplete behavior)."""
        base_query = random.choice(["piano", "guitar", "math", "spanish", "yoga"])

        # Simulate typing/autocomplete
        for i in range(1, len(base_query) + 1):
            partial = base_query[:i]
            self.client.get(
                f"/api/v1/search/instructors?q={partial}", name="search_autocomplete"
            )


# Event listeners for test lifecycle logging
@events.test_start.add_listener
def on_test_start(**_kwargs) -> None:
    """Log test configuration when starting."""
    logger.info("=" * 60)
    logger.info("Search & Discovery Load Test Starting")
    logger.info(f"  API Base URL: {Config.BASE_URL}")
    logger.info(f"  Frontend Origin: {Config.FRONTEND_ORIGIN}")
    logger.info(f"  Instructor IDs: {len(INSTRUCTOR_IDS)} configured")
    logger.info(f"  Search queries: {len(SEARCH_QUERIES)} configured")
    bypass_status = "ENABLED" if Config.RATE_LIMIT_BYPASS_TOKEN else "disabled"
    logger.info(f"  Rate limit bypass: {bypass_status}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(**_kwargs) -> None:
    """Log summary when test stops."""
    logger.info("=" * 60)
    logger.info("Search & Discovery Load Test Complete")
    logger.info("=" * 60)
