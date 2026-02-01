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
    GET /stream - SSE endpoint for per-user real-time messages
    GET /config - Get message configuration (edit window, etc.)
    GET /unread-count - Get total unread count for current user
    POST /mark-read - Mark messages as read by conversation or IDs

    === Message-specific Routes ===
    PATCH /{message_id} - Edit a message
    DELETE /{message_id} - Soft delete a message
    POST /{message_id}/reactions - Add emoji reaction
    DELETE /{message_id}/reactions - Remove emoji reaction
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
import logging
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ...api.dependencies.auth import get_current_active_user
from ...auth_sse import get_current_user_sse
from ...core.auth_cache import user_has_cached_permission
from ...core.config import settings
from ...core.enums import PermissionName
from ...core.exceptions import ForbiddenException, NotFoundException, ValidationException
from ...core.request_context import set_request_id
from ...database import SessionLocal, get_db
from ...dependencies.permissions import require_permission
from ...middleware.rate_limiter import RateLimitKeyType, rate_limit
from ...models.user import User
from ...schemas.message_requests import MarkMessagesReadRequest
from ...schemas.message_responses import (
    DeleteMessageResponse,
    MarkMessagesReadResponse,
    MessageConfigResponse,
    UnreadCountResponse,
)
from ...services.message_service import MessageService, SSEStreamContext

# Redis Pub/Sub (v3.1 - Redis is the ONLY notification source)
# NOTE: Using *_direct versions for proper architecture - routes don't need DB access
from ...services.messaging import (
    create_sse_stream,
    ensure_db_health,
    publish_message_deleted_direct,
    publish_message_edited_direct,
    publish_reaction_update_direct,
    publish_read_receipt_direct,
)

