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

    # Enable PostGIS extension for spatial features (idempotent)
    if is_postgres:
        print("Checking/Enabling PostGIS extension (if not already enabled)...")
        conn = op.get_bind()
        try:
            res = conn.exec_driver_sql(
                "SELECT 1 FROM pg_available_extensions WHERE name='postgis' AND installed_version IS NOT NULL"
            )
            already_installed = res.first() is not None
        except Exception:
            already_installed = False
        if not already_installed:
            try:
                op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                print("PostGIS extension created")
            except Exception as e:
                # Provide a clear, actionable error for local setups
                raise RuntimeError(
                    "PostGIS extension is not installed on this PostgreSQL instance. "
                    "Install PostGIS (e.g., 'brew install postgis' on macOS, or use a PostGIS-enabled Docker image) "
                    "and re-run migrations. Original error: %s" % str(e)
                )

    # Add alert history table for monitoring
    print("Creating alert_history table...")
    op.create_table(
        "alert_history",
        sa.Column("id", sa.String(26), nullable=False),
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
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("sender_id", sa.String(26), nullable=False),
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
                sender_first_name TEXT;
                sender_last_name TEXT;
            BEGIN
                SELECT first_name, last_name INTO sender_first_name, sender_last_name FROM users WHERE id = NEW.sender_id;
                payload = json_build_object(
                    'id', NEW.id,
                    'booking_id', NEW.booking_id,
                    'sender_id', NEW.sender_id,
                    'sender_first_name', sender_first_name,
                    'sender_last_name', sender_last_name,
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
                booking_id VARCHAR(26);
                reader_first_name TEXT;
                reader_last_name TEXT;
            BEGIN
                IF TG_OP = 'UPDATE' AND NEW.is_read = TRUE AND (OLD.is_read IS DISTINCT FROM NEW.is_read) THEN
                    UPDATE messages SET read_by = COALESCE(read_by, '[]'::jsonb) || jsonb_build_array(jsonb_build_object('user_id', NEW.user_id, 'read_at', NEW.read_at))
                    WHERE id = NEW.message_id;
                    SELECT m.booking_id INTO booking_id FROM messages m WHERE m.id = NEW.message_id;
                    SELECT first_name, last_name INTO reader_first_name, reader_last_name FROM users WHERE id = NEW.user_id;
                    payload = json_build_object(
                        'type', 'read_receipt',
                        'message_id', NEW.message_id,
                        'user_id', NEW.user_id,
                        'reader_first_name', reader_first_name,
                        'reader_last_name', reader_last_name,
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

    # -------------------------------
    # Addresses and Spatial Data
    # -------------------------------

    # Lightweight Geometry type for migrations without geoalchemy2 dependency
    class Geometry(sa.types.UserDefinedType):
        def __init__(self, geom_type: str = "POINT", srid: int = 4326):
            self.geom_type = geom_type
            self.srid = srid

        def get_col_spec(self, **kw):  # type: ignore[override]
            return f"GEOMETRY({self.geom_type}, {self.srid})"

    print("Creating user_addresses table...")
    op.create_table(
        "user_addresses",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Labels and defaults
        sa.Column("label", sa.String(20), nullable=True),  # 'home' | 'work' | 'other'
        sa.Column("custom_label", sa.String(50), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        # Recipient and lines
        sa.Column("recipient_name", sa.String(100), nullable=True),
        sa.Column("street_line1", sa.String(255), nullable=False),
        sa.Column("street_line2", sa.String(255), nullable=True),
        # Locality
        sa.Column("locality", sa.String(100), nullable=False),  # city/town
        sa.Column("administrative_area", sa.String(100), nullable=False),  # state/province
        sa.Column("postal_code", sa.String(20), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="US"),
        # Coordinates
        sa.Column("latitude", sa.Numeric(10, 8), nullable=True),
        sa.Column("longitude", sa.Numeric(11, 8), nullable=True),
        # Provider references
        sa.Column("place_id", sa.String(255), nullable=True),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("normalized_payload", sa.JSON(), nullable=True),
        # Geometry (PostGIS)
        sa.Column("location", Geometry("POINT", 4326), nullable=True),
        # Generic location hierarchy (globally applicable)
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("neighborhood", sa.String(100), nullable=True),
        sa.Column("subneighborhood", sa.String(100), nullable=True),
        # Flexible location metadata for city/region specific details
        sa.Column("location_metadata", sa.JSON(), nullable=True),
        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes and constraints for addresses
    op.create_index("ix_user_addresses_user_active", "user_addresses", ["user_id", "is_active"])
    if is_postgres:
        # Geometry index
        op.create_index(
            "ix_user_addresses_location",
            "user_addresses",
            ["location"],
            postgresql_using="gist",
        )
        # Partial unique: one default address per user
        op.create_index(
            "uq_user_default_address",
            "user_addresses",
            ["user_id"],
            unique=True,
            postgresql_where=sa.text("is_default = true"),
        )
    # Basic helpers
    op.create_index("ix_user_addresses_postal_code", "user_addresses", ["postal_code"])

    # Label checks
    op.create_check_constraint(
        "ck_user_addresses_label_values",
        "user_addresses",
        "label IS NULL OR label IN ('home','work','other')",
    )
    op.create_check_constraint(
        "ck_user_addresses_other_label_has_custom",
        "user_addresses",
        "label != 'other' OR custom_label IS NOT NULL",
    )

    # NYC neighborhoods table for service areas
    # Removed legacy nyc_neighborhoods in favor of generic region_boundaries

    # Generic region boundaries table (global, additive alongside nyc_neighborhoods for now)
    print("Creating region_boundaries table (generic global regions)...")
    op.create_table(
        "region_boundaries",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("region_type", sa.String(50), nullable=False),  # 'nyc', 'sf', 'toronto', etc.
        sa.Column("region_code", sa.String(50), nullable=True),
        sa.Column("region_name", sa.String(100), nullable=True),
        sa.Column("parent_region", sa.String(100), nullable=True),
        sa.Column("boundary", Geometry("POLYGON", 4326), nullable=True),
        sa.Column("centroid", Geometry("POINT", 4326), nullable=True),
        sa.Column("region_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    if is_postgres:
        op.create_index(
            "ix_region_boundaries_boundary",
            "region_boundaries",
            ["boundary"],
            postgresql_using="gist",
        )
    op.create_index("ix_region_boundaries_type", "region_boundaries", ["region_type"])
    op.create_index("ix_region_boundaries_region", "region_boundaries", ["region_type", "region_code"])
    op.create_index("ix_region_boundaries_name", "region_boundaries", ["region_type", "region_name"])

    # Instructor service areas (link instructors to neighborhoods)
    print("Creating instructor_service_areas table...")
    op.create_table(
        "instructor_service_areas",
        sa.Column("instructor_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "neighborhood_id", sa.String(26), sa.ForeignKey("region_boundaries.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("instructor_id", "neighborhood_id"),
    )
    op.create_index(
        "ix_instructor_service_areas_instructor",
        "instructor_service_areas",
        ["instructor_id", "is_active"],
    )

    # Reactions table for message reactions
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

    # Message edits table for edit history
    op.create_table(
        "message_edits",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("message_id", sa.String(26), nullable=False),
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

    # Drop service area tables and spatial indexes first (to avoid dependency issues)
    print("Dropping instructor service area and neighborhoods tables...")
    op.drop_index("ix_instructor_service_areas_instructor", table_name="instructor_service_areas")
    op.drop_table("instructor_service_areas")
    # Legacy nyc_neighborhoods not created in this migration anymore

    # Drop region_boundaries and its indexes to avoid duplicate-table issues on re-upgrade
    print("Dropping region_boundaries table and indexes...")
    try:
        op.drop_index("ix_region_boundaries_name", table_name="region_boundaries")
    except Exception:
        pass
    try:
        op.drop_index("ix_region_boundaries_region", table_name="region_boundaries")
    except Exception:
        pass
    try:
        op.drop_index("ix_region_boundaries_type", table_name="region_boundaries")
    except Exception:
        pass
    if is_postgres:
        try:
            op.drop_index("ix_region_boundaries_boundary", table_name="region_boundaries")
        except Exception:
            pass
    try:
        op.drop_table("region_boundaries")
    except Exception:
        pass

    print("Dropping user_addresses table and indexes...")
    op.drop_index("ix_user_addresses_postal_code", table_name="user_addresses")
    if is_postgres:
        op.drop_index("uq_user_default_address", table_name="user_addresses")
        op.drop_index("ix_user_addresses_location", table_name="user_addresses")
    op.drop_index("ix_user_addresses_user_active", table_name="user_addresses")
    op.drop_constraint("ck_user_addresses_other_label_has_custom", "user_addresses", type_="check")
    op.drop_constraint("ck_user_addresses_label_values", "user_addresses", type_="check")
    op.drop_table("user_addresses")

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
