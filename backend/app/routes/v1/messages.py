# backend/app/routes/v1/messages.py
"""
Messages routes - API v1

Versioned message endpoints under /api/v1/messages.
All business logic delegated to MessageService.

Provides RESTful endpoints and Server-Sent Events (SSE) for real-time messaging
between instructors and students in bookings.

Key Features:
    - Real-time messaging via SSE (no polling)
    - Message history with pagination
    - Unread message counts and notifications
    - Rate limiting to prevent spam
    - RBAC permission checks

Endpoints (organized with static routes BEFORE dynamic routes):
    === Static Routes (Section 1) ===
    GET /stream - SSE endpoint for per-user real-time messages (Phase 2)
    GET /config - Get message configuration (edit window, etc.)
    GET /unread-count - Get total unread count for current user
    GET /inbox-state - Get all conversations with unread counts (Phase 3)
    POST /mark-read - Mark messages as read
    POST /send - Send a message to a booking chat

    === Booking-specific Routes (Section 2) ===
    GET /stream/{booking_id} - (DEPRECATED) SSE endpoint for booking-specific messages
    GET /history/{booking_id} - Get paginated message history
    POST /typing/{booking_id} - Send typing indicator

    === Message-specific Routes (Section 3) ===
    PATCH /{message_id} - Edit a message
    DELETE /{message_id} - Soft delete a message
    POST /{message_id}/reactions - Add emoji reaction
    DELETE /{message_id}/reactions - Remove emoji reaction
"""

import asyncio
from asyncio import Queue
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...api.dependencies.auth import get_current_active_user
from ...auth_sse import get_current_user_sse
from ...core.config import settings
from ...core.enums import PermissionName
from ...core.exceptions import ForbiddenException, NotFoundException, ValidationException
from ...database import get_db
from ...dependencies.permissions import require_permission
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...models.user import User
from ...schemas.message_requests import MarkMessagesReadRequest, SendMessageRequest
from ...schemas.message_responses import (
    DeleteMessageResponse,
    InboxStateResponse,
    MarkMessagesReadResponse,
    MessageConfigResponse,
    MessageResponse,
    MessagesHistoryResponse,
    SendMessageResponse,
    TypingStatusResponse,
    UnreadCountResponse,
)
from ...services.message_notification_service import MessageNotificationService
from ...services.message_service import MessageService

