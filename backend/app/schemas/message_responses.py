from ._strict_base import StrictModel

# backend/app/schemas/message_responses.py
"""
Response schemas for the message/chat system.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field


class MessageSenderResponse(StrictModel):
    """Response schema for message sender info."""

    id: str
    first_name: str
    last_name: str
    email: str

    model_config = {"from_attributes": True}


class MessageResponse(StrictModel):
    """Response schema for a single message."""

    id: str
    booking_id: str
    sender_id: str
    content: str
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    delivered_at: Optional[datetime] = None
    edited_at: Optional[datetime] = None
    # Array of { user_id: str, read_at: datetime }
    read_by: Optional[List[Dict[str, Any]]] = None
    # Reactions summary: counts per emoji and the current user's reactions
    reactions: Optional[Dict[str, Any]] = None
    my_reactions: Optional[List[str]] = None
    sender: Optional[MessageSenderResponse] = None

    model_config = {"from_attributes": True}


class SendMessageResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response after sending a message."""

    success: bool = True
    message: MessageResponse


class MessagesHistoryResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for message history request."""

    booking_id: str
    messages: List[MessageResponse]
    limit: int
    offset: int
    has_more: bool


class UnreadCountResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for unread message count."""

    unread_count: int
    user_id: str


class MessageNotificationResponse(StrictModel):
    """Response schema for message notification."""

    id: str
    message_id: str
    user_id: str
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MarkMessagesReadResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response after marking messages as read."""

    success: bool = True
    messages_marked: int = Field(..., description="Number of messages marked as read")


class DeleteMessageResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response after deleting a message."""

    success: bool = True
    message: str = Field(default="Message deleted successfully", description="Success message")


class TypingStatusResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Response for typing indicator endpoints (empty body)."""

    success: bool = True


class MessageConfigResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Public config values for messaging UI."""

    edit_window_minutes: int


# Phase 3: Inbox state schemas
class OtherUserInfo(StrictModel):
    """Info about the other participant in a conversation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str
    name: str
    avatar_url: Optional[str] = None


class LastMessageInfo(StrictModel):
    """Preview information about the last message in a conversation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    preview: str
    at: datetime
    is_mine: bool


class StateCounts(StrictModel):
    """Counts of conversations by state."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    active: int
    archived: int
    trashed: int


class ConversationSummary(StrictModel):
    """Summary of a conversation for inbox display."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(..., description="Booking ID / conversation ID")
    type: str = Field(..., description="Conversation type (student or platform)")
    other_user: OtherUserInfo
    unread_count: int
    last_message: Optional[LastMessageInfo] = None


class InboxStateResponse(StrictModel):
    """Complete inbox state with all conversations and unread counts."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    conversations: List[ConversationSummary]
    total_unread: int
    unread_conversations: int = Field(
        ..., description="Count of conversations with unread messages (not total messages)"
    )
    state_counts: Optional[StateCounts] = Field(
        None, description="Count of conversations by state (active, archived, trashed)"
    )


class ConversationStateUpdateResponse(StrictModel):
    """Response for conversation state update."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    booking_id: str = Field(..., description="Booking/conversation ID")
    state: str = Field(..., description="New state (active, archived, or trashed)")
    state_changed_at: Optional[str] = Field(None, description="Timestamp of state change")
