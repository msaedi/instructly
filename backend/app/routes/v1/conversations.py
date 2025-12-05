# backend/app/routes/v1/conversations.py
"""
Conversations routes - API v1

Versioned conversation endpoints under /api/v1/conversations.
All business logic delegated to ConversationService.

Endpoints:
    GET /                               -> List user's conversations
    POST /                              -> Create/get conversation (pre-booking messaging)
    GET /{conversation_id}              -> Get conversation details
    GET /{conversation_id}/messages     -> Get messages with pagination
    POST /{conversation_id}/messages    -> Send a message
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...api.dependencies.auth import get_current_active_user
from ...database import get_db
from ...models.booking import Booking
from ...models.user import User
from ...ratelimit.dependency import rate_limit as new_rate_limit
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
    SendMessageRequest,
    SendMessageResponse,
    UserSummary,
)
from ...services.conversation_service import ConversationService

logger = logging.getLogger(__name__)

# V1 router - no prefix here, will be added when mounting in main.py
router = APIRouter(tags=["conversations-v1"])

ULID_PATH_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"


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
    dependencies=[Depends(new_rate_limit("read"))],
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
                content=last_msg.content[:100],  # Truncate for preview
                created_at=last_msg.created_at,
                is_from_me=last_msg.sender_id == current_user.id,
            )

        # Get upcoming bookings for this pair
        upcoming = service.get_upcoming_bookings_for_conversation(conv)
        next_booking = _build_booking_summary(upcoming[0]) if upcoming else None

        items.append(
            ConversationListItem(
                id=conv.id,
                other_user=_build_user_summary(other_user),
                last_message=last_message,
                unread_count=0,  # TODO: Implement unread count in Phase 3
                next_booking=next_booking,
                upcoming_booking_count=len(upcoming),
                state="active",  # TODO: Get from conversation_user_state in Phase 3
            )
        )

    return ConversationListResponse(
        conversations=items,
        next_cursor=next_cursor,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_conversation(
    conversation_id: str,
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
        state="active",  # TODO: Get from conversation_user_state in Phase 3
        created_at=conversation.created_at,
    )


@router.post(
    "",
    response_model=CreateConversationResponse,
    dependencies=[Depends(new_rate_limit("write"))],
)
def create_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
    db: Session = Depends(get_db),
) -> CreateConversationResponse:
    """
    Create a new conversation (for pre-booking messaging).

    If conversation already exists, returns the existing one.
    Only students can initiate conversations with instructors.
    """
    # The current user is the student, request contains instructor_id
    conversation, created = service.get_or_create_conversation(
        student_id=current_user.id,
        instructor_id=request.instructor_id,
    )

    # If initial message provided, send it
    if request.initial_message and created:
        service.send_message(
            conversation_id=conversation.id,
            sender_id=current_user.id,
            content=request.initial_message,
        )

    # Commit the transaction
    db.commit()

    return CreateConversationResponse(
        id=conversation.id,
        created=created,
    )


# =============================================================================
# Message Endpoints
# =============================================================================


@router.get(
    "/{conversation_id}/messages",
    response_model=MessagesResponse,
    dependencies=[Depends(new_rate_limit("read"))],
)
def get_messages(
    conversation_id: str,
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
    messages, has_more, next_cursor = service.get_messages(
        conversation_id=conversation_id,
        user_id=current_user.id,
        limit=limit,
        before_cursor=before,
        booking_id_filter=booking_id,
    )

    # If no messages and conversation doesn't exist, return 404
    if not messages and not service.get_conversation_by_id(conversation_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    items: List[MessageResponse] = []
    for msg in messages:
        # For system messages, include booking details if available
        booking_details = None
        if msg.booking_id and msg.message_type != "user":
            # TODO: Eager load booking details for system messages
            pass

        items.append(
            MessageResponse(
                id=msg.id,
                content=msg.content,
                sender_id=msg.sender_id,
                is_from_me=msg.sender_id == current_user.id,
                message_type=msg.message_type or "user",
                booking_id=msg.booking_id,
                booking_details=booking_details,
                created_at=msg.created_at,
                delivered_at=msg.delivered_at,
                read_by=msg.read_by or [],
            )
        )

    return MessagesResponse(
        messages=items,
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
    dependencies=[Depends(new_rate_limit("write"))],
)
def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    current_user: User = Depends(get_current_active_user),
    service: ConversationService = Depends(get_conversation_service),
    db: Session = Depends(get_db),
) -> SendMessageResponse:
    """
    Send a message in a conversation.

    Optionally specify a booking_id for explicit context.
    If not specified, auto-tags when exactly one upcoming booking exists.
    """
    message = service.send_message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=request.content,
        explicit_booking_id=request.booking_id,
    )

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Commit the transaction
    db.commit()

    return SendMessageResponse(
        id=message.id,
        created_at=message.created_at,
    )
