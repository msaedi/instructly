"""Message mutation operations, including reactions, edits, and deletes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, cast

from sqlalchemy.exc import IntegrityError

from ...core.exceptions import NotFoundException, RepositoryException
from ...models.conversation import Conversation
from ...models.message import Message, MessageEdit, MessageReaction
from .mixin_base import MessageRepositoryMixinBase


class MessageMutationMixin(MessageRepositoryMixinBase):
    """Message mutation operations, including reactions, edits, and deletes."""

    def has_user_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        """Check if a user has already reacted with emoji to a message."""
        try:
            exists = (
                self.db.query(MessageReaction)
                .filter(
                    MessageReaction.message_id == message_id,
                    MessageReaction.user_id == user_id,
                    MessageReaction.emoji == emoji,
                )
                .first()
            )
            return exists is not None
        except Exception as e:
            self.logger.error("Error checking reaction existence: %s", str(e))
            raise RepositoryException(f"Failed to check reaction existence: {str(e)}")

    def apply_message_edit(self, message_id: str, new_content: str) -> Optional[datetime]:
        """
        Create a MessageEdit history row and update the Message content and edited_at.

        Returns the edited_at timestamp if successful, None if message not found.
        """
        try:
            message = self.db.query(Message).filter(Message.id == message_id).first()
            if not message:
                return None
            self.db.add(MessageEdit(message_id=message_id, original_content=message.content))
            message.content = new_content
            edited_at = datetime.now(timezone.utc)
            message.edited_at = edited_at
            return edited_at
        except Exception as e:
            self.logger.error("Error applying message edit: %s", str(e))
            raise RepositoryException(f"Failed to apply message edit: {str(e)}")

    def soft_delete_message(self, message_id: str, user_id: str) -> Optional[Message]:
        """Soft delete a message by marking deletion metadata."""
        try:
            message = cast(
                Optional[Message],
                self.db.query(Message).filter(Message.id == message_id).first(),
            )
            if not message:
                return None

            message.is_deleted = True
            now = datetime.now(timezone.utc)
            message.deleted_at = now
            message.deleted_by = user_id
            message.updated_at = now
            # Persist deletion flags before recomputing visible-message aggregates.
            self.db.flush()
            conversation = cast(
                Optional[Conversation],
                self.db.query(Conversation)
                .filter(Conversation.id == message.conversation_id)
                .first(),
            )
            if not conversation:
                raise RepositoryException(
                    f"Conversation not found for message {message_id}: {message.conversation_id}"
                )

            conversation.last_message_at = self.get_last_message_at_for_conversation(
                str(message.conversation_id)
            )
            conversation.updated_at = now
            self.db.flush()
            self.logger.info("Soft deleted message %s by user %s", message_id, user_id)
            return message

        except Exception as e:
            self.logger.error("Error deleting message: %s", str(e))
            raise RepositoryException(f"Failed to delete message: {str(e)}")

    def add_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        """Add a reaction, treating duplicate inserts as idempotent success."""
        try:
            if not self.db.query(Message).filter(Message.id == message_id).first():
                raise NotFoundException("Message not found")
            exists = (
                self.db.query(MessageReaction)
                .filter(
                    MessageReaction.message_id == message_id,
                    MessageReaction.user_id == user_id,
                    MessageReaction.emoji == emoji,
                )
                .first()
            )
            if exists:
                return True
            reaction = MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji)
            self.db.add(reaction)
            try:
                self.db.flush()
            except IntegrityError:
                # Parallel inserts for the same reaction are safe to treat as idempotent success.
                return True
            self.logger.info("Added reaction %s by %s on message %s", emoji, user_id, message_id)
            return True
        except Exception as e:
            self.logger.error("Error adding reaction: %s", str(e))
            raise RepositoryException(f"Failed to add reaction: {str(e)}")

    def remove_reaction(self, message_id: str, user_id: str, emoji: str) -> bool:
        """Remove a reaction if it exists."""
        try:
            query = self.db.query(MessageReaction).filter(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user_id,
                MessageReaction.emoji == emoji,
            )
            if query.first() is None:
                return False
            query.delete(synchronize_session=False)
            self.logger.info("Removed reaction %s by %s on message %s", emoji, user_id, message_id)
            return True
        except Exception as e:
            self.logger.error("Error removing reaction: %s", str(e))
            raise RepositoryException(f"Failed to remove reaction: {str(e)}")
