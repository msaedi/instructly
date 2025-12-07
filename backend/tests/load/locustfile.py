"""
InstaInstru Load Test Harness - Phases 1, 2 & 3

This module implements the Locust-based load testing for InstaInstru's messaging system.
- Phase 1: Authentication flow and basic authenticated requests
- Phase 2: SSE connection task with TTFE (Time To First Event) measurement
- Phase 3: End-to-end messaging with E2E latency measurement

Usage:
    cd backend/tests/load
    locust -f locustfile.py --headless -u 5 -r 1 -t 2m

Configuration via environment variables:
    LOADTEST_BASE_URL: API base URL (default: https://preview-api.instainstru.com)
    LOADTEST_FRONTEND_ORIGIN: Frontend origin for CSRF (default: https://preview.instainstru.com)
    LOADTEST_USERS: Comma-separated list of test user emails
    LOADTEST_PASSWORD: Password for all test users (default: TestPassword123!)
    LOADTEST_LOGIN_PATH: Login endpoint path (default: /api/v1/auth/login)
    LOADTEST_AUTH_CHECK_PATH: Auth check endpoint (default: /api/v1/auth/me)
    LOADTEST_SSE_PATH: SSE stream endpoint (default: /api/v1/messages/stream)
    LOADTEST_SSE_HOLD_SECONDS: How long to hold SSE connection (default: 45)
    LOADTEST_MESSAGE_PATH_TEMPLATE: Message send endpoint template (default: /api/v1/conversations/{conversation_id}/messages)
    LOADTEST_E2E_TIMEOUT_SECONDS: E2E message timeout (default: 10)
"""

import itertools
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterator
import uuid

from locust import HttpUser, between, events, task
import sseclient

# Shared state for cross-user E2E latency measurement
# When a sender sends a message, they record the correlation_id and timestamp here.
# When a receiver gets the message via SSE, they look it up and compute E2E latency.
PENDING_MESSAGES: dict[str, float] = {}  # correlation_id -> send_timestamp
PENDING_LOCK = threading.Lock()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Configuration from environment variables
class Config:
    """Load test configuration loaded from environment variables."""

    # API endpoints
    BASE_URL: str = os.getenv("LOADTEST_BASE_URL", "https://preview-api.instainstru.com")
    FRONTEND_ORIGIN: str = os.getenv("LOADTEST_FRONTEND_ORIGIN", "https://preview.instainstru.com")
    LOGIN_PATH: str = os.getenv("LOADTEST_LOGIN_PATH", "/api/v1/auth/login")
    AUTH_CHECK_PATH: str = os.getenv("LOADTEST_AUTH_CHECK_PATH", "/api/v1/auth/me")

    # SSE configuration (Phase 2)
    SSE_PATH: str = os.getenv("LOADTEST_SSE_PATH", "/api/v1/messages/stream")
    SSE_HOLD_SECONDS: float = float(os.getenv("LOADTEST_SSE_HOLD_SECONDS", "45"))

    # E2E messaging configuration (Phase 3)
    MESSAGE_PATH_TEMPLATE: str = os.getenv(
        "LOADTEST_MESSAGE_PATH_TEMPLATE",
        "/api/v1/conversations/{conversation_id}/messages",
    )
    E2E_TIMEOUT_SECONDS: float = float(os.getenv("LOADTEST_E2E_TIMEOUT_SECONDS", "10"))

    # Test users
    USERS: list[str] = [
        u.strip()
        for u in os.getenv("LOADTEST_USERS", "loadtest1@example.com").split(",")
        if u.strip()
    ]
    PASSWORD: str = os.getenv("LOADTEST_PASSWORD", "TestPassword123!")

    # Rate limit bypass token (must match RATE_LIMIT_BYPASS_TOKEN on server)
    # This allows load tests to bypass per-IP rate limits
    RATE_LIMIT_BYPASS_TOKEN: str = os.getenv("LOADTEST_BYPASS_TOKEN", "")


# Load conversations mapping from JSON file
CONVERSATIONS_FILE = Path(__file__).parent / "config" / "conversations.json"
CONVERSATIONS: dict[str, dict[str, str]] = {}

if CONVERSATIONS_FILE.exists():
    try:
        with open(CONVERSATIONS_FILE) as f:
            CONVERSATIONS = json.load(f)
        logger.info(f"Loaded {len(CONVERSATIONS)} conversation mappings from {CONVERSATIONS_FILE}")
    except Exception as e:
        logger.warning(f"Failed to load conversations.json: {e}")
else:
    logger.warning(f"Conversations file not found: {CONVERSATIONS_FILE}")


# Round-robin user selection using itertools.cycle
_user_cycle: Iterator[str] = itertools.cycle(Config.USERS)


def get_next_user() -> str:
    """Get the next user email from the round-robin cycle."""
    return next(_user_cycle)


