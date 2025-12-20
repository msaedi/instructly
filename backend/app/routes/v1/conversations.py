# backend/app/routes/v1/conversations.py
"""
Conversations routes - API v1

Versioned conversation endpoints under /api/v1/conversations.
All business logic delegated to ConversationService.

Routes have ZERO direct DB access - all operations go through service layer.

Endpoints:
    GET /                               -> List user's conversations
    POST /                              -> Create/get conversation (pre-booking messaging)
    GET /{conversation_id}              -> Get conversation details
    GET /{conversation_id}/messages     -> Get messages with pagination
    POST /{conversation_id}/messages    -> Send a message
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.params import Path
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...database import get_db
from ...models.booking import Booking
from ...models.user import User
from ...ratelimit.dependency import rate_limit as new_rate_limit
from ...schemas.base_responses import SuccessResponse
from ...schemas.conversation import (
    BookingSummary,
    ConversationDetail,
    ConversationListItem,
    ConversationListResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    LastMessage,
    MessageResponse,
    MessagesResponse,
    ReactionInfo,
    ReadReceiptEntry,
    SendMessageRequest,
    SendMessageResponse,
    TypingRequest,
    UpdateConversationStateRequest,
    UpdateConversationStateResponse,
    UserSummary,
)
from ...services.conversation_service import ConversationService
from ...services.messaging import publish_new_message_direct, publish_typing_status_direct

logger = logging.getLogger(__name__)


def _safe_truncate(text: str, max_length: int) -> str:
    """
    Truncate text safely without breaking multi-byte Unicode characters.

    Python's str[:n] slicing is character-based (not byte-based), so it won't
    break mid-character. However, we add ellipsis if truncated for better UX.
    """
    if len(text) <= max_length:
        return text
    # Truncate and add ellipsis
    return text[: max_length - 1] + "…"


# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["conversations-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"
WRITE_DEP = Depends(new_rate_limit("write"))
READ_DEP = Depends(new_rate_limit("read"))


async def enforce_conversation_rate_limit(
    request: Request,
    response: Response,
    conversation_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Apply conversation-scoped rate limiting for message sends."""
    original_identity = getattr(request.state, "rate_identity", None)
    request.state.rate_identity = f"user:{current_user.id}:conv:{conversation_id}"
    try:
        await new_rate_limit("conv_msg")(request, response)
    finally:
        if original_identity is not None:
            request.state.rate_identity = original_identity


def get_conversation_service(db: Session = Depends(get_db)) -> ConversationService:
    """Dependency for ConversationService."""
    return ConversationService(db)


def _build_user_summary(user: User) -> UserSummary:
    """Build UserSummary from User model."""
    return UserSummary(
        id=user.id,
        first_name=user.first_name or "",
        last_initial=(user.last_name or " ")[0] if user.last_name else "",
        profile_photo_url=getattr(user, "profile_photo_url", None),
    )


def _build_booking_summary(booking: Booking) -> BookingSummary:
    """Build BookingSummary from Booking model."""
    # Get service name from the relationship
    service_name = "Lesson"
    if booking.instructor_service and booking.instructor_service.name:
        service_name = booking.instructor_service.name

    # Format start_time
    start_time_str = str(booking.start_time)
    if hasattr(booking.start_time, "strftime"):
        start_time_str = booking.start_time.strftime("%H:%M")
    elif isinstance(booking.start_time, str):
        # If it's already a string, take first 5 chars (HH:MM)
        start_time_str = booking.start_time[:5]

    return BookingSummary(
        id=booking.id,
        date=booking.booking_date.isoformat(),
        start_time=start_time_str,
        service_name=service_name,
    )


# =============================================================================
# Conversation List Endpoints
# =============================================================================


