from ._strict_base import StrictModel

# backend/app/schemas/message_responses.py
"""
Response schemas for the message/chat system.
"""

from pydantic import ConfigDict, Field


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


class MessageConfigResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Public config values for messaging UI."""

    edit_window_minutes: int


class UnreadCountResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    """Unread message count for a user."""

    unread_count: int
    user_id: str
