# backend/app/schemas/message_requests.py
"""
Request schemas for the message/chat system.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class SendMessageRequest(BaseModel):
    """Request to send a message."""

    booking_id: int = Field(..., description="ID of the booking")
    content: str = Field(..., min_length=1, max_length=1000, description="Message content")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()


class MarkMessagesReadRequest(BaseModel):
    """Request to mark messages as read."""

    booking_id: Optional[int] = Field(None, description="Mark all messages in this booking as read")
    message_ids: Optional[List[int]] = Field(None, description="Specific message IDs to mark as read")

    @field_validator("message_ids")
    @classmethod
    def validate_message_ids(cls, v: Optional[List[int]], values) -> Optional[List[int]]:
        """Ensure either booking_id or message_ids is provided."""
        booking_id = values.data.get("booking_id")
        if not booking_id and not v:
            raise ValueError("Either booking_id or message_ids must be provided")
        if booking_id and v:
            raise ValueError("Provide either booking_id or message_ids, not both")
        return v
