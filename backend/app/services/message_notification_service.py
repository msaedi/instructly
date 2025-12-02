# backend/app/services/message_notification_service.py
"""
Message Notification Service for real-time messaging.

Manages PostgreSQL LISTEN/NOTIFY for Server-Sent Events (SSE)
to enable real-time chat without polling.

Uses dependency injection pattern - NO SINGLETONS.
"""

import asyncio
import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Set

import asyncpg
from asyncpg import Connection

from ..core.config import settings

logger = logging.getLogger(__name__)


class MessageNotificationService:
    """
    Service that manages PostgreSQL LISTEN/NOTIFY connections
    and routes messages to SSE subscribers.

    This service uses a dedicated asyncpg connection for LISTEN
    operations, separate from the main SQLAlchemy connection pool.
    """

    # Heartbeat configuration
    HEARTBEAT_INTERVAL = 30  # Send heartbeat every 30 seconds
    HEARTBEAT_TIMEOUT = 10  # If no heartbeat received in 10s after sending, reconnect
    # Use the SAME channel as real messages to verify the actual message path works
    HEARTBEAT_CHANNEL = "message_notifications"

    def __init__(self) -> None:
        """Initialize the notification service."""
        self.connection: Optional[Connection] = None
        self.subscribers: Dict[str, Set[asyncio.Queue[Dict[str, Any]]]] = {}
        self.listen_task: Optional[asyncio.Task[None]] = None
        self.is_listening = False
        self.logger = logging.getLogger(__name__)
        # Track startup test result
        self._startup_test_received = False

        # Heartbeat tracking for detecting silent connection deaths
        self._last_heartbeat_received: Optional[float] = None
        self._heartbeat_sent_at: Optional[float] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._watchdog_task: Optional[asyncio.Task[None]] = None

        # Threading-based watchdog (independent of event loop)
        self._thread_watchdog: Optional[threading.Thread] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Reconnection state to prevent double-reconnects
        self._reconnecting: bool = False

    async def start(self) -> None:
        """
        Start the notification service.

        Creates a dedicated PostgreSQL connection for LISTEN operations
        and starts the listener task.
        """
        try:
            # Create dedicated connection for LISTEN
            # Use session pooler URL for LISTEN/NOTIFY (bypasses PgBouncer transaction mode)
            # Falls back to regular database URL for local dev where pooler isn't used
            db_url = str(settings.listen_database_url)

            # [MSG-DEBUG] Log which connection is being used for LISTEN
            using_session_pooler = settings.database_url_session is not None
            # Mask credentials in log output
            host_part = db_url.split("@")[1] if "@" in db_url else "local"
            self.logger.info(
                "[MSG-DEBUG] NotificationService.start: Connecting for LISTEN/NOTIFY",
                extra={
                    "using_session_pooler": using_session_pooler,
                    "host": host_part.split("/")[0] if "/" in host_part else host_part,
                },
            )

            # Convert SQLAlchemy URL to asyncpg format
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgres://")
            elif db_url.startswith("postgresql+psycopg2://"):
                db_url = db_url.replace("postgresql+psycopg2://", "postgres://")

            self.connection = await asyncpg.connect(db_url)
            self.is_listening = True

            # Start the listener task
            self.listen_task = asyncio.create_task(self._listen_for_notifications())

            # Test LISTEN/NOTIFY is working with a startup test
            await self._run_startup_test()

            # Start heartbeat system to detect silent connection deaths
            await self._start_heartbeat_system()

            # Store event loop reference and start thread-based watchdog
            # The thread watchdog can detect issues even if the event loop is frozen
            self._event_loop = asyncio.get_running_loop()
            self._start_thread_watchdog()

            self.logger.info(
                "[MSG-DEBUG] NotificationService.start: Service started successfully",
                extra={
                    "using_session_pooler": using_session_pooler,
                    "listen_notify_working": self._startup_test_received,
                    "heartbeat_interval": self.HEARTBEAT_INTERVAL,
                    "heartbeat_timeout": self.HEARTBEAT_TIMEOUT,
                    "thread_watchdog_started": self._thread_watchdog is not None,
                },
            )

        except Exception as e:
            self.logger.error(f"Failed to start notification service: {str(e)}")
            raise

    async def stop(self) -> None:
        """
        Stop the notification service.

        Closes the PostgreSQL connection and cancels the listener task.
        """
        self.logger.info("[MSG-DEBUG] Stopping notification service...")
        self.is_listening = False

        # Stop thread watchdog first (will exit on next iteration due to is_listening=False)
        if self._thread_watchdog and self._thread_watchdog.is_alive():
            self._thread_watchdog.join(timeout=5)
            if self._thread_watchdog.is_alive():
                self.logger.warning("[MSG-DEBUG] Thread watchdog did not stop in time")

        # Cancel heartbeat and watchdog tasks
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        if self.connection:
            await self.connection.close()
            self.connection = None

        # Clear all subscribers and reset state
        self.subscribers.clear()
        self._last_heartbeat_received = None
        self._heartbeat_sent_at = None
        self._heartbeat_task = None
        self._watchdog_task = None
        self._thread_watchdog = None
        self._event_loop = None
        self._reconnecting = False

        self.logger.info("Message notification service stopped")

    async def subscribe(self, booking_id: str) -> asyncio.Queue[Dict[str, Any]]:
        """
        Subscribe to notifications for a specific booking (DEPRECATED - kept for backward compatibility).

        Args:
            booking_id: ID of the booking to subscribe to

        Returns:
            Queue that will receive message notifications
        """
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        if booking_id not in self.subscribers:
            self.subscribers[booking_id] = set()
            # Start listening to this booking's channel
            if self.connection:
                channel_name = f"booking_chat_{booking_id}"
                await self.connection.add_listener(channel_name, self._handle_notification)
            else:
                self.logger.warning(
                    f"No connection available for channel subscription: {booking_id}"
                )

        self.subscribers[booking_id].add(queue)
        self.logger.info(f"Added subscriber for booking {booking_id}")

        return queue

    async def subscribe_user(self, user_id: str) -> asyncio.Queue[Dict[str, Any]]:
        """
        Subscribe to notifications for a specific user (all their conversations).

        Args:
            user_id: ID of the user to subscribe to

        Returns:
            Queue that will receive message notifications for all user's conversations
        """
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        # [MSG-DEBUG] Log subscription attempt
        self.logger.info(
            "[MSG-DEBUG] NotificationService.subscribe_user: Starting",
            extra={
                "user_id": user_id,
                "existing_subscribers": list(self.subscribers.keys()),
                "has_connection": self.connection is not None,
            },
        )

        if user_id not in self.subscribers:
            self.subscribers[user_id] = set()
            # Start listening to this user's channel
            if self.connection:
                channel_name = f"user_{user_id}_inbox"
                self.logger.info(
                    "[MSG-DEBUG] NotificationService.subscribe_user: Adding LISTEN to channel",
                    extra={"user_id": user_id, "channel_name": channel_name},
                )
                await self.connection.add_listener(channel_name, self._handle_notification)
                self.logger.info(
                    "[MSG-DEBUG] NotificationService.subscribe_user: LISTEN registered",
                    extra={"user_id": user_id, "channel_name": channel_name},
                )
            else:
                self.logger.warning(
                    "[MSG-DEBUG] NotificationService.subscribe_user: NO CONNECTION",
                    extra={"user_id": user_id},
                )

        self.subscribers[user_id].add(queue)
        self.logger.info(
            "[MSG-DEBUG] NotificationService.subscribe_user: Subscription complete",
            extra={
                "user_id": user_id,
                "total_subscribers_for_user": len(self.subscribers[user_id]),
            },
        )

        return queue

    async def unsubscribe(self, booking_id: str, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        """
        Unsubscribe from notifications for a booking (DEPRECATED - kept for backward compatibility).

        Args:
            booking_id: ID of the booking
            queue: Queue to remove from subscribers
        """
        if booking_id in self.subscribers:
            self.subscribers[booking_id].discard(queue)

            # If no more subscribers for this booking, stop listening
            if not self.subscribers[booking_id]:
                del self.subscribers[booking_id]
                if self.connection:
                    channel_name = f"booking_chat_{booking_id}"
                    await self.connection.remove_listener(channel_name, self._handle_notification)
                    self.logger.info(f"Stopped listening to channel: {channel_name}")

        self.logger.info(f"Removed subscriber for booking {booking_id}")

    async def unsubscribe_user(self, user_id: str, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        """
        Unsubscribe from notifications for a user.

        Args:
            user_id: ID of the user
            queue: Queue to remove from subscribers
        """
        if user_id in self.subscribers:
            self.subscribers[user_id].discard(queue)

            # If no more subscribers for this user, stop listening
            if not self.subscribers[user_id]:
                del self.subscribers[user_id]
                if self.connection:
                    channel_name = f"user_{user_id}_inbox"
                    await self.connection.remove_listener(channel_name, self._handle_notification)
                    self.logger.info(f"Stopped listening to user channel: {channel_name}")

        self.logger.info(f"Removed subscriber for user {user_id}")

    async def _run_startup_test(self) -> None:
        """
        Test that LISTEN/NOTIFY is working by sending a test notification.

        This verifies the database connection supports LISTEN/NOTIFY (not broken by PgBouncer
        transaction pooling). Without session mode, the listener would be lost after each
        transaction, causing this test to fail.
        """
        if not self.connection:
            self.logger.warning("[MSG-DEBUG] Cannot run startup test: no connection")
            return

        test_channel = "startup_test_channel"
        test_payload = "startup_test"

        self.logger.info(
            "[MSG-DEBUG] NotificationService._run_startup_test: Starting LISTEN/NOTIFY test..."
        )

        try:
            # Add listener for test channel
            await self.connection.add_listener(test_channel, self._handle_startup_test)
            self.logger.info(
                "[MSG-DEBUG] NotificationService._run_startup_test: LISTEN registered",
                extra={"channel": test_channel},
            )

            # Send NOTIFY to test channel
            await self.connection.execute(f"NOTIFY {test_channel}, '{test_payload}'")
            self.logger.info(
                "[MSG-DEBUG] NotificationService._run_startup_test: NOTIFY sent, waiting for callback..."
            )

            # Wait a moment for the notification to be received
            await asyncio.sleep(0.5)

            # Check if test was received
            if self._startup_test_received:
                self.logger.info(
                    "[MSG-DEBUG] NotificationService._run_startup_test: SUCCESS - LISTEN/NOTIFY is WORKING!"
                )
            else:
                self.logger.error(
                    "[MSG-DEBUG] NotificationService._run_startup_test: FAILED - NOTIFY not received! "
                    "Real-time messaging will NOT work. Check if DATABASE_URL_SESSION is configured "
                    "with Supabase session pooler (port 5432)."
                )

            # Clean up test listener
            await self.connection.remove_listener(test_channel, self._handle_startup_test)

        except Exception as e:
            self.logger.error(
                "[MSG-DEBUG] NotificationService._run_startup_test: ERROR during test",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

    def _handle_startup_test(
        self, connection: Connection, pid: int, channel: str, payload: str
    ) -> None:
        """Handle the startup test notification callback."""
        self.logger.info(
            "[MSG-DEBUG] NotificationService._handle_startup_test: NOTIFY RECEIVED!",
            extra={"channel": channel, "payload": payload, "pid": pid},
        )
        if payload == "startup_test":
            self._startup_test_received = True

    async def _heartbeat_loop(self) -> None:
        """
        Periodically send heartbeat NOTIFY to verify the LISTEN connection is alive.

        The heartbeat is sent through the SAME connection that's listening, which
        verifies the actual LISTEN path works. If the connection has died silently
        (common with Supabase session pooler after ~5-7 minutes), the heartbeat
        send will fail or the response won't be received.
        """
        self.logger.info("[MSG-DEBUG] Heartbeat loop started")

        while self.is_listening:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)

                if not self.is_listening:
                    break

                if self.connection and not self.connection.is_closed():
                    # Send heartbeat through the SAME connection that's listening
                    heartbeat_payload = json.dumps({"type": "heartbeat", "timestamp": time.time()})

                    # Set timestamp BEFORE sending (fixes race condition with watchdog)
                    self._heartbeat_sent_at = time.time()

                    await self.connection.execute(
                        f"NOTIFY {self.HEARTBEAT_CHANNEL}, '{heartbeat_payload}'"
                    )
                    self.logger.info(
                        "[MSG-DEBUG] Heartbeat NOTIFY sent",
                        extra={"timestamp": self._heartbeat_sent_at},
                    )
                else:
                    self.logger.warning("[MSG-DEBUG] Heartbeat loop: connection not available")

            except asyncio.CancelledError:
                self.logger.info("[MSG-DEBUG] Heartbeat loop cancelled")
                break
            except Exception as e:
                self.logger.error(
                    "[MSG-DEBUG] Heartbeat send failed - connection may be dead",
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                # Connection is dead, trigger reconnect
                await self._force_reconnect()
                break

        self.logger.info("[MSG-DEBUG] Heartbeat loop exited")

    async def _watchdog_loop(self) -> None:
        """
        Monitor heartbeat responses and reconnect if the connection dies silently.

        The watchdog checks if heartbeats are being received. If a heartbeat was
        sent but not received within the timeout, the connection has died silently
        and we need to force a reconnection.
        """
        self.logger.info("[MSG-DEBUG] Watchdog loop started")

        while self.is_listening:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds

                if not self.is_listening:
                    break

                # Only check if we've sent a heartbeat
                if self._heartbeat_sent_at is not None:
                    time_since_sent = time.time() - self._heartbeat_sent_at

                    # If heartbeat was sent but not received within timeout
                    if time_since_sent > self.HEARTBEAT_TIMEOUT:
                        # Check if heartbeat was received after it was sent
                        heartbeat_received_after_send = (
                            self._last_heartbeat_received is not None
                            and self._last_heartbeat_received >= self._heartbeat_sent_at
                        )

                        if not heartbeat_received_after_send:
                            self.logger.warning(
                                "[MSG-DEBUG] Heartbeat missed! Connection appears dead, forcing reconnect...",
                                extra={
                                    "time_since_sent": round(time_since_sent, 1),
                                    "last_heartbeat_received": self._last_heartbeat_received,
                                    "heartbeat_sent_at": self._heartbeat_sent_at,
                                },
                            )
                            await self._force_reconnect()
                            break
                        else:
                            # Heartbeat was received, reset sent timestamp to wait for next cycle
                            self._heartbeat_sent_at = None
                            self.logger.debug(
                                "[MSG-DEBUG] Heartbeat confirmed, resetting for next cycle"
                            )

            except asyncio.CancelledError:
                self.logger.info("[MSG-DEBUG] Watchdog loop cancelled")
                break
            except Exception as e:
                self.logger.error(
                    "[MSG-DEBUG] Watchdog error",
                    extra={"error": str(e), "error_type": type(e).__name__},
                )

        self.logger.info("[MSG-DEBUG] Watchdog loop exited")

    async def _force_reconnect(self) -> None:
        """
        Force close and reconnect the LISTEN connection.

        This is called when a silent connection death is detected (heartbeat missed).
        It cancels the heartbeat and watchdog tasks, closes the connection, and
        triggers the listener loop to reconnect.
        """
        if self._reconnecting:
            self.logger.debug("[MSG-DEBUG] Reconnection already in progress, skipping")
            return

        self._reconnecting = True
        try:
            self.logger.info("[MSG-DEBUG] Forcing reconnection...")

            # Cancel heartbeat and watchdog tasks
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            if self._watchdog_task and not self._watchdog_task.done():
                self._watchdog_task.cancel()
                try:
                    await self._watchdog_task
                except asyncio.CancelledError:
                    pass

            # Close existing connection
            if self.connection and not self.connection.is_closed():
                try:
                    await self.connection.close()
                except Exception as e:
                    self.logger.warning(
                        "[MSG-DEBUG] Error closing connection during force reconnect",
                        extra={"error": str(e)},
                    )

            # Reset state - the listener loop will detect connection is None and reconnect
            self.connection = None
            self._last_heartbeat_received = None
            self._heartbeat_sent_at = None
            self._heartbeat_task = None
            self._watchdog_task = None

            self.logger.info("[MSG-DEBUG] Force reconnect complete - listener loop will reconnect")
        finally:
            self._reconnecting = False

    async def _is_connection_alive(self) -> bool:
        """
        Check if the PostgreSQL connection is still responsive.

        Attempts a simple query to verify the connection is alive.

        Returns:
            True if connection is responsive, False otherwise
        """
        try:
            if not self.connection or self.connection.is_closed():
                return False

            # Try a simple query with timeout
            await asyncio.wait_for(
                self.connection.fetchval("SELECT 1"),
                timeout=5.0,
            )
            return True
        except asyncio.TimeoutError:
            self.logger.warning("[MSG-DEBUG] Connection alive check timed out")
            return False
        except Exception as e:
            self.logger.warning(
                "[MSG-DEBUG] Connection alive check failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            return False

    def _start_thread_watchdog(self) -> None:
        """
        Start a threading-based watchdog that monitors connection health.

        This watchdog runs in a separate thread, independent of the asyncio event loop.
        If the event loop freezes (e.g., due to a hung connection), this thread can
        still detect the issue and attempt to trigger recovery.
        """

        def watchdog_loop() -> None:
            self.logger.info("[MSG-DEBUG] Thread watchdog started")

            while self.is_listening:
                try:
                    time.sleep(15)  # Check every 15 seconds

                    if not self.is_listening:
                        break

                    # Skip if already reconnecting
                    if self._reconnecting:
                        self.logger.debug("[MSG-DEBUG] Thread watchdog: reconnection in progress")
                        continue

                    # Check heartbeat timing
                    if self._last_heartbeat_received is not None:
                        seconds_since_heartbeat = time.time() - self._last_heartbeat_received

                        if seconds_since_heartbeat > 90:  # 3 missed heartbeats
                            self.logger.critical(
                                "[MSG-DEBUG] THREAD WATCHDOG ALERT: No heartbeat for "
                                f"{seconds_since_heartbeat:.0f}s! Triggering reconnect...",
                                extra={
                                    "seconds_since_heartbeat": round(seconds_since_heartbeat, 1),
                                    "event_loop_running": self._event_loop.is_running()
                                    if self._event_loop
                                    else None,
                                },
                            )

                            # Try to trigger reconnect via the event loop
                            if self._event_loop and self._event_loop.is_running():
                                try:
                                    future = asyncio.run_coroutine_threadsafe(
                                        self._force_reconnect(), self._event_loop
                                    )
                                    # Wait up to 10 seconds for reconnect to complete
                                    future.result(timeout=10)
                                    self.logger.info(
                                        "[MSG-DEBUG] Thread watchdog: reconnect triggered successfully"
                                    )
                                except Exception as e:
                                    self.logger.error(
                                        "[MSG-DEBUG] Thread watchdog: failed to trigger reconnect",
                                        extra={"error": str(e), "error_type": type(e).__name__},
                                    )
                            else:
                                self.logger.error(
                                    "[MSG-DEBUG] Thread watchdog: event loop not running, "
                                    "cannot trigger reconnect"
                                )

                        elif seconds_since_heartbeat > 60:  # 2 missed heartbeats - warning
                            self.logger.warning(
                                f"[MSG-DEBUG] Thread watchdog warning: no heartbeat for "
                                f"{seconds_since_heartbeat:.0f}s"
                            )

                    # Also check if connection is closed
                    if (
                        self.connection
                        and hasattr(self.connection, "is_closed")
                        and self.connection.is_closed()
                    ):
                        self.logger.warning("[MSG-DEBUG] Thread watchdog: connection is closed")

                except Exception as e:
                    self.logger.error(
                        "[MSG-DEBUG] Thread watchdog error",
                        extra={"error": str(e), "error_type": type(e).__name__},
                    )

            self.logger.info("[MSG-DEBUG] Thread watchdog stopped")

        self._thread_watchdog = threading.Thread(
            target=watchdog_loop,
            daemon=True,
            name="msg-notification-thread-watchdog",
        )
        self._thread_watchdog.start()

    async def _start_heartbeat_system(self) -> None:
        """Start the heartbeat and watchdog tasks after connection is established."""
        if not self.connection:
            self.logger.warning("[MSG-DEBUG] Cannot start heartbeat system: no connection")
            return

        try:
            # Add listener for heartbeat channel (uses same handler as real messages)
            # This ensures we're testing the SAME path that real messages use
            await self.connection.add_listener(self.HEARTBEAT_CHANNEL, self._handle_notification)
            self.logger.info(
                "[MSG-DEBUG] Heartbeat LISTEN registered on message_notifications channel",
                extra={"channel": self.HEARTBEAT_CHANNEL},
            )

            # Start heartbeat and watchdog tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

            self.logger.info(
                "[MSG-DEBUG] Heartbeat system started - will detect silent connection deaths"
            )

        except Exception as e:
            self.logger.error(
                "[MSG-DEBUG] Failed to start heartbeat system",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

    async def _listen_for_notifications(self) -> None:
        """
        Main listener loop that processes PostgreSQL notifications.

        This runs continuously while the service is active,
        handling reconnection if necessary.
        """
        while self.is_listening:
            try:
                if not self.connection or self.connection.is_closed():
                    # Reconnect if connection was lost (without spawning new task)
                    self.logger.info(
                        "[MSG-DEBUG] NotificationService._listen_for_notifications: Connection lost, reconnecting..."
                    )
                    try:
                        # Use session pooler URL for LISTEN/NOTIFY
                        db_url = str(settings.listen_database_url)
                        using_session_pooler = settings.database_url_session is not None

                        # Convert SQLAlchemy URL to asyncpg format
                        if db_url.startswith("postgresql://"):
                            db_url = db_url.replace("postgresql://", "postgres://")
                        elif db_url.startswith("postgresql+psycopg2://"):
                            db_url = db_url.replace("postgresql+psycopg2://", "postgres://")

                        self.connection = await asyncpg.connect(db_url)

                        # Re-subscribe to all channels we were listening to
                        for subscriber_id in self.subscribers.keys():
                            # Determine channel type based on subscriber format
                            if subscriber_id.startswith("user_"):
                                channel_name = f"{subscriber_id}_inbox"
                            else:
                                channel_name = f"booking_chat_{subscriber_id}"
                            await self.connection.add_listener(
                                channel_name, self._handle_notification
                            )

                        # Restart heartbeat system after reconnection
                        await self._start_heartbeat_system()

                        self.logger.info(
                            "[MSG-DEBUG] NotificationService._listen_for_notifications: Reconnected successfully",
                            extra={
                                "using_session_pooler": using_session_pooler,
                                "resubscribed_channels": len(self.subscribers),
                                "heartbeat_restarted": True,
                            },
                        )
                    except Exception as e:
                        self.logger.error(f"Failed to reconnect: {str(e)}")
                        await asyncio.sleep(5)
                        continue

                # Wait for notifications (this blocks but is async)
                await asyncio.sleep(1)  # Check connection periodically

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in notification listener: {str(e)}")
                # Wait before retrying
                await asyncio.sleep(5)

    def _handle_notification(
        self, connection: Connection, pid: int, channel: str, payload: str
    ) -> None:
        """
        Handle incoming PostgreSQL notifications.

        This is called by asyncpg when a NOTIFY is received.

        Args:
            connection: The asyncpg connection
            pid: Process ID of the notifying backend
            channel: Channel name (e.g., "user_123_inbox" or "booking_chat_123")
            payload: JSON payload containing message data
        """
        # [MSG-DEBUG] Log incoming notification
        self.logger.info(
            "[MSG-DEBUG] NotificationService._handle_notification: NOTIFY received",
            extra={
                "channel": channel,
                "pid": pid,
                "payload_preview": payload[:200] if len(payload) > 200 else payload,
            },
        )

        try:
            # Parse the JSON payload
            decoded = json.loads(payload)
            message_data: Dict[str, Any]
            if isinstance(decoded, dict):
                message_data = decoded
            else:
                message_data = {"payload": decoded}

            # Check if this is a heartbeat - handle it and return early
            if message_data.get("type") == "heartbeat":
                self._last_heartbeat_received = time.time()
                self.logger.info(
                    "[MSG-DEBUG] Heartbeat received on message channel - connection alive",
                    extra={
                        "channel": channel,
                        "timestamp": self._last_heartbeat_received,
                    },
                )
                return  # Don't route heartbeats to user queues

            # Handle message_notifications channel (used by send_message/reaction/edit_notification)
            # These contain recipient_ids and should be routed to user queues
            if channel == self.HEARTBEAT_CHANNEL:
                recipient_ids = message_data.get("recipient_ids", [])
                notification_type = message_data.get("type")
                if recipient_ids:
                    self.logger.info(
                        "[MSG-DEBUG] NotificationService._handle_notification: Routing message_notifications to user queues",
                        extra={
                            "recipient_ids": recipient_ids,
                            "event_type": notification_type,
                            "message_id": message_data.get("message_id")
                            or (
                                message_data.get("message", {}).get("id")
                                if isinstance(message_data.get("message"), dict)
                                else None
                            ),
                        },
                    )
                    for user_id in recipient_ids:
                        if user_id in self.subscribers:
                            for queue in self.subscribers[user_id]:
                                asyncio.create_task(self._send_to_queue(queue, message_data))
                        else:
                            self.logger.debug(
                                "[MSG-DEBUG] No subscriber for user_id",
                                extra={"user_id": user_id},
                            )
                else:
                    self.logger.warning(
                        "[MSG-DEBUG] message_notifications with no recipient_ids",
                        extra={"event_type": notification_type},
                    )
                return

            # [MSG-DEBUG] Log parsed notification data (for non-heartbeat messages)
            self.logger.info(
                "[MSG-DEBUG] NotificationService._handle_notification: Parsed",
                extra={
                    "channel": channel,
                    "event_type": message_data.get("type"),
                    "conversation_id": message_data.get("conversation_id"),
                    "message_id": message_data.get("message", {}).get("id")
                    if isinstance(message_data.get("message"), dict)
                    else None,
                },
            )

            # Handle user inbox channels (new format)
            if channel.startswith("user_") and channel.endswith("_inbox"):
                # Extract user ID from channel name: "user_123_inbox" -> "123"
                user_id = channel[5:-6]  # Remove "user_" prefix and "_inbox" suffix

                # Send to all subscribers for this user
                if user_id in self.subscribers:
                    subscriber_count = len(self.subscribers[user_id])
                    self.logger.info(
                        "[MSG-DEBUG] NotificationService._handle_notification: Routing to user queues",
                        extra={
                            "user_id": user_id,
                            "subscriber_count": subscriber_count,
                            "event_type": message_data.get("type"),
                        },
                    )
                    for queue in self.subscribers[user_id]:
                        # Use asyncio.create_task to avoid blocking
                        asyncio.create_task(self._send_to_queue(queue, message_data))
                else:
                    self.logger.warning(
                        "[MSG-DEBUG] NotificationService._handle_notification: No subscribers for user",
                        extra={
                            "user_id": user_id,
                            "active_subscribers": list(self.subscribers.keys()),
                        },
                    )

            # Handle legacy booking channels (old format - kept for backward compatibility)
            elif channel.startswith("booking_chat_"):
                booking_id = channel.replace("booking_chat_", "")

                # Send to all subscribers for this booking
                if booking_id in self.subscribers:
                    subscriber_count = len(self.subscribers[booking_id])
                    self.logger.info(
                        "[MSG-DEBUG] NotificationService._handle_notification: Routing to booking queues",
                        extra={
                            "booking_id": booking_id,
                            "subscriber_count": subscriber_count,
                        },
                    )
                    for queue in self.subscribers[booking_id]:
                        # Use asyncio.create_task to avoid blocking
                        asyncio.create_task(self._send_to_queue(queue, message_data))
                else:
                    self.logger.warning(
                        "[MSG-DEBUG] NotificationService._handle_notification: No subscribers for booking",
                        extra={"booking_id": booking_id},
                    )

        except Exception as e:
            self.logger.error(
                "[MSG-DEBUG] NotificationService._handle_notification: ERROR",
                extra={"channel": channel, "error": str(e), "error_type": type(e).__name__},
            )

    async def _send_to_queue(
        self, queue: asyncio.Queue[Dict[str, Any]], message_data: Dict[str, Any]
    ) -> None:
        """
        Send message data to a subscriber queue.

        Args:
            queue: Subscriber's queue
            message_data: Message data to send
        """
        try:
            # Don't block if queue is full
            queue.put_nowait(message_data)
            self.logger.info(
                "[MSG-DEBUG] NotificationService._send_to_queue: Message queued successfully",
                extra={
                    "event_type": message_data.get("type"),
                    "queue_size": queue.qsize(),
                },
            )
        except asyncio.QueueFull:
            self.logger.warning(
                "[MSG-DEBUG] NotificationService._send_to_queue: Queue full, message dropped",
                extra={"event_type": message_data.get("type")},
            )

    async def send_heartbeat(self, booking_id: str) -> None:
        """
        Send a heartbeat to all subscribers of a booking.

        This keeps SSE connections alive.

        Args:
            booking_id: ID of the booking
        """
        heartbeat_data: Dict[str, Any] = {
            "type": "heartbeat",
            "timestamp": asyncio.get_event_loop().time(),
        }

        if booking_id in self.subscribers:
            for queue in self.subscribers[booking_id]:
                await self._send_to_queue(queue, heartbeat_data)

    def get_subscriber_count(self, booking_id: str) -> int:
        """
        Get the number of subscribers for a booking.

        Args:
            booking_id: ID of the booking

        Returns:
            Number of active subscribers
        """
        return len(self.subscribers.get(booking_id, []))

    def is_healthy(self) -> bool:
        """
        Check if the notification service is healthy.

        Health is determined by:
        1. Service is actively listening
        2. Not currently reconnecting
        3. Connection exists and is not closed
        4. Heartbeat was received recently (within 90s = 3 * HEARTBEAT_INTERVAL)

        Returns:
            True if healthy, False otherwise
        """
        # Not running
        if not self.is_listening:
            self.logger.debug("[MSG-DEBUG] is_healthy: False - not listening")
            return False

        # Currently reconnecting
        if self._reconnecting:
            self.logger.debug("[MSG-DEBUG] is_healthy: False - reconnecting")
            return False

        # No connection or connection closed
        if not self.connection or self.connection.is_closed():
            self.logger.debug("[MSG-DEBUG] is_healthy: False - no connection or closed")
            return False

        # Check if we've received a heartbeat recently
        # Allow up to 90 seconds (3 missed heartbeats) before considering unhealthy
        max_heartbeat_age = self.HEARTBEAT_INTERVAL * 3
        if self._last_heartbeat_received is not None:
            heartbeat_age = time.time() - self._last_heartbeat_received
            if heartbeat_age > max_heartbeat_age:
                self.logger.debug(
                    "[MSG-DEBUG] is_healthy: False - heartbeat too old",
                    extra={
                        "heartbeat_age": round(heartbeat_age, 1),
                        "max_age": max_heartbeat_age,
                    },
                )
                return False

        return True

    def get_health_details(self) -> Dict[str, Any]:
        """
        Get detailed health information for diagnostics.

        Returns:
            Dictionary with health details
        """
        heartbeat_age = None
        if self._last_heartbeat_received is not None:
            heartbeat_age = round(time.time() - self._last_heartbeat_received, 1)

        return {
            "is_listening": self.is_listening,
            "reconnecting": self._reconnecting,
            "has_connection": self.connection is not None,
            "connection_closed": self.connection.is_closed() if self.connection else None,
            "subscriber_count": sum(len(queues) for queues in self.subscribers.values()),
            "last_heartbeat_age_seconds": heartbeat_age,
            "heartbeat_interval": self.HEARTBEAT_INTERVAL,
            "thread_watchdog_alive": self._thread_watchdog.is_alive()
            if self._thread_watchdog
            else False,
            "healthy": self.is_healthy(),
        }

    async def send_message_notification(
        self,
        conversation_id: str,
        sender_id: str,
        recipient_id: str,
        message_data: Dict[str, Any],
    ) -> bool:
        """
        Send NOTIFY through the session pooler connection (same as LISTEN).

        This ensures the notification reaches our listener, unlike DB triggers
        which go through the transaction pooler (different pool = no delivery).

        Args:
            conversation_id: The conversation ID
            sender_id: ID of the message sender
            recipient_id: ID of the message recipient
            message_data: Message data to include in notification

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self.connection or self.connection.is_closed():
            self.logger.warning("[MSG-DEBUG] Cannot send message notification - no connection")
            return False

        try:
            # Build notification payload
            payload = json.dumps(
                {
                    "type": "new_message",
                    "conversation_id": conversation_id,
                    "sender_id": sender_id,
                    "recipient_ids": [sender_id, recipient_id],
                    "message": message_data,
                }
            )

            # Escape single quotes in JSON payload for SQL
            escaped_payload = payload.replace("'", "''")

            # Send on the SAME connection that's doing LISTEN
            await self.connection.execute(f"NOTIFY {self.HEARTBEAT_CHANNEL}, '{escaped_payload}'")

            self.logger.info(
                "[MSG-DEBUG] Message notification sent via session pooler",
                extra={
                    "conversation_id": conversation_id,
                    "sender_id": sender_id,
                    "recipient_id": recipient_id,
                    "channel": self.HEARTBEAT_CHANNEL,
                },
            )
            return True

        except Exception as e:
            self.logger.error(
                "[MSG-DEBUG] Failed to send message notification",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "conversation_id": conversation_id,
                },
            )
            return False

    async def send_reaction_notification(
        self,
        conversation_id: str,
        message_id: str,
        user_id: str,
        recipient_id: str,
        reaction_data: Dict[str, Any],
    ) -> bool:
        """
        Send reaction NOTIFY through the session pooler connection.

        Args:
            conversation_id: The conversation ID
            message_id: ID of the message being reacted to
            user_id: ID of the user adding reaction
            recipient_id: ID of the other participant
            reaction_data: Reaction data to include

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self.connection or self.connection.is_closed():
            self.logger.warning("[MSG-DEBUG] Cannot send reaction notification - no connection")
            return False

        try:
            payload = json.dumps(
                {
                    "type": "reaction_update",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "user_id": user_id,
                    "recipient_ids": [user_id, recipient_id],
                    "reaction": reaction_data,
                }
            )

            escaped_payload = payload.replace("'", "''")

            await self.connection.execute(f"NOTIFY {self.HEARTBEAT_CHANNEL}, '{escaped_payload}'")

            self.logger.info(
                "[MSG-DEBUG] Reaction notification sent via session pooler",
                extra={
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "channel": self.HEARTBEAT_CHANNEL,
                },
            )
            return True

        except Exception as e:
            self.logger.error(
                "[MSG-DEBUG] Failed to send reaction notification",
                extra={"error": str(e), "message_id": message_id},
            )
            return False

    async def send_edit_notification(
        self,
        conversation_id: str,
        message_id: str,
        editor_id: str,
        recipient_id: str,
        new_content: str,
    ) -> bool:
        """
        Send edit NOTIFY through the session pooler connection.

        Args:
            conversation_id: The conversation ID (booking_id)
            message_id: ID of the message being edited
            editor_id: ID of the user editing the message
            recipient_id: ID of the other participant
            new_content: The new message content after editing

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self.connection or self.connection.is_closed():
            self.logger.warning("[MSG-DEBUG] Cannot send edit notification - no connection")
            return False

        try:
            payload = json.dumps(
                {
                    "type": "message_edited",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "editor_id": editor_id,
                    "recipient_ids": [editor_id, recipient_id],
                    "data": {
                        "content": new_content,
                    },
                }
            )

            escaped_payload = payload.replace("'", "''")

            await self.connection.execute(f"NOTIFY {self.HEARTBEAT_CHANNEL}, '{escaped_payload}'")

            self.logger.info(
                "[MSG-DEBUG] Edit notification sent via session pooler",
                extra={
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "channel": self.HEARTBEAT_CHANNEL,
                },
            )
            return True

        except Exception as e:
            self.logger.error(
                "[MSG-DEBUG] Failed to send edit notification",
                extra={"error": str(e), "message_id": message_id},
            )
            return False

    async def send_read_notification(
        self,
        conversation_id: str,
        reader_id: str,
        recipient_id: str,
        message_ids: list[str],
        read_at: str,
    ) -> bool:
        """
        Send read receipt NOTIFY through the session pooler connection.

        Notifies the sender that their messages have been read.

        Args:
            conversation_id: The conversation ID (booking_id)
            reader_id: ID of the user who read the messages
            recipient_id: ID of the user who sent the messages (to be notified)
            message_ids: List of message IDs that were marked as read
            read_at: ISO timestamp when messages were read

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self.connection or self.connection.is_closed():
            self.logger.warning("[MSG-DEBUG] Cannot send read notification - no connection")
            return False

        try:
            payload = json.dumps(
                {
                    "type": "read_receipt",
                    "conversation_id": conversation_id,
                    "reader_id": reader_id,
                    "recipient_ids": [recipient_id],  # Only notify the sender
                    "message_ids": message_ids,
                    "read_at": read_at,
                }
            )

            escaped_payload = payload.replace("'", "''")

            await self.connection.execute(f"NOTIFY {self.HEARTBEAT_CHANNEL}, '{escaped_payload}'")

            self.logger.info(
                "[MSG-DEBUG] Read notification sent via session pooler",
                extra={
                    "conversation_id": conversation_id,
                    "reader_id": reader_id,
                    "recipient_id": recipient_id,
                    "message_count": len(message_ids),
                    "channel": self.HEARTBEAT_CHANNEL,
                },
            )
            return True

        except Exception as e:
            self.logger.error(
                "[MSG-DEBUG] Failed to send read notification",
                extra={"error": str(e), "conversation_id": conversation_id},
            )
            return False