# Ensure request schema is fully built before FastAPI inspects annotations.
MarkMessagesReadRequest.model_rebuild()

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["messages-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


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


# openapi-exempt: SSE stream cannot have JSON response schema
@router.get(
    "/stream",
    responses={
        200: {"description": "SSE stream established for user's inbox"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
        429: {"description": "Too many connection attempts"},
    },
)
@rate_limit("5/minute", key_type=RateLimitKeyType.USER)
async def stream_user_messages(
    request: Request,
    current_user: User = Depends(get_current_user_sse),
) -> EventSourceResponse:
    """
    SSE endpoint for real-time message streaming - per-user inbox (v4.0).

    Establishes a Server-Sent Events connection for receiving
    real-time messages across ALL user's conversations.

    Architecture (v4.0 with Broadcaster):
    - Single Redis PubSub connection shared across all SSE clients per worker
    - Enables 500+ concurrent SSE users instead of ~30 with per-connection pattern
    - Proper async waiting (no busy-wait polling)

    Features:
    - Redis Pub/Sub via Broadcaster (fan-out multiplexer)
    - Last-Event-ID support for automatic catch-up on reconnect
    - new_message events include SSE id: field
    - Heartbeat every 10 seconds
    - DB session explicitly closed before streaming (prevents idle_in_transaction)

    Supports Last-Event-ID header - when reconnecting, the client
    automatically sends the last received message ID, and the server
    sends any missed messages from the database.

    Requires VIEW_MESSAGES permission.
    """
    # SSE streams bypass the normal request lifecycle (middleware runs once at start,
    # but the connection persists). We manually set request_id here so logs during
    # the long-lived stream are correlated. This also sets X-Request-ID response header.
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    if not hasattr(request, "state"):
        request.state = SimpleNamespace()
    request.state.request_id = request_id
    set_request_id(request_id)

    # Log SSE connection attempt
    logger.info(
        "[SSE] Connection attempt",
        extra={
            "user_id": current_user.id,
            "user_email": current_user.email,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    # =========================================================================
    # PHASE 1: DB OPERATIONS (via service layer with manual session)
    #
    # CRITICAL: We use manual session management here instead of Depends(get_db)
    # because FastAPI's dependency cleanup only runs AFTER the response completes.
    # For SSE streams that run 30+ seconds, this would hold DB connections in
    # "idle in transaction" state, exhausting the connection pool.
    #
    # By manually closing the session BEFORE returning EventSourceResponse,
    # we ensure DB connections are released immediately after the initial queries.
    # =========================================================================

    user_id = current_user.id
    last_event_id = request.headers.get("Last-Event-ID")

    # Check permission using cached data (no DB query for transient users)
    # This avoids the redundant user lookup that was happening in get_stream_context
    cached_has_permission = user_has_cached_permission(current_user, PermissionName.VIEW_MESSAGES)

    # Service layer handles missed message fetch (permission pre-checked above)
    db = SessionLocal()
    try:
        await ensure_db_health(db)
        message_service = MessageService(db)
        context: SSEStreamContext = await asyncio.to_thread(
            message_service.get_stream_context,
            user_id=current_user.id,
            last_event_id=last_event_id,
            has_permission=cached_has_permission,  # Pass pre-computed permission
        )
    finally:
        # CRITICAL: Explicitly rollback and close DB session BEFORE starting the SSE stream.
        # Rollback is needed because autocommit=False means a transaction was started.
        # Without rollback, the connection returns to the pool in "idle in transaction" state,
        # which Supabase will kill after its idle_in_transaction_session_timeout.
        # async-blocking-ignore: SSE cleanup <1ms
        db.rollback()  # db-access-ok: SSE requires explicit session cleanup to prevent idle-in-transaction  # async-blocking-ignore
        db.close()  # db-access-ok: SSE requires explicit session close
        logger.debug(
            "[SSE] DB session closed before streaming",
            extra={"user_id": user_id},
        )

    # Check permission result from service
    if not context.has_permission:
        logger.warning(
            "[SSE] Permission denied",
            extra={"user_id": current_user.id, "permission": "VIEW_MESSAGES"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view messages",
        )

    # Log reconnection info if applicable
    if last_event_id:
        logger.info(
            "[SSE] Client reconnecting with Last-Event-ID",
            extra={
                "user_id": current_user.id,
                "last_event_id": last_event_id,
                "missed_count": len(context.missed_messages),
            },
        )

    # =========================================================================
    # PHASE 2: SSE STREAM (DB-free, via Broadcaster)
    # At this point, the DB session is closed. The stream runs purely via
    # the shared Broadcaster connection (1 Redis connection per worker).
    # =========================================================================

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        """Generate SSE events using Broadcaster multiplexer (no DB access)."""
        async for event in create_sse_stream(
            user_id=user_id,
            missed_messages=context.missed_messages,
        ):
            # Early exit if client disconnected
            if await request.is_disconnected():
                logger.info(
                    "[SSE] Client disconnected, stopping stream",
                    extra={"user_id": user_id},
                )
                break
            yield event

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
            "X-Request-ID": request_id,
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
        count = await asyncio.to_thread(service.get_unread_count, current_user.id)

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
    responses={
        200: {"description": "Messages marked as read"},
        400: {"description": "Validation error"},
        401: {"description": "Not authenticated"},
        403: {"description": "Permission denied"},
        422: {"description": "Either conversation_id or message_ids must be provided"},
    },
)
async def mark_messages_as_read(
    request: MarkMessagesReadRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    service: MessageService = Depends(get_message_service),
) -> MarkMessagesReadResponse:
    """
    Mark messages as read.

    Can mark specific messages or all messages in a conversation.
    Requires VIEW_MESSAGES permission.
    """
    try:
        if not request.conversation_id and not request.message_ids:
            raise ValidationException("Either conversation_id or message_ids must be provided")

        # Single service call that returns all data needed (no direct DB access)
        result = await asyncio.to_thread(
            service.mark_messages_read_with_context,
            request.conversation_id,
            request.message_ids,
            current_user.id,
        )

        # Redis Pub/Sub publishing (fire-and-forget) - using direct function (no DB needed)
        if result.count > 0 and result.marked_message_ids:
            if result.conversation_id and result.participant_ids:
                try:
                    await publish_read_receipt_direct(
                        participant_ids=result.participant_ids,
                        conversation_id=result.conversation_id,
                        reader_id=str(current_user.id),
                        message_ids=result.marked_message_ids,
                    )
                    logger.debug(
                        "[REDIS-PUBSUB] Mark-read: Published to Redis",
                        extra={
                            "message_count": len(result.marked_message_ids),
                            "conversation_id": result.conversation_id,
                        },
                    )
                except Exception as e:
                    logger.error(
                        "[REDIS-PUBSUB] Mark-read: Redis publish failed",
                        extra={"error": str(e), "conversation_id": result.conversation_id},
                    )
            else:
                logger.warning(
                    "[REDIS-PUBSUB] Mark-read: Could not resolve conversation_id for SSE routing",
                    extra={"message_ids": result.marked_message_ids[:3]},
                )

        return MarkMessagesReadResponse(
            success=True,
            messages_marked=result.count,
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


# ============================================================================
# SECTION 2: Message-specific routes (with {message_id} parameter)
# These must come LAST to avoid capturing static routes
# ============================================================================


# openapi-exempt: 204 No Content - no response body
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
    # [MSG-DEBUG] Log edit attempt
    logger.info(
        "[MSG-DEBUG] Message EDIT: Request received",
        extra={
            "user_id": current_user.id,
            "message_id": message_id,
            "new_content_length": len(request.content) if request.content else 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        # Single service call that returns all data needed (no direct DB access)
        result = await asyncio.to_thread(
            service.edit_message_with_context,
            message_id,
            current_user.id,
            request.content,
        )

        logger.info(
            "[MSG-DEBUG] Message EDIT: Success",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Redis Pub/Sub publishing (fire-and-forget) - using direct function (no DB needed)
        if result.conversation_id and result.participant_ids:
            try:
                await publish_message_edited_direct(
                    participant_ids=result.participant_ids,
                    conversation_id=result.conversation_id,
                    message_id=message_id,
                    new_content=request.content,
                    editor_id=str(current_user.id),
                    edited_at=result.edited_at or datetime.now(timezone.utc),
                )
                logger.debug(
                    "[REDIS-PUBSUB] Message EDIT: Published to Redis",
                    extra={"message_id": message_id, "conversation_id": result.conversation_id},
                )
            except Exception as e:
                logger.error(
                    "[REDIS-PUBSUB] Message EDIT: Redis publish failed",
                    extra={"error": str(e), "message_id": message_id},
                )
        else:
            logger.warning(
                "[REDIS-PUBSUB] Message EDIT: Could not resolve conversation_id",
                extra={"message_id": message_id},
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValidationException as e:
        logger.warning(
            "[MSG-DEBUG] Message EDIT: Validation error",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenException as e:
        logger.warning(
            "[MSG-DEBUG] Message EDIT: Forbidden",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundException as e:
        logger.warning(
            "[MSG-DEBUG] Message EDIT: Not found",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "[MSG-DEBUG] Message EDIT: Unexpected error",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
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
        # Single service call that returns all data needed (no direct DB access)
        result = await asyncio.to_thread(
            service.delete_message_with_context,
            message_id,
            current_user.id,
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Message not found",
            )

        # Redis Pub/Sub publishing (fire-and-forget) - using direct function (no DB needed)
        if result.conversation_id and result.participant_ids:
            try:
                await publish_message_deleted_direct(
                    participant_ids=result.participant_ids,
                    conversation_id=result.conversation_id,
                    message_id=message_id,
                    deleted_by=str(current_user.id),
                )
                logger.debug(
                    "[REDIS-PUBSUB] Message DELETE: Published to Redis",
                    extra={"message_id": message_id, "conversation_id": result.conversation_id},
                )
            except Exception as e:
                logger.error(
                    "[REDIS-PUBSUB] Message DELETE: Redis publish failed",
                    extra={"error": str(e), "message_id": message_id},
                )
        else:
            logger.warning(
                "[REDIS-PUBSUB] Message DELETE: Could not resolve conversation_id",
                extra={"message_id": message_id},
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
    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
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


# openapi-exempt: 204 No Content - no response body
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
    # [MSG-DEBUG] Log reaction add attempt
    logger.info(
        "[MSG-DEBUG] Reaction ADD: Request received",
        extra={
            "user_id": current_user.id,
            "message_id": message_id,
            "emoji": request.emoji,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        # Single service call that returns all data needed (no direct DB access)
        result = await asyncio.to_thread(
            service.add_reaction_with_context,
            message_id,
            current_user.id,
            request.emoji,
        )

        logger.info(
            "[MSG-DEBUG] Reaction ADD: Success",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "emoji": request.emoji,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Redis Pub/Sub publishing (fire-and-forget) - using direct function (no DB needed)
        if result.conversation_id and result.participant_ids and result.action:
            try:
                await publish_reaction_update_direct(
                    participant_ids=result.participant_ids,
                    conversation_id=result.conversation_id,
                    message_id=message_id,
                    user_id=str(current_user.id),
                    emoji=request.emoji,
                    action=result.action,
                )
                logger.debug(
                    "[REDIS-PUBSUB] Reaction ADD: Published to Redis",
                    extra={"message_id": message_id, "conversation_id": result.conversation_id},
                )
            except Exception as e:
                logger.error(
                    "[REDIS-PUBSUB] Reaction ADD: Redis publish failed",
                    extra={"error": str(e), "message_id": message_id},
                )
        else:
            logger.warning(
                "[REDIS-PUBSUB] Reaction ADD: Could not resolve conversation_id",
                extra={"message_id": message_id},
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ForbiddenException as e:
        logger.warning(
            "[MSG-DEBUG] Reaction ADD: Forbidden",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundException as e:
        logger.warning(
            "[MSG-DEBUG] Reaction ADD: Not found",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "[MSG-DEBUG] Reaction ADD: Unexpected error",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add reaction"
        )


# openapi-exempt: 204 No Content - no response body
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
    # [MSG-DEBUG] Log reaction remove attempt
    logger.info(
        "[MSG-DEBUG] Reaction REMOVE: Request received",
        extra={
            "user_id": current_user.id,
            "message_id": message_id,
            "emoji": request.emoji,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        # Single service call that returns all data needed (no direct DB access)
        result = await asyncio.to_thread(
            service.remove_reaction_with_context,
            message_id,
            current_user.id,
            request.emoji,
        )

        logger.info(
            "[MSG-DEBUG] Reaction REMOVE: Success",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "emoji": request.emoji,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Redis Pub/Sub publishing (fire-and-forget) - using direct function (no DB needed)
        if result.conversation_id and result.participant_ids:
            try:
                await publish_reaction_update_direct(
                    participant_ids=result.participant_ids,
                    conversation_id=result.conversation_id,
                    message_id=message_id,
                    user_id=str(current_user.id),
                    emoji=request.emoji,
                    action="removed",
                )
                logger.debug(
                    "[REDIS-PUBSUB] Reaction REMOVE: Published to Redis",
                    extra={"message_id": message_id, "conversation_id": result.conversation_id},
                )
            except Exception as e:
                logger.error(
                    "[REDIS-PUBSUB] Reaction REMOVE: Redis publish failed",
                    extra={"error": str(e), "message_id": message_id},
                )
        else:
            logger.warning(
                "[REDIS-PUBSUB] Reaction REMOVE: Could not resolve conversation_id",
                extra={"message_id": message_id},
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ForbiddenException as e:
        logger.warning(
            "[MSG-DEBUG] Reaction REMOVE: Forbidden",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NotFoundException as e:
        logger.warning(
            "[MSG-DEBUG] Reaction REMOVE: Not found",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "[MSG-DEBUG] Reaction REMOVE: Unexpected error",
            extra={
                "user_id": current_user.id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove reaction"
        )
