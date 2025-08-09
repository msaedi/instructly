# backend/alembic/versions/006_final_constraints.py
"""Final constraints - Schema completion and documentation

Revision ID: 006_final_constraints
Revises: 005_performance_indexes
Create Date: 2024-12-21 00:00:05.000000

This migration adds any remaining constraints and finalizes the schema.
It ensures all business rules are enforced at the database level.
Also adds monitoring infrastructure tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_final_constraints"
down_revision: Union[str, None] = "005_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add final constraints and schema adjustments."""
    print("Adding final constraints and adjustments...")
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    # Add alert history table for monitoring
    print("Creating alert_history table...")
    op.create_table(
        "alert_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("email_sent", sa.Boolean(), nullable=False, default=False),
        sa.Column("github_issue_created", sa.Boolean(), nullable=False, default=False),
        sa.Column("github_issue_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add indexes for alert history
    op.create_index("ix_alert_history_created_at", "alert_history", ["created_at"])
    op.create_index("ix_alert_history_alert_type", "alert_history", ["alert_type"])
    op.create_index("ix_alert_history_severity", "alert_history", ["severity"])

    # Add messages table for chat system
    print("Creating messages table for chat system...")
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        # Phase 2 additions
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "read_by",
            (sa.dialects.postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()),
            server_default=(sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'")),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add indexes for messages
    op.create_index("ix_messages_booking_created", "messages", ["booking_id", "created_at"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

    # Add message_notifications table for tracking unread messages
    print("Creating message_notifications table...")
    op.create_table(
        "message_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_user"),
    )

    # Add indexes for message_notifications
    op.create_index("ix_message_notifications_user_unread", "message_notifications", ["user_id", "is_read"])
    op.create_index("ix_message_notifications_message_id", "message_notifications", ["message_id"])

    if is_postgres:
        # Create PostgreSQL NOTIFY function for real-time messaging
        print("Creating PostgreSQL NOTIFY function for real-time messaging (PostgreSQL only)...")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION notify_new_message()
            RETURNS TRIGGER AS $$
            DECLARE
                payload json;
                sender_name TEXT;
            BEGIN
                SELECT full_name INTO sender_name FROM users WHERE id = NEW.sender_id;
                payload = json_build_object(
                    'id', NEW.id,
                    'booking_id', NEW.booking_id,
                    'sender_id', NEW.sender_id,
                    'sender_name', sender_name,
                    'content', NEW.content,
                    'created_at', NEW.created_at,
                    'is_deleted', NEW.is_deleted,
                    'type', 'message'
                );
                PERFORM pg_notify('booking_chat_' || NEW.booking_id::text, payload::text);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """
        )

        # Create trigger to fire on message insert
        op.execute(
            """
            CREATE TRIGGER message_insert_notify
            AFTER INSERT ON messages
            FOR EACH ROW
            EXECUTE FUNCTION notify_new_message();
        """
        )

        # Read receipt trigger: when a notification is marked read, update messages.read_by and notify
        op.execute(
            """
            CREATE OR REPLACE FUNCTION handle_message_read_receipt()
            RETURNS TRIGGER AS $$
            DECLARE
                payload json;
                booking_id INT;
                reader_name TEXT;
            BEGIN
                IF TG_OP = 'UPDATE' AND NEW.is_read = TRUE AND (OLD.is_read IS DISTINCT FROM NEW.is_read) THEN
                    UPDATE messages SET read_by = COALESCE(read_by, '[]'::jsonb) || jsonb_build_array(jsonb_build_object('user_id', NEW.user_id, 'read_at', NEW.read_at))
                    WHERE id = NEW.message_id;
                    SELECT m.booking_id INTO booking_id FROM messages m WHERE m.id = NEW.message_id;
                    SELECT full_name INTO reader_name FROM users WHERE id = NEW.user_id;
                    payload = json_build_object(
                        'type', 'read_receipt',
                        'message_id', NEW.message_id,
                        'user_id', NEW.user_id,
                        'reader_name', reader_name,
                        'read_at', NEW.read_at
                    );
                    IF booking_id IS NOT NULL THEN
                        PERFORM pg_notify('booking_chat_' || booking_id::text, payload::text);
                    END IF;
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
            EXECUTE FUNCTION handle_message_read_receipt();
            """
        )

    # Reactions table for message reactions
    op.create_table(
        "message_reactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_message_reaction"),
    )

    # Message edits table for edit history
    op.create_table(
        "message_edits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("original_content", sa.String(1000), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add any remaining check constraints that weren't in earlier migrations

    # Ensure bookings have positive duration
    op.create_check_constraint(
        "check_duration_positive",
        "bookings",
        "duration_minutes > 0",
    )

    # Ensure bookings have non-negative price
    op.create_check_constraint(
        "check_price_non_negative",
        "bookings",
        "total_price >= 0",
    )

    # Ensure bookings have positive hourly rate
    op.create_check_constraint(
        "check_rate_positive",
        "bookings",
        "hourly_rate > 0",
    )

    # Ensure time order is correct
    op.create_check_constraint(
        "check_time_order",
        "bookings",
        "start_time < end_time",
    )

    # Add check constraint for message content length
    op.create_check_constraint(
        "check_message_content_length",
        "messages",
        "LENGTH(content) > 0 AND LENGTH(content) <= 1000",
    )

    # Add schema documentation
    print("Schema finalization complete!")
    print("")
    print("=== FINAL SCHEMA SUMMARY ===")
    print("Tables created:")
    print("  - users (authentication and roles)")
    print("  - instructor_profiles (instructor details)")
    print("  - service_categories (organize services)")
    print("  - service_catalog (predefined services)")
    print("  - instructor_services (instructor offerings with soft delete)")
    print("  - availability_slots (single-table design with date/time)")
    print("  - blackout_dates (vacation tracking)")
    print("  - bookings (instant booking system)")
    print("  - password_reset_tokens (password recovery)")
    print("  - alert_history (monitoring alerts and notifications)")
    print("  - messages (real-time chat for bookings)")
    print("  - message_notifications (unread message tracking)")
    print("")
    print("Key design decisions implemented:")
    print("  - Single-table availability design (no instructor_availability)")
    print("  - Service catalog system with categories")
    print("  - Soft delete on instructor_services via is_active flag")
    print("  - Areas of service as VARCHAR (not ARRAY)")
    print("  - Location type support for bookings")
    print("  - Instant booking (default status = CONFIRMED)")
    print("  - Real-time chat with PostgreSQL LISTEN/NOTIFY")
    print("")
    print("Performance optimizations:")
    print("  - Composite indexes for common queries")
    print("  - Partial indexes for active records")
    print("  - Foreign key indexes")
    print("")
    print("Schema is ready for production use!")


def downgrade() -> None:
    """Drop final constraints and monitoring tables."""
    print("Dropping final constraints...")
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    op.drop_constraint("check_message_content_length", "messages", type_="check")
    op.drop_constraint("check_time_order", "bookings", type_="check")
    op.drop_constraint("check_rate_positive", "bookings", type_="check")
    op.drop_constraint("check_price_non_negative", "bookings", type_="check")
    op.drop_constraint("check_duration_positive", "bookings", type_="check")

    # Drop message notification trigger and function
    if is_postgres:
        print("Dropping message notification trigger and function (PostgreSQL only)...")
        op.execute("DROP TRIGGER IF EXISTS message_insert_notify ON messages;")
        op.execute("DROP FUNCTION IF EXISTS notify_new_message();")

    # Drop read receipt trigger and function (Phase 2 additions)
    if is_postgres:
        print("Dropping read receipt trigger and function (PostgreSQL only)...")
        op.execute("DROP TRIGGER IF EXISTS message_read_receipt_notify ON message_notifications;")
        op.execute("DROP FUNCTION IF EXISTS handle_message_read_receipt();")

    # Drop Phase 2 tables that depend on messages first
    print("Dropping message_reactions and message_edits tables...")
    op.drop_table("message_reactions")
    op.drop_table("message_edits")

    # Drop message_notifications table
    print("Dropping message_notifications table...")
    op.drop_index("ix_message_notifications_message_id", "message_notifications")
    op.drop_index("ix_message_notifications_user_unread", "message_notifications")
    op.drop_table("message_notifications")

    # Drop messages table
    print("Dropping messages table...")
    op.drop_index("ix_messages_created_at", "messages")
    op.drop_index("ix_messages_sender_id", "messages")
    op.drop_index("ix_messages_booking_created", "messages")
    op.drop_table("messages")

    # Drop alert history table
    print("Dropping alert_history table...")
    op.drop_index("ix_alert_history_severity", "alert_history")
    op.drop_index("ix_alert_history_alert_type", "alert_history")
    op.drop_index("ix_alert_history_created_at", "alert_history")
    op.drop_table("alert_history")

    print("Final constraints and monitoring tables dropped successfully!")
