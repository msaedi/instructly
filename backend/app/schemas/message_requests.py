# backend/app/schemas/message_requests.py
"""
Request schemas for the message/chat system.
"""

from typing import List, Optional

from pydantic import Field, model_validator

from ._strict_base import StrictRequestModel


class MarkMessagesReadRequest(StrictRequestModel):
    """Request to mark messages as read."""

    conversation_id: Optional[str] = Field(
        None, description="Mark all messages in this conversation as read"
    )
    message_ids: Optional[List[str]] = Field(
        None, description="Specific message IDs to mark as read"
    )

    @model_validator(mode="after")
    def check_either_conversation_or_ids(self) -> "MarkMessagesReadRequest":
        """Ensure either conversation_id or message_ids is provided, but not both."""
        if not self.conversation_id and not self.message_ids:
            raise ValueError("Either conversation_id or message_ids must be provided")
        if self.conversation_id and self.message_ids:
            raise ValueError("Provide either conversation_id or message_ids, not both")
        return self


# Ensure models are fully built for FastAPI dependency resolution in tests.
MarkMessagesReadRequest.model_rebuild()
