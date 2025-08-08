# backend/app/routes/messages.py
"""
Message routes for real-time chat system.

Provides RESTful endpoints and Server-Sent Events (SSE) for real-time messaging
between instructors and students in bookings.

Key Features:
    - Real-time messaging via SSE (no polling)
    - Message history with pagination
    - Unread message counts and notifications
    - Rate limiting to prevent spam
    - RBAC permission checks

Router Endpoints:
    POST /send - Send a message to a booking chat
    GET /stream/{booking_id} - SSE endpoint for real-time messages
    GET /history/{booking_id} - Get paginated message history
    GET /unread-count - Get total unread message count
    POST /mark-read - Mark messages as read
    DELETE /{message_id} - Soft delete a message
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse

from ..api.dependencies.auth import get_current_active_user
from ..auth_sse import get_current_user_sse
from ..core.enums import PermissionName
from ..core.exceptions import ForbiddenException, NotFoundException, ValidationException
from ..database import get_db
from ..dependencies.permissions import require_permission
from ..middleware.rate_limiter import RateLimitKeyType, rate_limit
from ..models.user import User
from ..schemas.message_requests import MarkMessagesReadRequest, SendMessageRequest
from ..schemas.message_responses import (
    DeleteMessageResponse,
    MarkMessagesReadResponse,
    MessageResponse,
    MessagesHistoryResponse,
    SendMessageResponse,
    UnreadCountResponse,
)
from ..services.message_service import MessageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/messages", tags=["messages"])

# Store the notification service instance (will be injected at startup)
_notification_service = None


def set_notification_service(service):
    """Set the notification service instance (called at app startup)."""
    global _notification_service
    _notification_service = service


def get_notification_service():
    """Get the notification service instance."""
    if _notification_service is None:
        raise RuntimeError("Notification service not initialized")
    return _notification_service


def get_message_service(db=Depends(get_db)) -> MessageService:
    """Get message service instance."""
    return MessageService(db)


@router.post(
    "/send",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_permission(PermissionName.SEND_MESSAGES)),
    ],
)
@rate_limit("10/minute", key_type=RateLimitKeyType.USER)
async def send_message(
    request: SendMessageRequest,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
):
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


@router.get(
    "/stream/{booking_id}",
)
async def stream_messages(
    booking_id: int,
    current_user: User = Depends(get_current_user_sse),
    service: MessageService = Depends(get_message_service),
):
    """
    SSE endpoint for real-time message streaming.

    Establishes a Server-Sent Events connection for receiving
    real-time messages for a specific booking.

    Requires VIEW_MESSAGES permission.
    Note: Permission check is done manually since SSE endpoints
    can't use regular FastAPI dependencies with EventSource.
    """

    # Check if user has VIEW_MESSAGES permission using PermissionService
    from ..services.permission_service import PermissionService

    permission_service = PermissionService(service.db)
    if not permission_service.user_has_permission(current_user.id, PermissionName.VIEW_MESSAGES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view messages",
        )

    # Verify user has access to this booking
    try:
        if not service._user_has_booking_access(booking_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this booking",
            )
    except Exception as e:
        logger.error(f"Error checking booking access: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access check failed: {str(e)}",
        )

    async def event_generator():
        """Generate SSE events for the client."""
        queue = None
        heartbeat_task = None
        notification_service = None

        try:
            # Send initial connection confirmation
            yield {"event": "connected", "data": json.dumps({"booking_id": booking_id, "status": "connected"})}

            # Small delay to ensure connection is established
            await asyncio.sleep(0.1)

            # Try to get notification service (optional)
            try:
                notification_service = get_notification_service()
            except RuntimeError as e:
                logger.warning(f"Notification service not available: {str(e)}")
                notification_service = None

            # Subscribe to notifications if service available
            if notification_service:
                try:
                    queue = await notification_service.subscribe(booking_id)
                except Exception as e:
                    logger.warning(f"Failed to subscribe to notifications: {str(e)}")
                    queue = None

            # Start heartbeat task if notification service available
            if notification_service and queue:
                try:
                    heartbeat_task = asyncio.create_task(send_heartbeats(notification_service, booking_id))
                except Exception as e:
                    logger.warning(f"Failed to start heartbeat task: {str(e)}")
                    heartbeat_task = None

            # Main event loop
            last_heartbeat = datetime.now()

            while True:
                try:
                    if queue:
                        # Try to get message from queue with timeout
                        try:
                            message_data = await asyncio.wait_for(queue.get(), timeout=30.0)  # 30 second timeout

                            # Process the message
                            if message_data.get("type") == "heartbeat":
                                yield {
                                    "event": "heartbeat",
                                    "data": json.dumps({"timestamp": message_data.get("timestamp")}),
                                }
                            else:
                                # CRITICAL: Skip notifications for our own messages
                                # This prevents the sender from receiving their own messages via SSE
                                if message_data.get("sender_id") == current_user.id:
                                    continue  # Don't send our own messages back to us

                                # Add sender information and mark as not mine
                                message_data["is_mine"] = False
                                yield {
                                    "event": "message",
                                    "data": json.dumps(message_data),
                                }
                        except asyncio.TimeoutError:
                            # Timeout is normal - send keep-alive
                            yield {
                                "event": "keep-alive",
                                "data": json.dumps(
                                    {
                                        "status": "alive",
                                        "timestamp": str(datetime.now()),
                                    }
                                ),
                            }
                    else:
                        # No queue available, send periodic heartbeats
                        await asyncio.sleep(5)
                        now = datetime.now()
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
                    logger.error(f"Error in SSE stream for booking {booking_id}: {str(e)}")
                    # Small delay before continuing
                    await asyncio.sleep(1)
                    continue

        except asyncio.CancelledError:
            if heartbeat_task:
                heartbeat_task.cancel()
            raise
        except Exception as e:
            logger.error(f"Error in SSE generator for booking {booking_id}: {str(e)}")
            raise
        finally:
            # Clean up subscription
            if notification_service and queue:
                try:
                    await notification_service.unsubscribe(booking_id, queue)
                except Exception as e:
                    logger.error(f"Error during unsubscribe: {str(e)}")
            if heartbeat_task:
                try:
                    heartbeat_task.cancel()
                except Exception as e:
                    logger.error(f"Error cancelling heartbeat: {str(e)}")

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


async def send_heartbeats(notification_service, booking_id: int):
    """Send periodic heartbeats to keep connection alive."""
    while True:
        await asyncio.sleep(30)  # Send heartbeat every 30 seconds
        await notification_service.send_heartbeat(booking_id)


@router.get(
    "/history/{booking_id}",
    response_model=MessagesHistoryResponse,
    dependencies=[Depends(require_permission(PermissionName.VIEW_MESSAGES))],
)
async def get_message_history(
    booking_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
):
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


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    dependencies=[Depends(require_permission(PermissionName.VIEW_MESSAGES))],
)
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
):
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


@router.post(
    "/mark-read",
    response_model=MarkMessagesReadResponse,
    dependencies=[Depends(require_permission(PermissionName.VIEW_MESSAGES))],
)
async def mark_messages_as_read(
    request: MarkMessagesReadRequest,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
):
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


@router.delete(
    "/{message_id}",
    response_model=DeleteMessageResponse,
    dependencies=[Depends(require_permission(PermissionName.SEND_MESSAGES))],
)
async def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
):
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
    except Exception as e:
        logger.error(f"Error deleting message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete message",
        )