# Ensure request schema is fully built before FastAPI inspects annotations.
SendMessageRequest.model_rebuild()
MarkMessagesReadRequest.model_rebuild()

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["messages-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"

# Store the notification service instance (will be injected at startup)
_notification_service: MessageNotificationService | None = None


def set_notification_service(service: MessageNotificationService) -> None:
    """Set the notification service instance (called at app startup)."""
    global _notification_service
    _notification_service = service


def get_notification_service() -> MessageNotificationService:
    """Get the notification service instance."""
    if _notification_service is None:
        raise RuntimeError("Notification service not initialized")
    return _notification_service


def get_message_service(db: Session = Depends(get_db)) -> MessageService:
    """Get message service instance."""
    return MessageService(db)


# Phase 2 schemas (defined here to avoid import cycles)
class ReactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    emoji: str


class EditMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    content: str = Field(..., min_length=1, max_length=5000, description="New message content")


# ============================================================================
# SECTION 1: Static routes (no path parameters)
# MUST be defined before dynamic routes to prevent matching issues
# ============================================================================


@router.get(
    "/stream",
    responses={
        200: {"description": "SSE stream established for user's inbox"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
    },
)
async def stream_user_messages(
    current_user: User = Depends(get_current_user_sse),
    service: MessageService = Depends(get_message_service),
) -> EventSourceResponse:
    """
    SSE endpoint for real-time message streaming - per-user inbox.

    Establishes a Server-Sent Events connection for receiving
    real-time messages across ALL user's conversations.

    Events include conversation_id for client-side routing.
    Requires VIEW_MESSAGES permission.
    """

    # Check if user has VIEW_MESSAGES permission
    from ...services.permission_service import PermissionService

    permission_service = PermissionService(service.db)
    if not permission_service.user_has_permission(current_user.id, PermissionName.VIEW_MESSAGES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view messages",
        )

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        """Generate SSE events for the user's inbox."""
        queue: Queue[dict[str, Any]] | None = None
        notification_service: MessageNotificationService | None = None

        try:
            # Send initial connection confirmation
            yield {
                "event": "connected",
                "data": json.dumps({"user_id": current_user.id, "status": "connected"}),
            }

            # Small delay to ensure connection is established
            await asyncio.sleep(0.1)

            # Try to get notification service
            try:
                notification_service = get_notification_service()
            except RuntimeError as e:
                logger.warning(f"Notification service not available: {str(e)}")
                notification_service = None

            # Subscribe to user's inbox channel
            if notification_service:
                try:
                    queue = await notification_service.subscribe_user(current_user.id)
                    logger.info(
                        f"[SSE DEBUG] Subscribed to user {current_user.id} inbox, queue: {queue is not None}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to subscribe to user inbox: {str(e)}")
                    queue = None
            else:
                logger.warning(
                    f"[SSE DEBUG] No notification service available for user {current_user.id}"
                )

            # Main event loop
            last_heartbeat = datetime.now(timezone.utc)

            while True:
                try:
                    if queue:
                        # Try to get message from queue with timeout
                        try:
                            message_data = await asyncio.wait_for(
                                queue.get(), timeout=30.0
                            )  # 30 second timeout

                            # Process the message
                            event_type = message_data.get("type") or "message"
                            logger.info(
                                f"[SSE DEBUG] Received message from queue: type={event_type}, user={current_user.id}"
                            )

                            if event_type == "heartbeat":
                                yield {
                                    "event": "heartbeat",
                                    "data": json.dumps(
                                        {"timestamp": message_data.get("timestamp")}
                                    ),
                                }
                            else:
                                # Add is_mine flag for chat messages
                                if event_type == "new_message" and message_data.get("message"):
                                    message_data["is_mine"] = (
                                        message_data["message"].get("sender_id") == current_user.id
                                    )

                                yield {
                                    "event": event_type,
                                    "data": json.dumps(message_data),
                                }
                        except asyncio.TimeoutError:
                            # Timeout is normal - send keep-alive
                            yield {
                                "event": "keep-alive",
                                "data": json.dumps(
                                    {
                                        "status": "alive",
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                    }
                                ),
                            }
                    else:
                        # No queue available, send periodic heartbeats
                        await asyncio.sleep(5)
                        now = datetime.now(timezone.utc)
                        if (now - last_heartbeat).total_seconds() >= 30:
                            yield {
                                "event": "heartbeat",
                                "data": json.dumps(
                                    {
                                        "timestamp": now.isoformat(),
                                    }
                                ),
                            }
                            last_heartbeat = now

                except Exception as e:
                    # Log error but continue
                    logger.error(f"Error in SSE stream for user {current_user.id}: {str(e)}")
                    # Small delay before continuing
                    await asyncio.sleep(1)
                    continue

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in SSE generator for user {current_user.id}: {str(e)}")
            raise
        finally:
            # Clean up subscription
            if notification_service and queue:
                try:
                    await notification_service.unsubscribe_user(current_user.id, queue)
                except Exception as e:
                    logger.error(f"Error during unsubscribe: {str(e)}")

    # Create EventSourceResponse with appropriate headers
    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "Pragma": "no-cache",
            "Expires": "0",
        },
        media_type="text/event-stream",
    )


@router.get(
    "/config",
    response_model=MessageConfigResponse,
    responses={
        200: {"description": "Message configuration"},
    },
)
async def get_message_config() -> MessageConfigResponse:
    """
    Get public configuration values for the messaging UI.

    Returns:
        MessageConfigResponse with edit_window_minutes and other config values.
    """
    return MessageConfigResponse(
        edit_window_minutes=getattr(settings, "message_edit_window_minutes", 5)
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    dependencies=[Depends(require_permission(PermissionName.VIEW_MESSAGES))],
    responses={
        200: {"description": "Unread message count"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
    },
)
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> UnreadCountResponse:
    """
    Get total unread message count for current user.

    Requires VIEW_MESSAGES permission.
    """
    try:
        count = service.get_unread_count(current_user.id)

        return UnreadCountResponse(
            unread_count=count,
            user_id=current_user.id,
        )

    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread count",
        )


