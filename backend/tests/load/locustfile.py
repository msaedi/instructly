"""
InstaInstru Load Test Harness - Phase 1: Locust Skeleton & Auth Flow

This module implements the Locust-based load testing for InstaInstru's messaging system.
Phase 1 focuses on authentication flow and basic authenticated requests.

Usage:
    cd backend/tests/load
    locust -f locustfile.py --headless -u 5 -r 1 -t 1m

Configuration via environment variables:
    LOADTEST_BASE_URL: API base URL (default: https://preview-api.instainstru.com)
    LOADTEST_USERS: Comma-separated list of test user emails
    LOADTEST_PASSWORD: Password for all test users (default: TestPassword123!)
    LOADTEST_LOGIN_PATH: Login endpoint path (default: /api/v1/auth/login)
    LOADTEST_AUTH_CHECK_PATH: Auth check endpoint (default: /api/v1/auth/me)
"""

import itertools
import logging
import os
from typing import Any, Iterator

from locust import HttpUser, between, events, task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Configuration from environment variables
class Config:
    """Load test configuration loaded from environment variables."""

    BASE_URL: str = os.getenv("LOADTEST_BASE_URL", "https://preview-api.instainstru.com")
    # Frontend origin for CSRF bypass - must match the allowed frontend domain
    FRONTEND_ORIGIN: str = os.getenv("LOADTEST_FRONTEND_ORIGIN", "https://preview.instainstru.com")
    USERS: list[str] = [
        u.strip()
        for u in os.getenv("LOADTEST_USERS", "loadtest1@example.com").split(",")
        if u.strip()
    ]
    PASSWORD: str = os.getenv("LOADTEST_PASSWORD", "TestPassword123!")
    LOGIN_PATH: str = os.getenv("LOADTEST_LOGIN_PATH", "/api/v1/auth/login")
    AUTH_CHECK_PATH: str = os.getenv("LOADTEST_AUTH_CHECK_PATH", "/api/v1/auth/me")


# Round-robin user selection using itertools.cycle
_user_cycle: Iterator[str] = itertools.cycle(Config.USERS)


def get_next_user() -> str:
    """Get the next user email from the round-robin cycle."""
    return next(_user_cycle)


class SSEMessagingUser(HttpUser):
    """
    Locust user for testing InstaInstru messaging system.

    Phase 1: Authentication and basic endpoint testing.
    Future phases will add SSE connections and message sending.

    Attributes:
        host: Base URL for API requests (from Config or CLI)
        wait_time: Random wait between tasks (1-3 seconds)
        token: JWT access token after successful login
        user_email: Email of the authenticated user
    """

    # Use configured base URL, can be overridden via Locust CLI --host
    host = Config.BASE_URL

    # Wait 1-3 seconds between tasks
    wait_time = between(1, 3)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.token: str | None = None
        self.user_email: str | None = None

        # Set default headers for CSRF bypass (required for API requests from load test)
        # Origin must match the allowed frontend domain to pass CSRF validation
        self.client.headers.update(
            {
                "Origin": Config.FRONTEND_ORIGIN,
                "Referer": f"{Config.FRONTEND_ORIGIN}/",
                "Content-Type": "application/json",
            }
        )

    def on_start(self) -> None:
        """
        Called when a simulated user starts.
        Performs login and stores the JWT token for subsequent requests.
        """
        self.user_email = get_next_user()
        logger.info(f"Starting user session for: {self.user_email}")

        # Perform login using OAuth2 form data (username field, not email)
        # Override Content-Type for form submission
        login_payload = {"username": self.user_email, "password": Config.PASSWORD}

        with self.client.post(
            Config.LOGIN_PATH,
            data=login_payload,  # Form data, not JSON
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="login",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    access_token = data.get("access_token")

                    if access_token:
                        self.token = access_token
                        # Set Authorization header for all subsequent requests
                        self.client.headers["Authorization"] = f"Bearer {access_token}"
                        response.success()
                        logger.info(f"Login successful for: {self.user_email}")
                    else:
                        response.failure("Login response missing access_token")
                        logger.error(f"Login response missing access_token for: {self.user_email}")
                        self.token = None
                except Exception as e:
                    response.failure(f"Failed to parse login response: {e}")
                    logger.error(f"Failed to parse login response for {self.user_email}: {e}")
                    self.token = None
            else:
                response.failure(f"Login failed with status {response.status_code}")
                logger.error(
                    f"Login failed for {self.user_email}: "
                    f"status={response.status_code}, body={response.text[:200]}"
                )
                self.token = None

    @task
    def auth_check(self) -> None:
        """
        Simple authenticated task to verify the token is working.
        Calls GET /api/v1/auth/me to confirm authentication.
        """
        # Skip if not authenticated
        if self.token is None:
            logger.warning(f"Skipping auth_check - no token for: {self.user_email}")
            return

        with self.client.get(
            Config.AUTH_CHECK_PATH,
            name="auth_check",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure("Token expired or invalid")
                logger.warning(f"Auth check failed (401) for: {self.user_email}")
            else:
                response.failure(f"Auth check failed with status {response.status_code}")


# Event listeners for test lifecycle logging
@events.test_start.add_listener
def on_test_start(**_kwargs: Any) -> None:
    """Log test configuration when starting."""
    logger.info("=" * 60)
    logger.info("InstaInstru Load Test Starting")
    logger.info(f"  API Base URL: {Config.BASE_URL}")
    logger.info(f"  Frontend Origin: {Config.FRONTEND_ORIGIN}")
    logger.info(f"  Test users: {len(Config.USERS)} configured")
    logger.info(f"  Login path: {Config.LOGIN_PATH}")
    logger.info(f"  Auth check path: {Config.AUTH_CHECK_PATH}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(**_kwargs: Any) -> None:
    """Log summary when test stops."""
    logger.info("=" * 60)
    logger.info("InstaInstru Load Test Complete")
    logger.info("=" * 60)
