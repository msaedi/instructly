# backend/app/schemas/conversation.py
"""
Pydantic schemas for conversation API.

Provides request/response models for the per-user-pair conversation endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserSummary(BaseModel):
    """Minimal user info for conversation list."""

    id: str
    first_name: str
    last_initial: str
    profile_photo_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BookingSummary(BaseModel):
    """Minimal booking info shown in conversation context."""

    id: str
    date: str  # YYYY-MM-DD format
    start_time: str  # HH:MM format
    service_name: str

    model_config = ConfigDict(from_attributes=True)


class LastMessage(BaseModel):
    """Preview of the last message in a conversation."""

    content: str
    created_at: datetime
    is_from_me: bool


class ConversationListItem(BaseModel):
    """Single conversation in the inbox list."""

    id: str
    other_user: UserSummary
    last_message: Optional[LastMessage] = None
    unread_count: int = 0
    next_booking: Optional[BookingSummary] = None
    upcoming_booking_count: int = 0
    state: str = "active"  # active | archived | trashed

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """Response for GET /conversations."""

    conversations: List[ConversationListItem]
    next_cursor: Optional[str] = None


class ConversationDetail(BaseModel):
    """Full conversation details."""

    id: str
    other_user: UserSummary
    next_booking: Optional[BookingSummary] = None
    upcoming_bookings: List[BookingSummary] = Field(default_factory=list)
    state: str = "active"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Single message in a conversation."""

    id: str
    content: str
    sender_id: Optional[str] = None  # None for system messages
    is_from_me: bool
    message_type: str  # 'user' | 'system_booking_created' | etc
    booking_id: Optional[str] = None
    booking_details: Optional[BookingSummary] = None  # For system messages
    created_at: datetime
    delivered_at: Optional[datetime] = None
    read_by: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MessagesResponse(BaseModel):
    """Response for GET /conversations/{id}/messages."""

    messages: List[MessageResponse]
    has_more: bool = False
    next_cursor: Optional[str] = None


class CreateConversationRequest(BaseModel):
    """Request to create a pre-booking conversation."""

    instructor_id: str
    initial_message: Optional[str] = None  # Optional first message


class CreateConversationResponse(BaseModel):
    """Response for POST /conversations."""

    id: str
    created: bool  # False if conversation already existed


class SendMessageRequest(BaseModel):
    """Request to send a message."""

    content: str = Field(..., min_length=1, max_length=1000)
    booking_id: Optional[str] = None  # Optional explicit booking context


class SendMessageResponse(BaseModel):
    """Response for POST /conversations/{id}/messages."""

    id: str
    created_at: datetime
