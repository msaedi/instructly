# backend/alembic/versions/003_availability_booking.py
"""Availability + booking system

Revision ID: 003_availability_booking
Revises: 002_instructor_system
Create Date: 2025-02-10 00:00:02.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import LargeBinary
from sqlalchemy.dialects.postgresql import BYTEA

# revision identifiers, used by Alembic.
revision: str = "003_availability_booking"
down_revision: Union[str, None] = "002_instructor_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def upgrade() -> None:
    """Create availability and booking tables."""
    print("Creating availability and booking system tables...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    print("Creating availability_days table...")
    bits_type = BYTEA if is_postgres else LargeBinary
    op.create_table(
        "availability_days",
        sa.Column("instructor_id", sa.String(length=26), nullable=False),
        sa.Column("day_date", sa.Date(), nullable=False),
        sa.Column("bits", bits_type, nullable=False),
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

    # Create blackout_dates table for instructor vacation/unavailable dates
    op.create_table(
        "blackout_dates",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instructor_id", "date", name="unique_instructor_blackout_date"),
        comment="Blackout/vacation dates when instructor is unavailable",
    )
    op.create_index("ix_blackout_dates_instructor_id", "blackout_dates", ["instructor_id"])
    op.create_index("ix_blackout_dates_date", "blackout_dates", ["date"])
    op.create_index(
        "idx_blackout_dates_instructor_date",
        "blackout_dates",
        ["instructor_id", "date"],
    )

    # Create bookings table
    op.create_table(
        "bookings",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("instructor_service_id", sa.String(26), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("booking_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("booking_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lesson_timezone", sa.String(50), nullable=True),
        sa.Column("instructor_tz_at_booking", sa.String(50), nullable=True),
        sa.Column("student_tz_at_booking", sa.String(50), nullable=True),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("rescheduled_from_booking_id", sa.String(26), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="CONFIRMED"),
        sa.Column("service_area", sa.String(), nullable=True),
        sa.Column("meeting_location", sa.Text(), nullable=True),
        sa.Column("location_address", sa.Text(), nullable=True),
        sa.Column("location_lat", sa.Numeric(10, 8), nullable=True),
        sa.Column("location_lng", sa.Numeric(11, 8), nullable=True),
        sa.Column("location_place_id", sa.String(255), nullable=True),
        sa.Column(
            "location_type",
            sa.String(50),
            nullable=True,
            comment="Type of meeting location: student_location, instructor_location, online, or neutral_location",
        ),
        sa.Column("student_note", sa.Text(), nullable=True),
        sa.Column("instructor_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", sa.String(26), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("student_credit_amount", sa.Integer(), nullable=True, comment="Student credit issued in cents (v2.1.1)"),
        sa.Column("refunded_to_card_amount", sa.Integer(), nullable=True, comment="Refunded to card in cents (v2.1.1)"),
        sa.Column("has_locked_funds", sa.Boolean(), nullable=False, server_default=sa.text("false"), comment="New booking has locked funds from reschedule (v2.1.1)"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["instructor_service_id"], ["instructor_services.id"]),
        sa.ForeignKeyConstraint(["rescheduled_from_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="Self-contained booking records - no dependency on availability slots",
    )

    op.create_table(
        "booking_disputes",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("dispute_id", sa.String(100), nullable=True),
        sa.Column("dispute_status", sa.String(30), nullable=True),
        sa.Column("dispute_amount", sa.Integer(), nullable=True),
        sa.Column("dispute_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispute_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_table(
        "booking_transfers",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("stripe_transfer_id", sa.String(100), nullable=True),
        sa.Column("transfer_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transfer_error", sa.String(500), nullable=True),
        sa.Column("transfer_retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("transfer_reversed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("transfer_reversal_id", sa.String(100), nullable=True),
        sa.Column("transfer_reversal_failed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("transfer_reversal_error", sa.String(500), nullable=True),
        sa.Column("transfer_reversal_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transfer_reversal_retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("refund_id", sa.String(100), nullable=True),
        sa.Column("refund_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_error", sa.String(500), nullable=True),
        sa.Column("refund_retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("payout_transfer_id", sa.String(100), nullable=True),
        sa.Column("advanced_payout_transfer_id", sa.String(100), nullable=True),
        sa.Column("payout_transfer_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payout_transfer_error", sa.String(500), nullable=True),
        sa.Column("payout_transfer_retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_table(
        "booking_no_shows",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("no_show_reported_by", sa.String(26), nullable=True),
        sa.Column("no_show_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("no_show_type", sa.String(20), nullable=True),
        sa.Column("no_show_disputed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("no_show_disputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("no_show_dispute_reason", sa.String(500), nullable=True),
        sa.Column("no_show_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("no_show_resolution", sa.String(30), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["no_show_reported_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_index(
        "ix_booking_no_shows_reported_at",
        "booking_no_shows",
        ["no_show_reported_at"],
    )

    op.create_table(
        "booking_locks",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_amount_cents", sa.Integer(), nullable=True),
        sa.Column("lock_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_resolution", sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_table(
        "booking_payments",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("payment_method_id", sa.String(255), nullable=True),
        sa.Column("payment_intent_id", sa.String(255), nullable=True),
        sa.Column("payment_status", sa.String(50), nullable=True),
        sa.Column("auth_scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("auth_last_error", sa.String(500), nullable=True),
        sa.Column("auth_failure_first_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_failure_t13_warning_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credits_reserved_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("settlement_outcome", sa.String(50), nullable=True),
        sa.Column("instructor_payout_amount", sa.Integer(), nullable=True),
        sa.Column("capture_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capture_escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capture_retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("capture_error", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_index("ix_booking_payments_payment_status", "booking_payments", ["payment_status"])
    op.create_index(
        "ix_booking_payments_auth_scheduled_for",
        "booking_payments",
        ["auth_scheduled_for"],
    )

    op.create_table(
        "booking_reschedules",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("late_reschedule_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reschedule_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rescheduled_to_booking_id", sa.String(26), nullable=True),
        sa.Column("original_lesson_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rescheduled_to_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id"),
    )
    op.create_index("idx_bookings_student_id", "bookings", ["student_id"])
    op.create_index("idx_bookings_instructor_id", "bookings", ["instructor_id"])
    op.create_index("idx_bookings_date", "bookings", ["booking_date"])
    op.create_index("idx_bookings_status", "bookings", ["status"])
    op.create_index("idx_bookings_created_at", "bookings", ["created_at"])
    op.create_index("ix_bookings_start_utc", "bookings", ["booking_start_utc"])
    op.create_index(
        "ix_booking_instructor_completed",
        "bookings",
        ["instructor_id", "status", "completed_at"],
        postgresql_where=sa.text("status = 'COMPLETED'"),
    )
    op.create_index(
        "ix_booking_student_completed",
        "bookings",
        ["student_id", "status", "completed_at"],
        postgresql_where=sa.text("status = 'COMPLETED'"),
    )
    op.create_index(
        "idx_bookings_instructor_datetime", "bookings", ["instructor_id", "booking_date", "start_time", "end_time"]
    )
    op.create_index(
        "ix_bookings_instructor_date_status",
        "bookings",
        ["instructor_id", "booking_date", "status"],
    )
    op.create_index(
        "ix_bookings_student_date_status",
        "bookings",
        ["student_id", "booking_date", "status"],
    )
    op.create_index("idx_bookings_instructor_service_id", "bookings", ["instructor_service_id"])
    op.create_index("idx_bookings_cancelled_by_id", "bookings", ["cancelled_by_id"])
    op.create_index("idx_bookings_rescheduled_from_id", "bookings", ["rescheduled_from_booking_id"])
    op.create_index("idx_bookings_location_place_id", "bookings", ["location_place_id"])
    op.create_check_constraint(
        "ck_bookings_status",
        "bookings",
        "status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')",
    )
    op.create_check_constraint(
        "ck_bookings_location_type",
        "bookings",
        "location_type IN ('student_location', 'instructor_location', 'online', 'neutral_location')",
    )
    op.create_check_constraint(
        "ck_booking_payments_payment_status",
        "booking_payments",
        "payment_status IS NULL OR payment_status IN ("
        "'scheduled','authorized','payment_method_required','manual_review','locked','settled'"
        ")",
    )
    op.create_check_constraint(
        "ck_booking_no_shows_no_show_type",
        "booking_no_shows",
        "no_show_type IS NULL OR no_show_type IN ('instructor', 'student')",
    )
    op.create_check_constraint(
        "ck_booking_locks_lock_resolution",
        "booking_locks",
        "lock_resolution IS NULL OR lock_resolution IN ("
        "'new_lesson_completed',"
        "'new_lesson_cancelled_ge12',"
        "'new_lesson_cancelled_lt12',"
        "'instructor_cancelled',"
        "'completed',"
        "'cancelled_by_student',"
        "'cancelled_by_instructor',"
        "'expired'"
        ")",
    )
    op.create_check_constraint(
        "check_duration_positive",
        "bookings",
        "duration_minutes > 0",
    )
    op.create_check_constraint(
        "check_price_non_negative",
        "bookings",
        "total_price >= 0",
    )
    op.create_check_constraint(
        "check_rate_positive",
        "bookings",
        "hourly_rate > 0",
    )
    op.create_check_constraint(
        "check_time_order",
        "bookings",
        "CASE "
        "WHEN end_time < start_time THEN TRUE "
        "ELSE start_time < end_time "
        "END",
    )

    if is_postgres:
        _create_extension_prefer_extensions_schema("btree_gist")
        op.execute(
            """
            ALTER TABLE bookings
              ADD COLUMN IF NOT EXISTS booking_span tsrange
              GENERATED ALWAYS AS (
                tsrange(
                  (booking_date::timestamp + start_time),
                  CASE
                    WHEN end_time < start_time
                      THEN (booking_date::timestamp + interval '1 day' + end_time)
                    ELSE (booking_date::timestamp + end_time)
                  END,
                  '[)'
                )
              ) STORED
            """
        )
        op.execute(
            """
            ALTER TABLE bookings
              ADD CONSTRAINT bookings_no_overlap_per_instructor
              EXCLUDE USING gist (
                instructor_id WITH =,
                booking_span WITH &&
              )
              WHERE (cancelled_at IS NULL AND status IN ('CONFIRMED','COMPLETED','NO_SHOW'))
            """
        )
        op.execute(
            """
            ALTER TABLE bookings
              ADD CONSTRAINT bookings_no_overlap_per_student
              EXCLUDE USING gist (
                student_id WITH =,
                booking_span WITH &&
              )
              WHERE (cancelled_at IS NULL AND status IN ('CONFIRMED','COMPLETED','NO_SHOW'))
            """
        )

    # Payment tables
    op.create_table(
        "stripe_customers",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="unique_user_stripe_customer"),
        sa.UniqueConstraint("stripe_customer_id", name="unique_stripe_customer_id"),
        comment="Maps users to their Stripe customer IDs",
    )
    op.create_index("idx_stripe_customers_user_id", "stripe_customers", ["user_id"])
    op.create_index("idx_stripe_customers_stripe_customer_id", "stripe_customers", ["stripe_customer_id"])

    op.create_table(
        "stripe_connected_accounts",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_profile_id", sa.String(26), nullable=False),
        sa.Column("stripe_account_id", sa.String(255), nullable=False),
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["instructor_profile_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instructor_profile_id", name="unique_instructor_stripe_account"),
        sa.UniqueConstraint("stripe_account_id", name="unique_stripe_account_id"),
        comment="Instructor Stripe Connect account mapping",
    )
    op.create_index("idx_stripe_connected_accounts_instructor_profile_id", "stripe_connected_accounts", ["instructor_profile_id"])
    op.create_index("idx_stripe_connected_accounts_stripe_account_id", "stripe_connected_accounts", ["stripe_account_id"])
    op.create_index("idx_stripe_connected_accounts_onboarding_completed", "stripe_connected_accounts", ["onboarding_completed"])

    op.create_table(
        "payment_intents",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, comment="Amount in cents"),
        sa.Column("application_fee", sa.Integer(), nullable=False, comment="Platform fee in cents"),
        sa.Column("status", sa.String(50), nullable=False),
        # Earnings metadata (stored at payment creation for accurate display)
        sa.Column("base_price_cents", sa.Integer(), nullable=True, comment="Lesson price in cents (hourly_rate * duration)"),
        sa.Column("instructor_tier_pct", sa.Numeric(5, 4), nullable=True, comment="Instructor platform fee rate (e.g., 0.12 for 12%)"),
        sa.Column("instructor_payout_cents", sa.Integer(), nullable=True, comment="Amount transferred to instructor in cents"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_payment_intent_id", name="unique_stripe_payment_intent_id"),
        comment="Stripe payment intents for bookings",
    )
    op.create_index("ix_payment_intents_booking", "payment_intents", ["booking_id"])
    op.create_index("idx_payment_intents_stripe_payment_intent_id", "payment_intents", ["stripe_payment_intent_id"])
    op.create_index("idx_payment_intents_status", "payment_intents", ["status"])
    op.create_check_constraint(
        "ck_payment_intents_status",
        "payment_intents",
        "status IN ('requires_payment_method', 'requires_confirmation', 'requires_action', 'requires_capture', 'processing', 'succeeded', 'canceled')",
    )

    op.create_table(
        "payment_methods",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("stripe_payment_method_id", sa.String(255), nullable=False),
        sa.Column("last4", sa.String(4), nullable=True),
        sa.Column("brand", sa.String(50), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="User payment methods",
    )
    op.create_index("idx_payment_methods_user_id", "payment_methods", ["user_id"])
    op.create_index("idx_payment_methods_is_default", "payment_methods", ["is_default"])
    op.create_index(
        "idx_payment_methods_unique_default_per_user",
        "payment_methods",
        ["user_id", "is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Event-based payment tracking",
    )
    op.create_index("ix_payment_events_booking", "payment_events", ["booking_id"])
    op.create_index("idx_payment_events_event_type", "payment_events", ["event_type"])
    op.create_index("idx_payment_events_created_at", "payment_events", ["created_at"])

    op.create_table(
        "instructor_payout_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_profile_id", sa.String(26), nullable=False),
        sa.Column("stripe_account_id", sa.String(255), nullable=False),
        sa.Column("payout_id", sa.String(255), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("arrival_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_message", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instructor_profile_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Instructor payout analytics",
    )
    op.create_index(
        "idx_instructor_payout_events_instructor_profile_id",
        "instructor_payout_events",
        ["instructor_profile_id"],
    )
    op.create_index(
        "idx_instructor_payout_events_payout_id",
        "instructor_payout_events",
        ["payout_id"],
    )

    # Reviews
    op.create_table(
        "reviews",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("instructor_service_id", sa.String(26), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="published"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column("booking_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_service_id"], ["instructor_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_reviews_booking"),
        comment="Student reviews for bookings",
    )
    op.create_check_constraint("ck_reviews_rating_range", "reviews", "rating >= 1 AND rating <= 5")
    op.create_check_constraint(
        "ck_reviews_text_length",
        "reviews",
        "review_text IS NULL OR LENGTH(review_text) <= 500",
    )
    op.create_index("idx_reviews_instructor", "reviews", ["instructor_id"])
    op.create_index("idx_reviews_instructor_service", "reviews", ["instructor_id", "instructor_service_id"])
    op.create_index("idx_reviews_created_at", "reviews", ["created_at"])

    op.create_table(
        "review_responses",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("review_id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", name="uq_review_responses_review"),
        comment="Instructor responses to reviews",
    )
    op.create_check_constraint(
        "ck_review_responses_text_length",
        "review_responses",
        "response_text IS NULL OR LENGTH(response_text) <= 500",
    )
    op.create_index("idx_review_responses_review", "review_responses", ["review_id"])

    op.create_table(
        "review_tips",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("review_id", sa.String(26), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", name="uq_review_tips_review"),
        comment="Tips attached to reviews",
    )
    op.create_check_constraint("ck_review_tips_positive", "review_tips", "amount_cents > 0")
    op.create_check_constraint(
        "ck_review_tips_status",
        "review_tips",
        "status IN ("
        "'pending',"
        "'processing',"
        "'succeeded',"
        "'failed',"
        "'completed',"
        "'requires_action',"
        "'requires_confirmation',"
        "'requires_payment_method',"
        "'requires_capture',"
        "'canceled',"
        "'cancelled'"
        ")",
    )
    op.create_index("idx_review_tips_review", "review_tips", ["review_id"])
    op.create_index("idx_review_tips_status", "review_tips", ["status"])

    if is_postgres:
        print("Creating check_availability function...")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION check_availability(
              p_instructor_id TEXT,
              p_date DATE,
              p_time_after TIME DEFAULT NULL,
              p_time_before TIME DEFAULT NULL,
              p_duration_minutes INT DEFAULT 60
            ) RETURNS BOOLEAN AS $$
            DECLARE
              v_bits BYTEA;
              v_start_slot INT;
              v_end_slot INT;
              v_duration_slots INT;
              v_contiguous_slots INT := 0;
              v_bit_value INT;
              v_byte_idx INT;
              v_bit_idx INT;
            BEGIN
              SELECT bits INTO v_bits
              FROM availability_days
              WHERE instructor_id = p_instructor_id AND day_date = p_date;

              IF v_bits IS NULL THEN
                RETURN FALSE;
              END IF;

              v_start_slot := COALESCE(
                (EXTRACT(HOUR FROM p_time_after)::INT * 2) + (EXTRACT(MINUTE FROM p_time_after)::INT / 30),
                0
              );
              v_end_slot := COALESCE(
                (EXTRACT(HOUR FROM p_time_before)::INT * 2) + (EXTRACT(MINUTE FROM p_time_before)::INT / 30) - 1,
                47
              );

              v_duration_slots := CEIL(p_duration_minutes::FLOAT / 30);

              FOR i IN v_start_slot..v_end_slot LOOP
                v_byte_idx := i / 8;
                v_bit_idx := 7 - (i % 8);
                v_bit_value := (get_byte(v_bits, v_byte_idx) >> v_bit_idx) & 1;

                IF v_bit_value = 1 THEN
                  v_contiguous_slots := v_contiguous_slots + 1;
                  IF v_contiguous_slots >= v_duration_slots THEN
                    RETURN TRUE;
                  END IF;
                ELSE
                  v_contiguous_slots := 0;
                END IF;
              END LOOP;

              RETURN FALSE;
            END;
            $$ LANGUAGE plpgsql SET search_path = public, extensions;
            """
        )

        print("Creating clear_availability_bits function...")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION clear_availability_bits(
              p_instructor_id TEXT,
              p_booking_date DATE,
              p_start_slot INT,
              p_end_slot INT
            ) RETURNS BOOLEAN AS $$
            DECLARE
              v_bits BYTEA;
              v_byte_idx INT;
              v_bit_idx INT;
              v_mask INT;
            BEGIN
              SELECT bits INTO v_bits
              FROM availability_days
              WHERE instructor_id = p_instructor_id AND day_date = p_booking_date;

              IF v_bits IS NULL THEN
                RETURN FALSE;
              END IF;

              FOR i IN p_start_slot..(p_end_slot - 1) LOOP
                v_byte_idx := i / 8;
                v_bit_idx := 7 - (i % 8);
                v_mask := 255 - (1 << v_bit_idx);
                v_bits := set_byte(v_bits, v_byte_idx, get_byte(v_bits, v_byte_idx) & v_mask);
              END LOOP;

              UPDATE availability_days
              SET bits = v_bits, updated_at = NOW()
              WHERE instructor_id = p_instructor_id AND day_date = p_booking_date;

              RETURN FOUND;
            END;
            $$ LANGUAGE plpgsql SET search_path = public, extensions;
            """
        )


def downgrade() -> None:
    """Drop availability and booking tables."""
    print("Dropping availability and booking system tables...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    if is_postgres:
        op.execute("DROP FUNCTION IF EXISTS clear_availability_bits(TEXT, DATE, INT, INT);")
        op.execute("DROP FUNCTION IF EXISTS check_availability(TEXT, DATE, TIME, TIME, INT);")

    op.drop_index("idx_review_tips_status", table_name="review_tips")
    op.drop_index("idx_review_tips_review", table_name="review_tips")
    op.drop_constraint("ck_review_tips_status", "review_tips", type_="check")
    op.drop_constraint("ck_review_tips_positive", "review_tips", type_="check")
    op.drop_constraint("uq_review_tips_review", "review_tips", type_="unique")
    op.drop_table("review_tips")

    op.drop_index("idx_review_responses_review", table_name="review_responses")
    op.drop_constraint("ck_review_responses_text_length", "review_responses", type_="check")
    op.drop_constraint("uq_review_responses_review", "review_responses", type_="unique")
    op.drop_table("review_responses")

    op.drop_index("idx_reviews_created_at", table_name="reviews")
    op.drop_index("idx_reviews_instructor_service", table_name="reviews")
    op.drop_index("idx_reviews_instructor", table_name="reviews")
    op.drop_constraint("ck_reviews_text_length", "reviews", type_="check")
    op.drop_constraint("ck_reviews_rating_range", "reviews", type_="check")
    op.drop_constraint("uq_reviews_booking", "reviews", type_="unique")
    op.drop_table("reviews")


    op.drop_index("idx_instructor_payout_events_payout_id", table_name="instructor_payout_events")
    op.drop_index("idx_instructor_payout_events_instructor_profile_id", table_name="instructor_payout_events")
    op.drop_table("instructor_payout_events")

    op.drop_index("idx_payment_events_created_at", table_name="payment_events")
    op.drop_index("idx_payment_events_event_type", table_name="payment_events")
    op.drop_index("ix_payment_events_booking", table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index("idx_payment_methods_unique_default_per_user", table_name="payment_methods")
    op.drop_index("idx_payment_methods_is_default", table_name="payment_methods")
    op.drop_index("idx_payment_methods_user_id", table_name="payment_methods")
    op.drop_table("payment_methods")

    op.drop_constraint("ck_payment_intents_status", "payment_intents", type_="check")
    op.drop_index("idx_payment_intents_status", table_name="payment_intents")
    op.drop_index("idx_payment_intents_stripe_payment_intent_id", table_name="payment_intents")
    op.drop_index("ix_payment_intents_booking", table_name="payment_intents")
    op.drop_table("payment_intents")

    op.drop_index("idx_stripe_connected_accounts_onboarding_completed", table_name="stripe_connected_accounts")
    op.drop_index("idx_stripe_connected_accounts_stripe_account_id", table_name="stripe_connected_accounts")
    op.drop_index("idx_stripe_connected_accounts_instructor_profile_id", table_name="stripe_connected_accounts")
    op.drop_table("stripe_connected_accounts")

    op.drop_index("idx_stripe_customers_stripe_customer_id", table_name="stripe_customers")
    op.drop_index("idx_stripe_customers_user_id", table_name="stripe_customers")
    op.drop_table("stripe_customers")

    op.drop_table("booking_payments")
    op.drop_table("booking_reschedules")
    op.drop_table("booking_locks")
    op.drop_table("booking_no_shows")
    op.drop_table("booking_transfers")
    op.drop_table("booking_disputes")

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_bookings_time_conflicts")
        op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_no_overlap_per_student")
        op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_no_overlap_per_instructor")

    op.drop_constraint("check_time_order", "bookings", type_="check")
    op.drop_constraint("check_rate_positive", "bookings", type_="check")
    op.drop_constraint("check_price_non_negative", "bookings", type_="check")
    op.drop_constraint("check_duration_positive", "bookings", type_="check")
    op.drop_constraint("ck_bookings_location_type", "bookings", type_="check")
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.drop_index("idx_bookings_location_place_id", table_name="bookings")
    op.drop_index("idx_bookings_rescheduled_from_id", table_name="bookings")
    op.drop_index("idx_bookings_cancelled_by_id", table_name="bookings")
    op.drop_index("idx_bookings_instructor_service_id", table_name="bookings")
    op.drop_index("ix_bookings_student_date_status", table_name="bookings")
    op.drop_index("ix_bookings_instructor_date_status", table_name="bookings")
    op.drop_index("idx_bookings_instructor_datetime", table_name="bookings")
    op.drop_index("ix_booking_student_completed", table_name="bookings")
    op.drop_index("ix_booking_instructor_completed", table_name="bookings")
    op.drop_index("idx_bookings_created_at", table_name="bookings")
    op.drop_index("idx_bookings_status", table_name="bookings")
    op.drop_index("idx_bookings_date", table_name="bookings")
    op.drop_index("idx_bookings_instructor_id", table_name="bookings")
    op.drop_index("idx_bookings_student_id", table_name="bookings")
    op.drop_index("ix_bookings_start_utc", table_name="bookings")
    op.drop_table("bookings")

    op.drop_index("idx_blackout_dates_instructor_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_instructor_id", table_name="blackout_dates")
    op.drop_table("blackout_dates")

    op.drop_index("ix_avail_days_instructor_date", table_name="availability_days")
    op.drop_table("availability_days")