@router.get(
    "",
    response_model=ConversationListResponse,
    dependencies=[READ_DEP],
)
def list_conversations(
    state: Optional[str] = Query(None, pattern="^(active|archived|trashed)$"),
    limit: int = Query(20, ge=1, le=50),
    cursor: Optional[str] = Query(None, description="Pagination cursor (ISO timestamp)"),
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """
    List all conversations for the current user.

    Returns one entry per conversation partner, sorted by most recent message.
    """
    conversations, next_cursor = service.list_conversations_for_user(
        user_id=current_user.id,
        state_filter=state,
        limit=limit,
        cursor=cursor,
    )

    # Batch load all context data to avoid N+1 queries (3 queries instead of 3*N)
    conv_ids = [c.id for c in conversations]
    upcoming_by_conv = service.batch_get_upcoming_bookings(conversations, current_user.id)
    states_by_conv = service.batch_get_states(conv_ids, current_user.id)
    unread_by_conv = service.batch_get_unread_counts(conv_ids, current_user.id)

    items: List[ConversationListItem] = []
    for conv in conversations:
        # Get the other participant
        other_user = conv.student if conv.instructor_id == current_user.id else conv.instructor
        if not other_user:
            # Skip conversations with missing user data
            continue

        # Build last message preview
        last_message = None
        if conv.messages:
            # Get most recent message (assuming messages are ordered by created_at)
            last_msg = sorted(conv.messages, key=lambda m: m.created_at)[-1]
            last_message = LastMessage(
                content=_safe_truncate(last_msg.content, 100),  # Unicode-safe truncate
                created_at=last_msg.created_at,
                is_from_me=last_msg.sender_id == current_user.id,
            )

        # Get batch-loaded context
        upcoming = upcoming_by_conv.get(conv.id, [])
        next_booking = _build_booking_summary(upcoming[0]) if upcoming else None
        state_value = states_by_conv.get(conv.id, "active")
        unread_count = unread_by_conv.get(conv.id, 0)

        items.append(
            ConversationListItem(
                id=conv.id,
                other_user=_build_user_summary(other_user),
                last_message=last_message,
                unread_count=unread_count,
                next_booking=next_booking,
                upcoming_bookings=[_build_booking_summary(b) for b in upcoming],
                upcoming_booking_count=len(upcoming),
                state=state_value,
            )
        )

    return ConversationListResponse(
        conversations=items,
        next_cursor=next_cursor,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    dependencies=[READ_DEP],
)
def get_conversation(
    conversation_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationDetail:
    """
    Get details for a single conversation.
    """
    conversation = service.get_conversation_by_id(conversation_id, current_user.id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Get the other participant
    other_user = (
        conversation.student
        if conversation.instructor_id == current_user.id
        else conversation.instructor
    )
    if not other_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation participant not found"
        )

    # Get upcoming bookings
    upcoming = service.get_upcoming_bookings_for_conversation(conversation)

    return ConversationDetail(
        id=conversation.id,
        other_user=_build_user_summary(other_user),
        next_booking=_build_booking_summary(upcoming[0]) if upcoming else None,
        upcoming_bookings=[_build_booking_summary(b) for b in upcoming],
        state=service.get_conversation_user_state(conversation.id, current_user.id),
        created_at=conversation.created_at,
    )


@router.post(
    "",
    response_model=CreateConversationResponse,
    dependencies=[WRITE_DEP],
)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
) -> CreateConversationResponse:
    """
    Create a new conversation (for pre-booking messaging).

    If conversation already exists, returns the existing one.
    Only students can initiate conversations with instructors.
    """
    # Service handles validation, creation, initial message, and transaction commit
    result = await asyncio.to_thread(
        service.create_conversation_with_message,
        student_id=current_user.id,
        instructor_id=request.instructor_id,
        initial_message=request.initial_message,
    )

    if not result.success:
        if result.error == "Instructor not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result.error,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error,
        )

    return CreateConversationResponse(
        id=result.conversation_id,
        created=result.created,
    )


