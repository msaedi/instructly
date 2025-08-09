# backend/app/schemas/message_responses.py
"""
Response schemas for the message/chat system.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class MessageSenderResponse(BaseModel):
    """Response schema for message sender info."""

    id: int
    full_name: str
    email: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Response schema for a single message."""

    id: int
    booking_id: int
    sender_id: int
    content: str
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False
    delivered_at: Optional[datetime] = None
    edited_at: Optional[datetime] = None
    # Array of { user_id: int, read_at: datetime }
    read_by: Optional[List[dict]] = None
    # Reactions summary: counts per emoji and the current user's reactions
    reactions: Optional[dict] = None
    my_reactions: Optional[List[str]] = None
    sender: Optional[MessageSenderResponse] = None

    model_config = {"from_attributes": True}


class SendMessageResponse(BaseModel):
    """Response after sending a message."""

    success: bool = True
    message: MessageResponse


class MessagesHistoryResponse(BaseModel):
    """Response for message history request."""

    booking_id: int
    messages: List[MessageResponse]
    limit: int
    offset: int
    has_more: bool


class UnreadCountResponse(BaseModel):
    """Response for unread message count."""

    unread_count: int
    user_id: int


class MessageNotificationResponse(BaseModel):
    """Response schema for message notification."""

    id: int
    message_id: int
    user_id: int
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MarkMessagesReadResponse(BaseModel):
    """Response after marking messages as read."""

    success: bool = True
    messages_marked: int = Field(..., description="Number of messages marked as read")


class DeleteMessageResponse(BaseModel):
    """Response after deleting a message."""

    success: bool = True
    message: str = Field(default="Message deleted successfully", description="Success message")


class TypingStatusResponse(BaseModel):
    """Response for typing indicator endpoints (empty body)."""

    success: bool = True


class MessageConfigResponse(BaseModel):
    """Public config values for messaging UI."""

    edit_window_minutes: int
