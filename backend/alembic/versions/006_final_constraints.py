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

from alembic import op
import sqlalchemy as sa
from sqlalchemy import LargeBinary
from sqlalchemy.dialects.postgresql import BYTEA, JSONB


def _get_public_tables(exclude: list[str]) -> list[str]:
    """Return list of public schema base tables excluding given names."""

    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        """
        SELECT c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' -- ordinary tables
          AND n.nspname = 'public'
          AND c.relname NOT IN (%s)
        ORDER BY c.relname
        """
        % ",".join(["'%s'" % name for name in exclude])
    ).fetchall()
    return [r[0] for r in rows]


def _enable_rls_with_permissive_policy(table_name: str) -> None:
    """Enable RLS and create a permissive policy on the given table."""

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = '{table_name}' AND n.nspname = 'public' AND c.relrowsecurity = true
            ) THEN
                EXECUTE 'ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY';
            END IF;
        END$$;
        """
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = '{table_name}' AND policyname = 'all_access'
            ) THEN
                EXECUTE 'CREATE POLICY all_access ON public.{table_name} FOR ALL TO PUBLIC USING (true) WITH CHECK (true)';
            END IF;
        END$$;
        """
    )


def _drop_permissive_policy_and_disable_rls(table_name: str) -> None:
    """Drop permissive policy and disable RLS on the given table (idempotent)."""

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = '{table_name}' AND policyname = 'all_access'
            ) THEN
                EXECUTE 'DROP POLICY all_access ON public.{table_name}';
            END IF;
        END$$;
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = '{table_name}' AND n.nspname = 'public' AND c.relrowsecurity = true
            ) THEN
                EXECUTE 'ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY';
            END IF;
        END$$;
        """
    )


def _create_extension_prefer_extensions_schema(extension_name: str) -> None:
    """Create extension using extensions schema when available."""

    bind = op.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return

    op.execute(
        f"""
        DO $$
        DECLARE
            extensions_schema_exists BOOLEAN;
            extension_installed BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM pg_namespace WHERE nspname = 'extensions'
            ) INTO extensions_schema_exists;

            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = '{extension_name}'
            ) INTO extension_installed;

            IF NOT extension_installed THEN
                IF extensions_schema_exists THEN
                    EXECUTE 'CREATE EXTENSION IF NOT EXISTS {extension_name} WITH SCHEMA extensions';
                ELSE
                    EXECUTE 'CREATE EXTENSION IF NOT EXISTS {extension_name}';
                END IF;
            END IF;
        END
        $$;
        """
    )

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
                _create_extension_prefer_extensions_schema("postgis")
                print("PostGIS extension created")
            except Exception as e:
                # Provide a clear, actionable error for local setups
                raise RuntimeError(
                    "PostGIS extension is not installed on this PostgreSQL instance. "
                    "Install PostGIS (e.g., 'brew install postgis' on macOS, or use a PostGIS-enabled Docker image) "
                    "and re-run migrations. Original error: %s" % str(e)
                )

    print("Creating platform_config table...")
    json_type = JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    op.create_table(
        "platform_config",
        sa.Column("key", sa.Text(), primary_key=True, nullable=False),
        sa.Column("value_json", json_type, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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

    print("Creating notification outbox tables...")
    event_outbox_payload_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")
    notification_payload_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")

    op.create_table(
        "event_outbox",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", json_type, nullable=False, server_default=event_outbox_payload_default),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_event_outbox_idempotency_key"),
    )
    op.create_index("ix_event_outbox_event_type", "event_outbox", ["event_type"])
    op.create_index("ix_event_outbox_status_next_attempt", "event_outbox", ["status", "next_attempt_at"])

    op.create_table(
        "notification_delivery",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", json_type, nullable=False, server_default=notification_payload_default),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_delivery_idempotency"),
    )
    op.create_index(
        "ix_notification_delivery_event_type_delivered_at",
        "notification_delivery",
        ["event_type", "delivered_at"],
    )

    print("Creating availability_days table...")
    bits_type = BYTEA if is_postgres else LargeBinary  # 6 bytes (48 half-hours)
    op.create_table(
        "availability_days",
        sa.Column("instructor_id", sa.String(length=26), nullable=False),
        sa.Column("day_date", sa.Date(), nullable=False),
        sa.Column("bits", bits_type, nullable=False),  # expect len=6 (30-min res)
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("instructor_id", "day_date"),
    )
    op.create_index(
        "ix_avail_days_instructor_date",
        "availability_days",
        ["instructor_id", "day_date"],
    )

    print("Creating audit_log table...")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.String(length=26), nullable=True),
        sa.Column("actor_role", sa.String(length=30), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("before", json_type, nullable=True),
        sa.Column("after", json_type, nullable=True),
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_audit_log_entity ON audit_log (entity_type, entity_id, occurred_at DESC);"
        )
        op.execute(
            "CREATE INDEX ix_audit_log_actor ON audit_log (actor_id, occurred_at DESC);"
        )
        op.execute(
            "CREATE INDEX ix_audit_log_action ON audit_log (action, occurred_at DESC);"
        )
    else:
        op.create_index(
            "ix_audit_log_entity",
            "audit_log",
            ["entity_type", "entity_id", "occurred_at"],
        )
        op.create_index(
            "ix_audit_log_actor",
            "audit_log",
            ["actor_id", "occurred_at"],
        )
        op.create_index(
            "ix_audit_log_action",
            "audit_log",
            ["action", "occurred_at"],
        )

    # Background check guard rails on instructor profiles
    print("Adding background check fields to instructor_profiles...")
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_status", sa.String(length=20), nullable=True),
    )
    op.alter_column(
        "instructor_profiles",
        "bgc_status",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=None,
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_report_id", sa.String(length=64), nullable=True),
    )
    op.alter_column(
        "instructor_profiles",
        "bgc_report_id",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_env", sa.String(length=20), nullable=False, server_default="sandbox"),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_eta", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_invited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column(
            "bgc_includes_canceled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_in_dispute", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_dispute_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_dispute_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_dispute_resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_pre_adverse_notice_id", sa.String(length=26), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_pre_adverse_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_final_adverse_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_review_email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_report_result", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("checkr_candidate_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("checkr_invitation_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("bgc_note", sa.Text(), nullable=True),
    )

    op.create_check_constraint(
        "ck_instructor_profiles_bgc_status",
        "instructor_profiles",
        "bgc_status IN ('pending','passed','review','failed','consider','canceled')",
    )
    op.create_check_constraint(
        "ck_instructor_profiles_bgc_env",
        "instructor_profiles",
        "bgc_env IN ('sandbox','production')",
    )
    op.create_check_constraint(
        "ck_live_requires_bgc_passed",
        "instructor_profiles",
        "(is_live = FALSE) OR (bgc_status = 'passed')",
    )
    op.create_index(
        "ix_instructor_profiles_checkr_candidate_id",
        "instructor_profiles",
        ["checkr_candidate_id"],
    )
    op.create_index(
        "ix_instructor_profiles_checkr_invitation_id",
        "instructor_profiles",
        ["checkr_invitation_id"],
    )
    op.create_index(
        "ix_instructor_profiles_bgc_report_id",
        "instructor_profiles",
        ["bgc_report_id"],
    )

    print("Creating bgc_webhook_log table...")
    op.create_table(
        "bgc_webhook_log",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("delivery_id", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column(
            "payload_json",
            json_type,
            nullable=False,
        ),
        sa.Column("signature", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_bgc_webhook_log_event_type_created_at",
        "bgc_webhook_log",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_bgc_webhook_log_delivery_id",
        "bgc_webhook_log",
        ["delivery_id"],
    )
    op.create_index(
        "ix_bgc_webhook_log_http_status",
        "bgc_webhook_log",
        ["http_status", "created_at"],
    )

    print("Creating background_checks history table...")
    op.create_table(
        "background_checks",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("instructor_id", sa.String(length=26), nullable=False),
        sa.Column("report_id_enc", sa.Text(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("package", sa.Text(), nullable=True),
        sa.Column("env", sa.String(length=20), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_background_checks_report_id_enc",
        "background_checks",
        ["report_id_enc"],
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_background_checks_instructor_created_at_desc "
            "ON background_checks (instructor_id, created_at DESC);"
        )
    else:
        op.create_index(
            "ix_background_checks_instructor_created_at",
            "background_checks",
            ["instructor_id", "created_at"],
        )

    print("Creating bgc_adverse_action_events table...")
    op.create_table(
        "bgc_adverse_action_events",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("profile_id", sa.String(length=26), nullable=False),
        sa.Column("notice_id", sa.String(length=26), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint(
        "uq_bgc_adverse_action_events_profile_notice_type",
        "bgc_adverse_action_events",
        ["profile_id", "notice_id", "event_type"],
    )
    op.create_index(
        "ix_bgc_adverse_action_events_profile",
        "bgc_adverse_action_events",
        ["profile_id"],
    )

    print("Creating background_jobs table...")
    payload_type = (
        sa.dialects.postgresql.JSONB(astext_type=sa.Text())
        if is_postgres
        else sa.JSON()
    )
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_background_jobs_status_available",
        "background_jobs",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_background_jobs_type_status",
        "background_jobs",
        ["type", "status"],
    )

    print("Creating bgc_consent table...")
    op.create_table(
        "bgc_consent",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("instructor_id", sa.String(length=26), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("consent_version", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bgc_consent_instructor_id", "bgc_consent", ["instructor_id"])

    # ======== CONVERSATIONS TABLE (Per-User-Pair Architecture) ========
    # Create conversations table BEFORE messages so messages can reference it
    print("Creating conversations table for per-user-pair messaging...")
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

    # Add indexes for conversations
    op.create_index("idx_conversations_student", "conversations", ["student_id"])
    op.create_index("idx_conversations_instructor", "conversations", ["instructor_id"])
    op.create_index("idx_conversations_last_message", "conversations", ["last_message_at"])

    # Add unique index for pair uniqueness (PostgreSQL uses LEAST/GREATEST expressions)
    if is_postgres:
        op.execute(
            """
            CREATE UNIQUE INDEX idx_conversations_pair_unique
            ON conversations (LEAST(student_id, instructor_id), GREATEST(student_id, instructor_id));
            """
        )
    else:
        # SQLite fallback: simple unique constraint on ordered pair
        # Note: This doesn't prevent (A,B) and (B,A) but SQLite is only for testing
        op.create_unique_constraint(
            "conversations_pair_unique_sqlite",
            "conversations",
            ["student_id", "instructor_id"],
        )

    # Add messages table for chat system
    print("Creating messages table for chat system...")
    op.create_table(
        "messages",
        sa.Column("id", sa.String(26), nullable=False),
        # booking_id is now nullable (for pre-booking messages or conversation-only context)
        sa.Column("booking_id", sa.String(26), nullable=True),
        # sender_id is nullable for system messages (no human sender)
        sa.Column("sender_id", sa.String(26), nullable=True),
        sa.Column("content", sa.String(1000), nullable=False),
        # conversation_id for per-user-pair messaging
        sa.Column("conversation_id", sa.String(26), nullable=False),
        # message_type: 'user', 'system_booking_created', 'system_booking_cancelled', etc.
        sa.Column("message_type", sa.String(50), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(26), nullable=True),
        # Phase 2 additions
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "read_by",
            (sa.dialects.postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()),
            server_default=(sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'")),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add indexes for messages
    op.create_index("ix_messages_booking_created", "messages", ["booking_id", "created_at"])
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index("ix_messages_deleted_at", "messages", ["deleted_at"])
    # Composite index for catch-up queries (booking_id.in_() with id range scan)
    op.create_index("ix_messages_booking_id_id", "messages", ["booking_id", "id"])
    # Index for conversation-based queries
    op.create_index("ix_messages_conversation", "messages", ["conversation_id", "created_at"])
    if is_postgres:
        op.create_index(
            "idx_messages_unread_lookup",
            "messages",
            ["conversation_id", "sender_id", "is_deleted"],
            postgresql_where=sa.text("is_deleted = false"),
        )
    # Partial index for messages with booking_id (for backward compatibility queries)
    if is_postgres:
        op.create_index(
            "ix_messages_booking_nullable",
            "messages",
            ["booking_id"],
            postgresql_where=sa.text("booking_id IS NOT NULL"),
        )

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
        # Create PostgreSQL NOTIFY function for real-time messaging (per-user channels)
        print("Creating PostgreSQL NOTIFY function for per-user channels (PostgreSQL only)...")
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
                -- Get sender name for display
                SELECT first_name INTO v_sender_name
                FROM users WHERE id = NEW.sender_id;

                -- Set delivered_at timestamp (message is delivered when SSE is sent)
                v_delivered_at := NOW();
                UPDATE messages SET delivered_at = v_delivered_at WHERE id = NEW.id;

                -- Handle conversation-based messages (no booking_id)
                IF NEW.conversation_id IS NOT NULL THEN
                    -- Get conversation participants
                    SELECT c.student_id, c.instructor_id INTO v_conversation
                    FROM conversations c WHERE c.id = NEW.conversation_id;

                    IF v_conversation IS NOT NULL THEN
                        -- Build payload with conversation_id for client-side routing
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

                        -- Notify instructor's channel
                        IF v_conversation.instructor_id IS NOT NULL THEN
                            PERFORM pg_notify(
                                'user_' || v_conversation.instructor_id || '_inbox',
                                v_payload::text
                            );
                        END IF;

                        -- Notify student's channel
                        IF v_conversation.student_id IS NOT NULL THEN
                            PERFORM pg_notify(
                                'user_' || v_conversation.student_id || '_inbox',
                                v_payload::text
                            );
                        END IF;
                    END IF;
                    RETURN NEW;
                END IF;

                -- Handle legacy booking-based messages
                IF NEW.booking_id IS NOT NULL THEN
                    -- Get booking participants
                    SELECT b.instructor_id, b.student_id INTO v_booking
                    FROM bookings b WHERE b.id = NEW.booking_id;

                    IF v_booking IS NOT NULL THEN
                        -- Build payload with conversation_id for client-side routing
                        v_payload := jsonb_build_object(
                            'type', 'new_message',
                            'conversation_id', NEW.booking_id,
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

                        -- Notify instructor's channel
                        PERFORM pg_notify(
                            'user_' || v_booking.instructor_id || '_inbox',
                            v_payload::text
                        );

                        -- Notify student's channel
                        PERFORM pg_notify(
                            'user_' || v_booking.student_id || '_inbox',
                            v_payload::text
                        );
                    END IF;
                END IF;

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
            EXECUTE FUNCTION public.notify_new_message();
        """
        )

        # Read receipt trigger: when a notification is marked read, update messages.read_by and notify per-user channel
        op.execute(
            """
            CREATE OR REPLACE FUNCTION public.handle_message_read_receipt()
            RETURNS TRIGGER
            SET search_path = public
            AS $$
            DECLARE
                v_payload JSONB;
                v_booking RECORD;
                v_message RECORD;
                v_recipient_id VARCHAR(26);
            BEGIN
                IF TG_OP = 'UPDATE' AND NEW.is_read = TRUE AND (OLD.is_read IS DISTINCT FROM NEW.is_read) THEN
                    -- Update read_by array
                    UPDATE messages SET read_by = COALESCE(read_by, '[]'::jsonb) || jsonb_build_array(jsonb_build_object('user_id', NEW.user_id, 'read_at', NEW.read_at))
                    WHERE id = NEW.message_id;

                    -- Get message and booking info
                    SELECT m.booking_id, m.sender_id INTO v_message FROM messages m WHERE m.id = NEW.message_id;
                    SELECT b.instructor_id, b.student_id INTO v_booking FROM bookings b WHERE b.id = v_message.booking_id;

                    -- Determine recipient (the message sender, not the reader)
                    v_recipient_id := v_message.sender_id;

                    -- Build payload
                    v_payload := jsonb_build_object(
                        'type', 'read_receipt',
                        'conversation_id', v_message.booking_id,
                        'message_id', NEW.message_id,
                        'reader_id', NEW.user_id,
                        'read_at', NEW.read_at
                    );

                    -- Notify the sender that their message was read
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
        # Use MULTIPOLYGON to support NYC NTA (many are MultiPolygons)
        sa.Column("boundary", Geometry("MULTIPOLYGON", 4326), nullable=True),
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
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("coverage_type", sa.String(20), nullable=True),  # primary|secondary|by_request
        sa.Column("max_distance_miles", sa.Numeric(5, 2), nullable=True),
        sa.PrimaryKeyConstraint("instructor_id", "neighborhood_id"),
    )
    op.create_index(
        "ix_instructor_service_areas_neighborhood_id",
        "instructor_service_areas",
        ["neighborhood_id"],
    )
    op.create_index(
        "ix_instructor_service_areas_instructor",
        "instructor_service_areas",
        ["instructor_id", "is_active"],
    )
    # Helpful index for filtering by instructor and coverage_type
    op.create_index(
        "ix_isa_instructor_coverage",
        "instructor_service_areas",
        ["instructor_id", "coverage_type"],
    )
    # CHECK constraint for coverage_type values
    op.create_check_constraint(
        "ck_instructor_service_areas_coverage_type",
        "instructor_service_areas",
        "coverage_type IS NULL OR coverage_type IN ('primary','secondary','by_request')",
    )

    print("Creating instructor_preferred_places table...")
    op.create_table(
        "instructor_preferred_places",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("address", sa.String(512), nullable=False),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("position", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("place_id", sa.String(255), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instructor_id",
            "kind",
            "address",
            name="uq_instructor_preferred_places_instructor_kind_address",
        ),
        sa.CheckConstraint(
            "kind IN ('teaching_location','public_space')",
            name="ck_instructor_preferred_places_kind",
        ),
    )
    op.create_index(
        "ix_instructor_preferred_places_instructor_kind_position",
        "instructor_preferred_places",
        ["instructor_id", "kind", "position"],
    )

    if is_postgres:
        op.execute(
            """
            CREATE OR REPLACE FUNCTION public.update_updated_at_column()
            RETURNS TRIGGER
            SET search_path = public
            AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER instructor_preferred_places_set_updated_at
            BEFORE UPDATE ON instructor_preferred_places
            FOR EACH ROW
            EXECUTE FUNCTION public.update_updated_at_column();
            """
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

    # ======================================
    # Beta program tables (invites & access)
    # ======================================
    print("Creating beta_invites table...")
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="instructor_beta"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_beta_invites_code"),
    )
    op.create_index("ix_beta_invites_code", "beta_invites", ["code"])  # helps foreign key in access
    op.create_index("ix_beta_invites_email", "beta_invites", ["email"])  # quick lookup for prefill

    print("Creating beta_access table...")
    op.create_table(
        "beta_access",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column(
            "invited_by_code", sa.String(16), sa.ForeignKey("beta_invites.code", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False, server_default="instructor_only"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role", "phase", name="uq_beta_access_user_role_phase"),
    )
    op.create_index("ix_beta_access_user", "beta_access", ["user_id"])  # common filter

    # ======================================
    # Beta settings (admin-controlled toggles)
    # ======================================
    print("Creating beta_settings table...")
    op.create_table(
        "beta_settings",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("beta_disabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("beta_phase", sa.String(32), nullable=False, server_default="instructor_only"),
        sa.Column("allow_signup_without_invite", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
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
        "CASE "
        "WHEN end_time = TIME '00:00:00' AND start_time <> TIME '00:00:00' THEN TRUE "
        "ELSE start_time < end_time "
        "END",
    )

    # Add check constraint for message content length
    op.create_check_constraint(
        "check_message_content_length",
        "messages",
        "LENGTH(content) > 0 AND LENGTH(content) <= 1000",
    )

    # Soft delete consistency constraint: is_deleted and deleted_at must be in sync
    # If is_deleted=FALSE, deleted_at must be NULL; if is_deleted=TRUE, deleted_at must be NOT NULL
    op.create_check_constraint(
        "ck_messages_soft_delete_consistency",
        "messages",
        "(is_deleted = FALSE AND deleted_at IS NULL) OR (is_deleted = TRUE AND deleted_at IS NOT NULL)",
    )

    # Add check constraint for conversation state values
    op.create_check_constraint(
        "ck_conversation_user_state_state",
        "conversation_user_state",
        "state IN ('active', 'archived', 'trashed')",
    )

    # Conversation user state: add conversation_id and migrate from booking_id
    if not hasattr(sa, "Boolean"):  # pragma: no cover - defensive
        pass
    print("Adding conversation_id to conversation_user_state and migrating data...")
    op.add_column(
        "conversation_user_state",
        sa.Column("conversation_id", sa.String(length=26), nullable=True),
    )
    op.drop_constraint(
        "uq_conversation_user_state_user_booking",
        "conversation_user_state",
        type_="unique",
    )
    op.create_foreign_key(
        "fk_conversation_user_state_conversation",
        "conversation_user_state",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        """
        UPDATE conversation_user_state cus
        SET conversation_id = conv.id
        FROM bookings b
        JOIN conversations conv
          ON conv.student_id = b.student_id
         AND conv.instructor_id = b.instructor_id
        WHERE cus.booking_id = b.id
          AND cus.conversation_id IS NULL
        """
    )
    # Delete orphaned records that couldn't be migrated (no matching conversation)
    op.execute(
        """
        DELETE FROM conversation_user_state
        WHERE conversation_id IS NULL
        """
    )
    # Now safe to add NOT NULL constraint
    op.alter_column("conversation_user_state", "conversation_id", nullable=False)
    op.drop_column("conversation_user_state", "booking_id")
    op.create_unique_constraint(
        "uq_conversation_user_state_user_conversation",
        "conversation_user_state",
        ["user_id", "conversation_id"],
    )

    if is_postgres:
        print("Enabling RLS (idempotent) with permissive policies on application tables...")
        exclude_tables = [
            "alembic_version",
            "spatial_ref_sys",
            "geometry_columns",
            "geography_columns",
        ]
        tables = _get_public_tables(exclude_tables)
        for table_name in tables:
            _enable_rls_with_permissive_policy(table_name)
        print(f"RLS ensured on {len(tables)} tables (permissive policies created if missing)")

    # Ensure ON CONFLICT target exists for region boundaries loader
    print("Ensuring region_boundaries unique index for loader UPSERT...")
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE tablename = 'region_boundaries'
                  AND indexname = 'region_boundaries_rtype_rcode_idx'
              ) THEN
                CREATE UNIQUE INDEX region_boundaries_rtype_rcode_idx
                  ON region_boundaries(region_type, region_code);
              END IF;
            END$$;
            """
        )
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

    if is_postgres:
        print("Disabling RLS and removing permissive policies (idempotent)...")
        exclude_tables = [
            "alembic_version",
            "spatial_ref_sys",
            "geometry_columns",
            "geography_columns",
        ]
        tables = _get_public_tables(exclude_tables)
        for table_name in tables:
            _drop_permissive_policy_and_disable_rls(table_name)
        print(f"RLS disabled on {len(tables)} tables (policies dropped if existed)")

    # Drop unique index if present to keep downgrade symmetrical
    print("Dropping region_boundaries unique index if it exists...")
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE tablename = 'region_boundaries'
                  AND indexname = 'region_boundaries_rtype_rcode_idx'
              ) THEN
                DROP INDEX region_boundaries_rtype_rcode_idx;
              END IF;
            END$$;
            """
        )
    )

    print("Dropping platform_config table...")
    op.drop_table("platform_config")

    print("Dropping availability_days table...")
    op.drop_index("ix_avail_days_instructor_date", table_name="availability_days")
    op.drop_table("availability_days")

    print("Dropping audit_log table...")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_audit_log_entity;")
        op.execute("DROP INDEX IF EXISTS ix_audit_log_actor;")
        op.execute("DROP INDEX IF EXISTS ix_audit_log_action;")
        op.execute("DROP TABLE IF EXISTS audit_log;")
    else:
        op.drop_index("ix_audit_log_action", table_name="audit_log")
        op.drop_index("ix_audit_log_actor", table_name="audit_log")
        op.drop_index("ix_audit_log_entity", table_name="audit_log")
        op.drop_table("audit_log")

    print("Dropping notification outbox tables...")
    op.drop_index(
        "ix_notification_delivery_event_type_delivered_at",
        table_name="notification_delivery",
    )
    op.drop_table("notification_delivery")
    op.drop_index("ix_event_outbox_status_next_attempt", table_name="event_outbox")
    op.drop_index("ix_event_outbox_event_type", table_name="event_outbox")
    op.drop_table("event_outbox")

    print("Dropping instructor_preferred_places table...")
    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS instructor_preferred_places_set_updated_at ON instructor_preferred_places;"
        )
        op.execute("DROP FUNCTION IF EXISTS public.update_updated_at_column();")
    op.drop_index(
        "ix_instructor_preferred_places_instructor_kind_position",
        table_name="instructor_preferred_places",
    )
    op.drop_table("instructor_preferred_places")

    # Drop service area tables and spatial indexes first (to avoid dependency issues)
    print("Dropping instructor service area and neighborhoods tables...")
    op.drop_index(
        "ix_instructor_service_areas_neighborhood_id",
        table_name="instructor_service_areas",
    )
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

    op.drop_constraint("ck_messages_soft_delete_consistency", "messages", type_="check")
    op.drop_constraint("check_message_content_length", "messages", type_="check")
    op.drop_constraint("ck_conversation_user_state_state", "conversation_user_state", type_="check")
    op.drop_constraint("check_time_order", "bookings", type_="check")
    op.drop_constraint("check_rate_positive", "bookings", type_="check")
    op.drop_constraint("check_price_non_negative", "bookings", type_="check")
    op.drop_constraint("check_duration_positive", "bookings", type_="check")

    # Revert conversation_user_state back to booking-based linkage
    op.drop_constraint(
        "uq_conversation_user_state_user_conversation",
        "conversation_user_state",
        type_="unique",
    )
    op.drop_constraint(
        "fk_conversation_user_state_conversation",
        "conversation_user_state",
        type_="foreignkey",
    )
    op.add_column(
        "conversation_user_state",
        sa.Column("booking_id", sa.String(length=26), nullable=True),
    )
    op.create_unique_constraint(
        "uq_conversation_user_state_user_booking",
        "conversation_user_state",
        ["user_id", "booking_id"],
    )
    op.drop_column("conversation_user_state", "conversation_id")

    # Drop message notification trigger and function
    if is_postgres:
        print("Dropping message notification trigger and function (PostgreSQL only)...")
        op.execute("DROP TRIGGER IF EXISTS message_insert_notify ON messages;")
        op.execute("DROP FUNCTION IF EXISTS public.notify_new_message();")

    # Drop read receipt trigger and function (Phase 2 additions)
    if is_postgres:
        print("Dropping read receipt trigger and function (PostgreSQL only)...")
        op.execute("DROP TRIGGER IF EXISTS message_read_receipt_notify ON message_notifications;")
        op.execute("DROP FUNCTION IF EXISTS public.handle_message_read_receipt();")

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
    op.drop_index("ix_messages_deleted_at", "messages")
    op.drop_index("ix_messages_booking_id_id", "messages")
    op.drop_index("ix_messages_conversation", "messages")
    if is_postgres:
        op.drop_index("idx_messages_unread_lookup", "messages")
    if is_postgres:
        op.drop_index("ix_messages_booking_nullable", "messages")
    op.drop_table("messages")

    # Drop conversations table
    print("Dropping conversations table...")
    op.drop_index("idx_conversations_last_message", "conversations")
    op.drop_index("idx_conversations_instructor", "conversations")
    op.drop_index("idx_conversations_student", "conversations")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_conversations_pair_unique;")
    else:
        op.drop_constraint("conversations_pair_unique_sqlite", "conversations", type_="unique")
    op.drop_table("conversations")

    print("Dropping bgc_webhook_log table...")
    op.drop_index("ix_bgc_webhook_log_http_status", table_name="bgc_webhook_log")
    op.drop_index("ix_bgc_webhook_log_delivery_id", table_name="bgc_webhook_log")
    op.drop_index("ix_bgc_webhook_log_event_type_created_at", table_name="bgc_webhook_log")
    op.drop_table("bgc_webhook_log")

    print("Dropping bgc_adverse_action_events table...")
    op.drop_index("ix_bgc_adverse_action_events_profile", "bgc_adverse_action_events")
    op.drop_constraint(
        "uq_bgc_adverse_action_events_profile_notice_type",
        "bgc_adverse_action_events",
        type_="unique",
    )
    op.drop_table("bgc_adverse_action_events")

    print("Dropping background_checks history table...")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_background_checks_instructor_created_at_desc;")
        op.execute("DROP INDEX IF EXISTS ix_background_checks_report_id_enc;")
        op.execute("DROP TABLE IF EXISTS background_checks CASCADE;")
    else:
        op.drop_index(
            "ix_background_checks_instructor_created_at",
            table_name="background_checks",
        )
        op.drop_index(
            "ix_background_checks_report_id_enc",
            table_name="background_checks",
        )
        op.drop_table("background_checks")

    print("Dropping background_jobs table...")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_background_jobs_type_status;")
        op.execute("DROP INDEX IF EXISTS ix_background_jobs_status_available;")
        op.execute("DROP TABLE IF EXISTS background_jobs CASCADE;")
    else:
        op.drop_index(
            "ix_background_jobs_type_status",
            table_name="background_jobs",
        )
        op.drop_index(
            "ix_background_jobs_status_available",
            table_name="background_jobs",
        )
        op.drop_table("background_jobs")

    print("Dropping bgc_consent table and background check columns...")
    op.drop_index("ix_bgc_consent_instructor_id", table_name="bgc_consent")
    op.drop_table("bgc_consent")

    op.drop_index("ix_instructor_profiles_checkr_candidate_id", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_checkr_invitation_id", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_bgc_report_id", table_name="instructor_profiles")

    if is_postgres:
        op.execute(
            "ALTER TABLE instructor_profiles DROP CONSTRAINT IF EXISTS ck_instructor_profiles_bgc_env"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP CONSTRAINT IF EXISTS ck_instructor_profiles_bgc_status"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP CONSTRAINT IF EXISTS ck_live_requires_bgc_passed"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_env"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_completed_at"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_report_id"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_valid_until"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_eta"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_invited_at"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_includes_canceled"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_dispute_resolved_at"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_dispute_opened_at"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_dispute_note"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_in_dispute"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_final_adverse_sent_at"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_review_email_sent_at"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_pre_adverse_sent_at"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_pre_adverse_notice_id"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_status"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_report_result"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS checkr_candidate_id"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS checkr_invitation_id"
        )
        op.execute(
            "ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS bgc_note"
        )
    else:
        op.drop_constraint("ck_instructor_profiles_bgc_env", "instructor_profiles", type_="check")
        op.drop_constraint("ck_instructor_profiles_bgc_status", "instructor_profiles", type_="check")
        op.drop_constraint("ck_live_requires_bgc_passed", "instructor_profiles", type_="check")
        op.drop_column("instructor_profiles", "bgc_env")
        op.drop_column("instructor_profiles", "bgc_completed_at")
        op.drop_column("instructor_profiles", "bgc_report_id")
        op.drop_column("instructor_profiles", "bgc_valid_until")
        op.drop_column("instructor_profiles", "bgc_eta")
        op.drop_column("instructor_profiles", "bgc_invited_at")
        op.drop_column("instructor_profiles", "bgc_includes_canceled")
        op.drop_column("instructor_profiles", "bgc_dispute_resolved_at")
        op.drop_column("instructor_profiles", "bgc_dispute_opened_at")
        op.drop_column("instructor_profiles", "bgc_dispute_note")
        op.drop_column("instructor_profiles", "bgc_in_dispute")
        op.drop_column("instructor_profiles", "bgc_final_adverse_sent_at")
        op.drop_column("instructor_profiles", "bgc_review_email_sent_at")
        op.drop_column("instructor_profiles", "bgc_pre_adverse_sent_at")
        op.drop_column("instructor_profiles", "bgc_pre_adverse_notice_id")
        op.drop_column("instructor_profiles", "bgc_status")
        op.drop_column("instructor_profiles", "bgc_report_result")
        op.drop_column("instructor_profiles", "checkr_candidate_id")
        op.drop_column("instructor_profiles", "checkr_invitation_id")
        op.drop_column("instructor_profiles", "bgc_note")

    # Drop alert history table
    print("Dropping alert_history table...")
    op.drop_index("ix_alert_history_severity", "alert_history")
    op.drop_index("ix_alert_history_alert_type", "alert_history")
    op.drop_index("ix_alert_history_created_at", "alert_history")
    op.drop_table("alert_history")

    # Drop beta tables (access first due to FK to invites)
    print("Dropping beta_access and beta_invites tables...")
    op.drop_index("ix_beta_access_user", table_name="beta_access")
    op.drop_table("beta_access")

    # Drop beta_settings table
    op.drop_table("beta_settings")

    op.drop_index("ix_beta_invites_email", table_name="beta_invites")
    op.drop_index("ix_beta_invites_code", table_name="beta_invites")
    op.drop_table("beta_invites")

    print("Final constraints and monitoring tables dropped successfully!")
