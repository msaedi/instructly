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

    def __init__(self) -> None:
        """Initialize the notification service."""
        self.connection: Optional[Connection] = None
        self.subscribers: Dict[str, Set[asyncio.Queue[Dict[str, Any]]]] = {}
        self.listen_task: Optional[asyncio.Task[None]] = None
        self.is_listening = False
        self.logger = logging.getLogger(__name__)

    async def start(self) -> None:
        """
        Start the notification service.

        Creates a dedicated PostgreSQL connection for LISTEN operations
        and starts the listener task.
        """
        try:
            # Create dedicated connection for LISTEN
            # Use the active database URL from settings (respects INT/STG/PROD)
            db_url = str(settings.database_url)
            # Convert SQLAlchemy URL to asyncpg format
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgres://")
            elif db_url.startswith("postgresql+psycopg2://"):
                db_url = db_url.replace("postgresql+psycopg2://", "postgres://")

            self.connection = await asyncpg.connect(db_url)
            self.is_listening = True

            # Start the listener task
            self.listen_task = asyncio.create_task(self._listen_for_notifications())

            self.logger.info("Message notification service started successfully")

        except Exception as e:
            self.logger.error(f"Failed to start notification service: {str(e)}")
            raise

    async def stop(self) -> None:
        """
        Stop the notification service.

        Closes the PostgreSQL connection and cancels the listener task.
        """
        self.is_listening = False

        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        if self.connection:
            await self.connection.close()
            self.connection = None

        # Clear all subscribers
        self.subscribers.clear()

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
                    self.logger.info("Connection lost, attempting to reconnect...")
                    try:
                        # Use the active database URL from settings
                        db_url = str(settings.database_url)
                        # Convert SQLAlchemy URL to asyncpg format
                        if db_url.startswith("postgresql://"):
                            db_url = db_url.replace("postgresql://", "postgres://")
                        elif db_url.startswith("postgresql+psycopg2://"):
                            db_url = db_url.replace("postgresql+psycopg2://", "postgres://")

                        self.connection = await asyncpg.connect(db_url)

                        # Re-subscribe to all channels we were listening to
                        for booking_id in self.subscribers.keys():
                            channel_name = f"booking_chat_{booking_id}"
                            await self.connection.add_listener(
                                channel_name, self._handle_notification
                            )

                        self.logger.info("Successfully reconnected to database")
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

            # [MSG-DEBUG] Log parsed notification data
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
