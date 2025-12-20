# backend/alembic/versions/004_messaging.py
"""Messaging system - conversations, messages, notifications

Revision ID: 004_messaging
Revises: 003_availability_booking
Create Date: 2025-02-10 00:00:03.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "004_messaging"
down_revision: Union[str, None] = "003_availability_booking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create messaging tables and triggers."""
    print("Creating messaging tables...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"
    json_type = JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    print("Creating conversations table...")
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="One conversation per student-instructor pair",
    )

    op.create_index("idx_conversations_student", "conversations", ["student_id"])
    op.create_index("idx_conversations_instructor", "conversations", ["instructor_id"])
    op.create_index("idx_conversations_last_message", "conversations", ["last_message_at"])

    if is_postgres:
        op.execute(
            """
            CREATE UNIQUE INDEX idx_conversations_pair_unique
            ON conversations (LEAST(student_id, instructor_id), GREATEST(student_id, instructor_id));
            """
        )
    else:
        op.create_unique_constraint(
            "conversations_pair_unique_sqlite",
            "conversations",
            ["student_id", "instructor_id"],
        )

    print("Creating messages table...")
    op.create_table(
        "messages",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=True),
        sa.Column("sender_id", sa.String(26), nullable=True),
        sa.Column("content", sa.String(1000), nullable=False),
        sa.Column("conversation_id", sa.String(26), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(26), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "read_by",
            json_type,
            server_default=(sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'")),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_messages_booking_created", "messages", ["booking_id", "created_at"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index("ix_messages_deleted_at", "messages", ["deleted_at"])
    op.create_index("ix_messages_booking_id_id", "messages", ["booking_id", "id"])
    op.create_index("ix_messages_conversation", "messages", ["conversation_id", "created_at"])
    if is_postgres:
        op.create_index(
            "idx_messages_unread_lookup",
            "messages",
            ["conversation_id", "sender_id", "is_deleted"],
            postgresql_where=sa.text("is_deleted = false"),
        )
        op.create_index(
            "ix_messages_booking_nullable",
            "messages",
            ["booking_id"],
            postgresql_where=sa.text("booking_id IS NOT NULL"),
        )

    op.create_check_constraint(
        "check_message_content_length",
        "messages",
        "LENGTH(content) > 0 AND LENGTH(content) <= 1000",
    )
    op.create_check_constraint(
        "ck_messages_soft_delete_consistency",
        "messages",
        "(is_deleted = FALSE AND deleted_at IS NULL) OR (is_deleted = TRUE AND deleted_at IS NOT NULL)",
    )

    print("Creating message_notifications table...")
    op.create_table(
        "message_notifications",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("message_id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_user"),
    )

    op.create_index("ix_message_notifications_user_unread", "message_notifications", ["user_id", "is_read"])
    op.create_index("ix_message_notifications_message_id", "message_notifications", ["message_id"])

    print("Creating conversation_user_state table...")
    op.create_table(
        "conversation_user_state",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("conversation_id", sa.String(26), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_user_state_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "conversation_id", name="uq_conversation_user_state_user_conversation"),
        comment="User-specific conversation states (active, archived, trashed)",
    )
    op.create_index(
        "ix_conversation_user_state_user_state",
        "conversation_user_state",
        ["user_id", "state"],
    )
    op.create_check_constraint(
        "ck_conversation_user_state_state",
        "conversation_user_state",
        "state IN ('active', 'archived', 'trashed')",
    )

    op.create_table(
        "message_reactions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("message_id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_message_reaction"),
    )

    op.create_table(
        "message_edits",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("message_id", sa.String(26), nullable=False),
        sa.Column("original_content", sa.String(1000), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    if is_postgres:
        print("Creating PostgreSQL NOTIFY function for per-user channels...")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION public.notify_new_message()
            RETURNS TRIGGER
            SET search_path = public
            AS $$
            DECLARE
                v_booking RECORD;
                v_conversation RECORD;
                v_payload JSONB;
                v_sender_name TEXT;
                v_delivered_at TIMESTAMP WITH TIME ZONE;
            BEGIN
                SELECT first_name INTO v_sender_name
                FROM users WHERE id = NEW.sender_id;

                v_delivered_at := NOW();
                UPDATE messages SET delivered_at = v_delivered_at WHERE id = NEW.id;

                IF NEW.conversation_id IS NOT NULL THEN
                    SELECT c.student_id, c.instructor_id INTO v_conversation
                    FROM conversations c WHERE c.id = NEW.conversation_id;

                    IF v_conversation IS NOT NULL THEN
                        v_payload := jsonb_build_object(
                            'type', 'new_message',
                            'conversation_id', NEW.conversation_id,
                            'message', jsonb_build_object(
                                'id', NEW.id,
                                'content', NEW.content,
                                'sender_id', NEW.sender_id,
                                'sender_name', v_sender_name,
                                'created_at', NEW.created_at,
                                'booking_id', NEW.booking_id,
                                'is_deleted', NEW.is_deleted,
                                'delivered_at', v_delivered_at
                            )
                        );

                        IF v_conversation.instructor_id IS NOT NULL THEN
                            PERFORM pg_notify(
                                'user_' || v_conversation.instructor_id || '_inbox',
                                v_payload::text
                            );
                        END IF;

                        IF v_conversation.student_id IS NOT NULL THEN
                            PERFORM pg_notify(
                                'user_' || v_conversation.student_id || '_inbox',
                                v_payload::text
                            );
                        END IF;
                    END IF;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        op.execute(
            """
            CREATE TRIGGER message_insert_notify
            AFTER INSERT ON messages
            FOR EACH ROW
            EXECUTE FUNCTION public.notify_new_message();
            """
        )

        op.execute(
            """
            CREATE OR REPLACE FUNCTION public.handle_message_read_receipt()
            RETURNS TRIGGER
            SET search_path = public
            AS $$
            DECLARE
                v_message RECORD;
                v_booking RECORD;
                v_payload JSONB;
                v_recipient_id TEXT;
            BEGIN
                IF NEW.is_read = TRUE THEN
                    SELECT m.booking_id, m.sender_id INTO v_message FROM messages m WHERE m.id = NEW.message_id;
                    SELECT b.instructor_id, b.student_id INTO v_booking FROM bookings b WHERE b.id = v_message.booking_id;

                    v_recipient_id := v_message.sender_id;

                    v_payload := jsonb_build_object(
                        'type', 'read_receipt',
                        'conversation_id', v_message.booking_id,
                        'message_id', NEW.message_id,
                        'reader_id', NEW.user_id,
                        'read_at', NEW.read_at
                    );

                    PERFORM pg_notify(
                        'user_' || v_recipient_id || '_inbox',
                        v_payload::text
                    );
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )

        op.execute(
            """
            CREATE TRIGGER message_read_receipt_notify
            AFTER UPDATE ON message_notifications
            FOR EACH ROW
            EXECUTE FUNCTION public.handle_message_read_receipt();
            """
        )


def downgrade() -> None:
    """Drop messaging tables and triggers."""
    print("Dropping messaging tables...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS message_read_receipt_notify ON message_notifications;")
        op.execute("DROP FUNCTION IF EXISTS public.handle_message_read_receipt();")
        op.execute("DROP TRIGGER IF EXISTS message_insert_notify ON messages;")
        op.execute("DROP FUNCTION IF EXISTS public.notify_new_message();")

    op.drop_table("message_edits")
    op.drop_table("message_reactions")

    op.drop_constraint("ck_conversation_user_state_state", "conversation_user_state", type_="check")
    op.drop_index("ix_conversation_user_state_user_state", table_name="conversation_user_state")
    op.drop_constraint(
        "uq_conversation_user_state_user_conversation",
        "conversation_user_state",
        type_="unique",
    )
    op.drop_table("conversation_user_state")

    op.drop_index("ix_message_notifications_message_id", table_name="message_notifications")
    op.drop_index("ix_message_notifications_user_unread", table_name="message_notifications")
    op.drop_table("message_notifications")

    op.drop_constraint("ck_messages_soft_delete_consistency", "messages", type_="check")
    op.drop_constraint("check_message_content_length", "messages", type_="check")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_messages_unread_lookup")
        op.execute("DROP INDEX IF EXISTS ix_messages_booking_nullable")
    op.drop_index("ix_messages_conversation", table_name="messages")
    op.drop_index("ix_messages_booking_id_id", table_name="messages")
    op.drop_index("ix_messages_deleted_at", table_name="messages")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_sender_id", table_name="messages")
    op.drop_index("ix_messages_booking_created", table_name="messages")
    op.drop_table("messages")

    if not is_postgres:
        op.drop_constraint("conversations_pair_unique_sqlite", "conversations", type_="unique")
    else:
        op.execute("DROP INDEX IF EXISTS idx_conversations_pair_unique")
    op.drop_index("idx_conversations_last_message", table_name="conversations")
    op.drop_index("idx_conversations_instructor", table_name="conversations")
    op.drop_index("idx_conversations_student", table_name="conversations")
    op.drop_table("conversations")