@router.get(
    "/inbox-state",
    response_model=InboxStateResponse,
    dependencies=[Depends(require_permission(PermissionName.VIEW_MESSAGES))],
    responses={
        200: {"description": "Inbox state with all conversations"},
        304: {"description": "Not Modified - content unchanged (ETag match)"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
    },
)
async def get_inbox_state(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
) -> InboxStateResponse:
    """
    Get all conversations with unread counts and last message previews.

    Supports ETag caching - returns 304 Not Modified if content unchanged.
    Poll this endpoint every 5-15 seconds for inbox updates.

    Returns:
        - conversations: List of all user's conversations
        - total_unread: Sum of all unread messages

    Requires VIEW_MESSAGES permission.
    """
    try:
        # Determine user role
        user_role = "instructor" if current_user.role == "instructor" else "student"

        # Get inbox state from service
        inbox_state = service.get_inbox_state(current_user.id, user_role)

        # Generate ETag
        etag = service.generate_inbox_etag(inbox_state)

        # Check if client has current version (ETag match)
        if if_none_match and if_none_match.strip('"') == etag:
            # FastAPI doesn't have a clean way to return 304, so we raise an exception
            # that gets caught and returns 304
            response.status_code = status.HTTP_304_NOT_MODIFIED
            # Return empty response for 304 - client will use cached version
            return InboxStateResponse(conversations=[], total_unread=0, unread_conversations=0)

        # Set ETag header for successful response
        response.headers["ETag"] = f'"{etag}"'

        # Return validated response model
        return InboxStateResponse(**inbox_state)

    except Exception as e:
        logger.error(f"Error getting inbox state: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get inbox state",
        )


@router.post(
    "/mark-read",
    response_model=MarkMessagesReadResponse,
    dependencies=[Depends(require_permission(PermissionName.VIEW_MESSAGES))],
    responses={
        200: {"description": "Messages marked as read"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
        422: {"description": "Either booking_id or message_ids must be provided"},
    },
)
async def mark_messages_as_read(
    request: MarkMessagesReadRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> MarkMessagesReadResponse:
    """
    Mark messages as read.

    Can mark specific messages or all messages in a booking.
    Requires VIEW_MESSAGES permission.
    """
    try:
        if request.booking_id:
            # Mark all messages in booking as read
            count = service.mark_booking_messages_as_read(
                booking_id=request.booking_id,
                user_id=current_user.id,
            )
        elif request.message_ids:
            # Mark specific messages as read
            count = service.mark_messages_as_read(
                message_ids=request.message_ids,
                user_id=current_user.id,
            )
        else:
            raise ValidationException("Either booking_id or message_ids must be provided")

        return MarkMessagesReadResponse(
            success=True,
            messages_marked=count,
        )

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ForbiddenException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error marking messages as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark messages as read",
        )


@router.post(
    "/send",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_permission(PermissionName.SEND_MESSAGES)),
    ],
    responses={
        201: {"description": "Message sent successfully"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied or no access to booking"},
        404: {"description": "Booking not found"},
    },
)
@rate_limit("10/minute", key_type=RateLimitKeyType.USER)
async def send_message(
    request: SendMessageRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> SendMessageResponse:
    """
    Send a message in a booking chat.

    Requires SEND_MESSAGES permission.
    Rate limited to 10 messages per minute.
    """
    try:
        message = service.send_message(
            booking_id=request.booking_id,
            sender_id=current_user.id,
            content=request.content,
        )

        return SendMessageResponse(
            success=True,
            message=MessageResponse.model_validate(message),
        )

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ForbiddenException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message",
        )


# ============================================================================
# SECTION 2: Booking-specific routes (with {booking_id} parameter)
# These use /stream/, /history/, /typing/ prefixes to avoid conflicts
# ============================================================================


# DEPRECATED: Per-booking SSE endpoint removed in Phase 2
# Replaced by /stream (per-user inbox) for ALL user conversations
# Old endpoint: /stream/{booking_id}
# New endpoint: /stream (no booking_id - receives all user's messages)


@router.get(
    "/history/{booking_id}",
    response_model=MessagesHistoryResponse,
    dependencies=[Depends(require_permission(PermissionName.VIEW_MESSAGES))],
    responses={
        200: {"description": "Message history"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied or no access to booking"},
    },
)
async def get_message_history(
    booking_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> MessagesHistoryResponse:
    """
    Get message history for a booking.

    Returns paginated list of messages in chronological order.
    Requires VIEW_MESSAGES permission.
    """
    try:
        messages = service.get_message_history(
            booking_id=booking_id,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
        )

        return MessagesHistoryResponse(
            booking_id=booking_id,
            messages=[MessageResponse.model_validate(msg) for msg in messages],
            limit=limit,
            offset=offset,
            has_more=len(messages) == limit,
        )

    except ForbiddenException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error fetching message history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch message history",
        )


@router.post(
    "/typing/{booking_id}",
    response_model=TypingStatusResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(PermissionName.SEND_MESSAGES))],
    responses={
        200: {"description": "Typing indicator sent"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied or no access to booking"},
    },
)
@rate_limit("1/second", key_type=RateLimitKeyType.USER)
async def send_typing_indicator(
    booking_id: str,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> TypingStatusResponse:
    """
    Send a typing indicator for a booking chat (ephemeral, no DB writes).

    Broadcasts a NOTIFY with type=typing_status.
    Rate limited to 1 per second.
    """
    # Let service handle access and notify
    try:
        service.send_typing_indicator(booking_id, current_user.id, current_user.first_name)
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to send typing indicator: {str(e)}")
    return TypingStatusResponse(success=True)


# ============================================================================
# SECTION 3: Message-specific routes (with {message_id} parameter)
# These must come LAST to avoid capturing static routes
# ============================================================================


@router.patch(
    "/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_permission(PermissionName.SEND_MESSAGES))],
    responses={
        204: {"description": "Message edited"},
        400: {"description": "Validation error (e.g., edit window expired)"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied or not message owner"},
        404: {"description": "Message not found"},
    },
)
@rate_limit("10/minute", key_type=RateLimitKeyType.USER)
async def edit_message(
    message_id: str,
    request: EditMessageRequest,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> Response:
    """
    Edit a message.

    Only the sender can edit their own messages within the edit window.
    Requires SEND_MESSAGES permission.
    """
    try:
        service.edit_message(message_id, current_user.id, request.content)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValidationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error editing message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to edit message"
        )


@router.delete(
    "/{message_id}",
    response_model=DeleteMessageResponse,
    dependencies=[Depends(require_permission(PermissionName.SEND_MESSAGES))],
    responses={
        200: {"description": "Message deleted"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied or not message owner"},
        404: {"description": "Message not found"},
    },
)
async def delete_message(
    message_id: str,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> DeleteMessageResponse:
    """
    Soft delete a message.

    Only the sender can delete their own messages.
    Requires SEND_MESSAGES permission.
    """
    try:
        deleted = service.delete_message(
            message_id=message_id,
            user_id=current_user.id,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found",
            )

        return DeleteMessageResponse(
            success=True,
            message="Message deleted successfully",
        )

    except ForbiddenException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except HTTPException:
        raise  # Re-raise HTTPExceptions (like 404) as-is
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete message",
        )


@router.post(
    "/{message_id}/reactions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_permission(PermissionName.SEND_MESSAGES))],
    responses={
        204: {"description": "Reaction added"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
        404: {"description": "Message not found"},
    },
)
@rate_limit("10/minute", key_type=RateLimitKeyType.USER)
async def add_reaction(
    message_id: str,
    request: ReactionRequest,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> Response:
    """
    Add an emoji reaction to a message.

    Requires SEND_MESSAGES permission.
    Rate limited to 10 per minute.
    """
    try:
        service.add_reaction(message_id, current_user.id, request.emoji)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding reaction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add reaction"
        )


@router.delete(
    "/{message_id}/reactions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_permission(PermissionName.SEND_MESSAGES))],
    responses={
        204: {"description": "Reaction removed"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
    },
)
@rate_limit("10/minute", key_type=RateLimitKeyType.USER)
async def remove_reaction(
    message_id: str,
    request: ReactionRequest,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> Response:
    """
    Remove an emoji reaction from a message.

    Requires SEND_MESSAGES permission.
    Rate limited to 10 per minute.
    """
    try:
        service.remove_reaction(message_id, current_user.id, request.emoji)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing reaction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove reaction"
        )