@router.put(
    "/{conversation_id}/state",
    dependencies=[WRITE_DEP],
    response_model=UpdateConversationStateResponse,
)
def update_conversation_state(
    request: UpdateConversationStateRequest,
    conversation_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
) -> UpdateConversationStateResponse:
    """Update per-user conversation state (active/archived/trashed)."""
    conversation = service.get_conversation_by_id(conversation_id, current_user.id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Note: get_conversation_by_id already verifies user is a participant

    try:
        service.set_conversation_user_state(conversation_id, current_user.id, request.state)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return UpdateConversationStateResponse(id=conversation_id, state=request.state)


# =============================================================================
# Message Endpoints
# =============================================================================


@router.post(
    "/{conversation_id}/typing",
    dependencies=[WRITE_DEP],
    response_model=SuccessResponse,
)
async def send_typing_indicator(
    request: TypingRequest,
    conversation_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
) -> SuccessResponse:
    """Send typing indicator for a conversation."""
    # Get typing context (participant IDs) via service
    typing_context = await asyncio.to_thread(
        service.get_typing_context, conversation_id, current_user.id
    )
    if not typing_context:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    user_name = current_user.first_name or current_user.email or "Someone"

    try:
        # Use direct publish function (no DB required)
        await publish_typing_status_direct(
            participant_ids=typing_context.participant_ids,
            conversation_id=conversation_id,
            user_id=str(current_user.id),
            user_name=user_name,
            is_typing=request.is_typing,
        )
    except Exception as exc:  # best effort
        logger.error("[REDIS-PUBSUB] Failed to publish typing status", extra={"error": str(exc)})

    return SuccessResponse(success=True, message="Typing status sent")


@router.get(
    "/{conversation_id}/messages",
    response_model=MessagesResponse,
    dependencies=[READ_DEP],
)
async def get_messages(
    conversation_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    limit: int = Query(50, ge=1, le=100),
    before: Optional[str] = Query(None, description="Cursor for pagination (message ID)"),
    booking_id: Optional[str] = Query(None, description="Filter by booking ID"),
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
) -> MessagesResponse:
    """
    Get messages for a conversation with pagination.

    Messages are returned in chronological order (oldest first).
    Use 'before' cursor to load older messages.
    """
    # Service returns all data including booking details (no direct repo access needed)
    result = await asyncio.to_thread(
        service.get_messages_with_details,
        conversation_id=conversation_id,
        user_id=current_user.id,
        limit=limit,
        before_cursor=before,
        booking_id_filter=booking_id,
    )

    if not result.conversation_found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Transform service data to response schema
    items: List[MessageResponse] = []
    for msg_data in result.messages:
        # Build booking summary if present
        booking_details = None
        if msg_data.booking_details:
            booking_details = BookingSummary(
                id=msg_data.booking_details["id"],
                date=msg_data.booking_details["date"],
                start_time=msg_data.booking_details["start_time"],
                service_name=msg_data.booking_details["service_name"],
            )

        # Transform to response schemas
        read_by_entries = [
            ReadReceiptEntry(user_id=r["user_id"], read_at=r.get("read_at", ""))
            for r in msg_data.read_by
        ]
        reaction_list = [
            ReactionInfo(user_id=r["user_id"], emoji=r["emoji"]) for r in msg_data.reactions
        ]

        items.append(
            MessageResponse(
                id=msg_data.id,
                conversation_id=conversation_id,
                content=msg_data.content,
                sender_id=msg_data.sender_id,
                is_from_me=msg_data.sender_id == current_user.id,
                message_type=msg_data.message_type,
                booking_id=msg_data.booking_id,
                booking_details=booking_details,
                created_at=msg_data.created_at,
                edited_at=msg_data.edited_at,
                is_deleted=msg_data.is_deleted,
                delivered_at=msg_data.delivered_at,
                read_by=read_by_entries,
                reactions=reaction_list,
            )
        )

    return MessagesResponse(
        messages=items,
        has_more=result.has_more,
        next_cursor=result.next_cursor,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
    dependencies=[WRITE_DEP, Depends(enforce_conversation_rate_limit)],
)
async def send_message(
    request: SendMessageRequest,
    conversation_id: str = Path(..., pattern=ULID_PATH_PATTERN),
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
) -> SendMessageResponse:
    """
    Send a message in a conversation.

    Optionally specify a booking_id for explicit context.
    If not specified, auto-tags when exactly one upcoming booking exists.
    """
    # Service handles creation, transaction commit, and returns publish context
    result = await asyncio.to_thread(
        service.send_message_with_context,
        conversation_id,
        current_user.id,
        request.content,
        request.booking_id,
    )

    if not result.message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    message = result.message

    # Publish SSE event using direct function (no DB required)
    try:
        await publish_new_message_direct(
            participant_ids=result.participant_ids,
            message_id=str(message.id),
            content=message.content,
            sender_id=str(current_user.id),
            sender_name=f"{current_user.first_name or ''} {current_user.last_name or ''}".strip()
            or current_user.email,
            conversation_id=conversation_id,
            created_at=message.created_at,
            booking_id=message.booking_id,
            delivered_at=message.delivered_at,
            message_type=message.message_type,
        )
        logger.debug(
            "[REDIS-PUBSUB] Conversation message published",
            extra={"message_id": message.id, "conversation_id": conversation_id},
        )
    except Exception as e:
        # Fire-and-forget: log but don't fail the request
        logger.error(
            "[REDIS-PUBSUB] Failed to publish conversation message",
            extra={"error": str(e), "message_id": message.id},
        )

    return SendMessageResponse(
        id=message.id,
        created_at=message.created_at,
    )