class SSEMessagingUser(HttpUser):
    """
    Locust user for testing InstaInstru messaging system.

    Phase 1: Authentication and basic endpoint testing.
    Phase 2: SSE connections with TTFE measurement.
    Phase 3: E2E messaging with latency measurement.

    Attributes:
        host: Base URL for API requests (from Config or CLI)
        wait_time: Random wait between tasks (1-3 seconds)
        token: JWT access token after successful login
        user_email: Email of the authenticated user
        conversation_id: Conversation ID for messaging (from conversations.json)
        booking_id: Booking ID for messaging context (from conversations.json)
    """

    # Use configured base URL, can be overridden via Locust CLI --host
    host = Config.BASE_URL

    # Wait 1-3 seconds between tasks
    wait_time = between(1, 3)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.token: str | None = None
        self.user_email: str | None = None
        self.conversation_id: str | None = None
        self.booking_id: str | None = None

        # Set default headers for CSRF bypass (required for API requests from load test)
        # Origin must match the allowed frontend domain to pass CSRF validation
        headers = {
            "Origin": Config.FRONTEND_ORIGIN,
            "Referer": f"{Config.FRONTEND_ORIGIN}/",
            "Content-Type": "application/json",
        }
        # Add rate limit bypass token if configured (for load testing)
        if Config.RATE_LIMIT_BYPASS_TOKEN:
            headers["X-Rate-Limit-Bypass"] = Config.RATE_LIMIT_BYPASS_TOKEN
        self.client.headers.update(headers)

    def on_start(self) -> None:
        """
        Called when a simulated user starts.
        Performs login and stores the JWT token for subsequent requests.
        Also loads conversation mapping for E2E messaging.
        """
        self.user_email = get_next_user()
        logger.info(f"Starting user session for: {self.user_email}")

        # Perform login using OAuth2 form data (username field, not email)
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

        # Load conversation mapping for E2E messaging (Phase 3)
        if self.user_email and self.user_email in CONVERSATIONS:
            mapping = CONVERSATIONS[self.user_email]
            self.conversation_id = mapping.get("conversation_id")
            self.booking_id = mapping.get("booking_id")
            logger.info(
                f"Loaded conversation mapping for {self.user_email}: "
                f"conversation_id={self.conversation_id}, booking_id={self.booking_id}"
            )
        else:
            logger.warning(
                f"No conversation mapping for {self.user_email} - E2E messaging disabled"
            )

    @task(weight=1)
    def auth_check(self) -> None:
        """
        Simple authenticated task to verify the token is working.
        Calls GET /api/v1/auth/me to confirm authentication.
        Lower weight than SSE task.
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

    @task(weight=3)
    def maintain_sse_connection(self) -> None:
        """
        Open and maintain an SSE connection for real-time message streaming.
        Measures Time To First Event (TTFE) and reports it as a custom metric.

        Also checks for cross-user E2E correlation: when a new_message event
        contains a correlation ID from PENDING_MESSAGES, emits e2e_full_latency.

        The connection is held open for LOADTEST_SSE_HOLD_SECONDS before closing.
        """
        # Skip if not authenticated
        if not getattr(self, "token", None):
            logger.warning(f"Skipping SSE - no token for: {self.user_email}")
            return

        # Build headers for SSE request
        sse_headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Origin": Config.FRONTEND_ORIGIN,
            "Referer": f"{Config.FRONTEND_ORIGIN}/",
            "Authorization": f"Bearer {self.token}",
        }
        # Add rate limit bypass token if configured
        if Config.RATE_LIMIT_BYPASS_TOKEN:
            sse_headers["X-Rate-Limit-Bypass"] = Config.RATE_LIMIT_BYPASS_TOKEN

        logger.debug(f"Opening SSE connection for: {self.user_email}")

        try:
            with self.client.get(
                Config.SSE_PATH,
                headers=sse_headers,
                stream=True,
                name="sse_stream",
                catch_response=True,
                timeout=Config.SSE_HOLD_SECONDS + 30,  # Allow extra time beyond hold duration
            ) as response:
                if response.status_code != 200:
                    response.failure(f"SSE connect failed: {response.status_code}")
                    logger.error(
                        f"SSE connection failed for {self.user_email}: "
                        f"status={response.status_code}, body={response.text[:200]}"
                    )
                    return

                # Record connection start time for TTFE calculation
                connection_start = time.time()

                # Create SSE client from the response
                # Locust's response wraps requests.Response, access via .raw or iter_lines
                try:
                    sse_client = sseclient.SSEClient(response)
                except (TypeError, AttributeError):
                    # Fallback: try to access the underlying response
                    sse_client = sseclient.SSEClient(response.iter_lines())

                events_received = 0
                first_event_recorded = False

                # Iterate over SSE events until hold duration expires
                for event in sse_client.events():
                    now = time.time()
                    elapsed = now - connection_start

                    # Record TTFE for the first event with data
                    if not first_event_recorded and event.data:
                        ttfe_ms = elapsed * 1000.0
                        first_event_recorded = True

                        # Emit TTFE as a custom Locust metric
                        events.request.fire(
                            request_type="SSE",
                            name="ttfe",
                            response_time=ttfe_ms,
                            response_length=0,
                            exception=None,
                        )
                        logger.debug(
                            f"TTFE recorded for {self.user_email}: {ttfe_ms:.1f}ms"
                        )

                    events_received += 1

                    # Check for cross-user E2E correlation in new_message events
                    # NOTE: The event TYPE is in event.event (SSE protocol), not in the JSON data
                    if event.data and event.event == "new_message":
                        self._check_e2e_correlation(event.data, now)

                    # Stop after hold duration
                    if elapsed > Config.SSE_HOLD_SECONDS:
                        logger.debug(
                            f"SSE hold duration reached for {self.user_email}: "
                            f"{elapsed:.1f}s, {events_received} events received"
                        )
                        break

                # Mark the SSE connection as successful
                response.success()
                logger.info(
                    f"SSE connection closed for {self.user_email}: "
                    f"{events_received} events in {time.time() - connection_start:.1f}s"
                )

        except Exception as e:
            logger.error(f"SSE error for {self.user_email}: {e}")
            # The response context manager will handle failure reporting

    def _check_e2e_correlation(self, event_data: str, receive_time: float) -> None:
        """
        Check if an SSE event contains a correlation ID from a pending message.
        If found, emit e2e_full_latency metric for cross-user E2E measurement.

        Args:
            event_data: Raw JSON string from SSE event
            receive_time: Timestamp when the event was received
        """
        try:
            payload = json.loads(event_data)
        except json.JSONDecodeError:
            return

        # The SSE event type filtering is done before calling this method.
        # The payload structure for new_message is: {"message": {...}, "conversation_id": ..., "is_mine": ...}
        msg = payload.get("message", {}) or {}
        content = msg.get("content", "") or ""

        # Look for correlation pattern: "locust-e2e:<uuid>"
        prefix = "locust-e2e:"
        if prefix not in content:
            return

        # Extract correlation ID
        try:
            correlation_id = content.split(prefix, 1)[1].split()[0]
        except (IndexError, ValueError):
            return

        # Look up and remove from PENDING_MESSAGES
        send_time: float | None = None
        with PENDING_LOCK:
            send_time = PENDING_MESSAGES.pop(correlation_id, None)

        if send_time is not None:
            e2e_ms = (receive_time - send_time) * 1000.0
            events.request.fire(
                request_type="SSE",
                name="e2e_full_latency",
                response_time=e2e_ms,
                response_length=0,
                exception=None,
            )
            logger.info(
                f"E2E full latency for {self.user_email}: {e2e_ms:.1f}ms "
                f"(correlation_id={correlation_id[:8]}...)"
            )

    @task(weight=1)
    def send_message_and_measure_e2e(self) -> None:
        """
        Send a message with correlation ID for cross-user E2E measurement.

        This task:
        1. Generates a correlation ID
        2. Records send time in PENDING_MESSAGES shared state
        3. Sends the message via POST
        4. Does NOT wait for SSE (the receiver computes E2E latency)

        The actual E2E latency (e2e_full_latency) is emitted by the receiving
        user's maintain_sse_connection task when they get the new_message event.
        """
        # Precondition checks
        if not getattr(self, "token", None):
            logger.warning(f"Skipping E2E send - no token for: {self.user_email}")
            return

        if not self.conversation_id:
            logger.debug(f"Skipping E2E send - no conversation_id for: {self.user_email}")
            return

        # Generate correlation ID for cross-user E2E tracking
        correlation_id = str(uuid.uuid4())
        content = f"locust-e2e:{correlation_id}"

        # Record send time in shared state BEFORE sending
        with PENDING_LOCK:
            PENDING_MESSAGES[correlation_id] = time.time()

        # Build message path and payload
        message_path = Config.MESSAGE_PATH_TEMPLATE.format(
            conversation_id=self.conversation_id
        )
        message_body = {"content": content}
        if self.booking_id:
            message_body["booking_id"] = self.booking_id

        # Send the message - Locust tracks this as normal HTTP latency
        post_response = self.client.post(
            message_path,
            json=message_body,
            name="send_message",
        )

        # Check POST response
        if post_response.status_code not in (200, 201):
            logger.error(
                f"Message send failed for {self.user_email}: "
                f"status={post_response.status_code}, body={post_response.text[:200]}"
            )
            # Clean up pending message since send failed
            with PENDING_LOCK:
                PENDING_MESSAGES.pop(correlation_id, None)
            return

        logger.debug(
            f"Message sent for {self.user_email}: correlation_id={correlation_id[:8]}..."
        )


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
    logger.info(f"  SSE path: {Config.SSE_PATH}")
    logger.info(f"  SSE hold duration: {Config.SSE_HOLD_SECONDS}s")
    logger.info(f"  Message path template: {Config.MESSAGE_PATH_TEMPLATE}")
    logger.info(f"  E2E timeout: {Config.E2E_TIMEOUT_SECONDS}s")
    logger.info(f"  Conversations loaded: {len(CONVERSATIONS)}")
    bypass_status = "ENABLED" if Config.RATE_LIMIT_BYPASS_TOKEN else "disabled"
    logger.info(f"  Rate limit bypass: {bypass_status}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(**_kwargs: Any) -> None:
    """Log summary when test stops."""
    logger.info("=" * 60)
    logger.info("InstaInstru Load Test Complete")
    logger.info("=" * 60)
