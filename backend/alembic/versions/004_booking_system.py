# backend/alembic/versions/004_booking_system.py
"""Booking system - Self-contained bookings without availability references

Revision ID: 004_booking_system
Revises: 003_availability_system
Create Date: 2024-12-21 00:00:03.000000

This migration creates the booking system tables with self-contained bookings
that do not reference availability slots. Bookings store all necessary
information (instructor, date, times) directly, achieving complete layer
independence between availability and bookings.

Design principle: Bookings are commitments that exist independently of
availability changes. This allows instructors to modify their availability
without affecting existing bookings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004_booking_system"
down_revision: Union[str, None] = "003_availability_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create booking and password reset tables."""
    print("Creating booking system tables...")

    # Create bookings table with self-contained design
    op.create_table(
        "bookings",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("instructor_service_id", sa.String(26), nullable=False),
        # NO availability_slot_id - bookings are self-contained
        # Booking snapshot data
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        # Optional link to original booking if this was created via reschedule
        sa.Column("rescheduled_from_booking_id", sa.String(26), nullable=True),
        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="CONFIRMED"),
        # Location details
        sa.Column("service_area", sa.String(), nullable=True),
        sa.Column("meeting_location", sa.Text(), nullable=True),
        sa.Column(
            "location_type",
            sa.String(50),
            nullable=True,
            comment="Type of meeting location: student_home, instructor_location, or neutral",
        ),
        # Messages
        sa.Column("student_note", sa.Text(), nullable=True),
        sa.Column("instructor_note", sa.Text(), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        # Cancellation details
        sa.Column("cancelled_by_id", sa.String(26), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        # Payment fields (Phase 1.2)
        sa.Column("payment_method_id", sa.String(255), nullable=True, comment="Stripe payment method ID"),
        sa.Column("payment_intent_id", sa.String(255), nullable=True, comment="Current Stripe payment intent"),
        sa.Column("payment_status", sa.String(50), nullable=True, comment="Computed from latest events"),
        # Foreign keys
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["instructor_service_id"], ["instructor_services.id"]),
        sa.ForeignKeyConstraint(["rescheduled_from_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="Self-contained booking records - no dependency on availability slots",
    )

    # Create all booking indexes
    op.create_index("idx_bookings_student_id", "bookings", ["student_id"])
    op.create_index("idx_bookings_instructor_id", "bookings", ["instructor_id"])
    op.create_index("idx_bookings_date", "bookings", ["booking_date"])
    op.create_index("idx_bookings_status", "bookings", ["status"])
    op.create_index("idx_bookings_created_at", "bookings", ["created_at"])

    # NEW: Index for time-based conflict checking
    # This index optimizes queries that check for booking conflicts by time range
    op.create_index(
        "idx_bookings_instructor_datetime", "bookings", ["instructor_id", "booking_date", "start_time", "end_time"]
    )

    op.create_index(
        "idx_bookings_instructor_date_status",
        "bookings",
        ["instructor_id", "booking_date", "status"],
    )
    # NOTE: idx_bookings_student_status moved to 005_performance_indexes.py
    # with better 3-column design including booking_date for date-filtered queries
    op.create_index("idx_bookings_instructor_service_id", "bookings", ["instructor_service_id"])
    op.create_index("idx_bookings_cancelled_by_id", "bookings", ["cancelled_by_id"])
    op.create_index("idx_bookings_rescheduled_from_id", "bookings", ["rescheduled_from_booking_id"])

    # Add check constraints
    op.create_check_constraint(
        "ck_bookings_status",
        "bookings",
        "status IN ('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW')",
    )

    op.create_check_constraint(
        "ck_bookings_location_type",
        "bookings",
        "location_type IN ('student_home', 'instructor_location', 'neutral')",
    )

    # Create password_reset_tokens table
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Password reset token management",
    )

    # Create indexes for password_reset_tokens
    op.create_index("ix_password_reset_tokens_token", "password_reset_tokens", ["token"], unique=True)
    op.create_index("idx_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    # Create user_favorites table for student-instructor favorites
    op.create_table(
        "user_favorites",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "instructor_id", name="unique_student_instructor_favorite"),
        comment="Students can favorite instructors",
    )

    # Create indexes for user_favorites
    op.create_index("idx_favorites_student", "user_favorites", ["student_id"])
    op.create_index("idx_favorites_instructor", "user_favorites", ["instructor_id"])

    # ======== PAYMENT TABLES ========
    # Create stripe_customers table - Maps users to Stripe customer IDs
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
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="unique_user_stripe_customer"),
        sa.UniqueConstraint("stripe_customer_id", name="unique_stripe_customer_id"),
        comment="Maps users to their Stripe customer IDs",
    )

    # Create indexes for stripe_customers
    op.create_index("idx_stripe_customers_user_id", "stripe_customers", ["user_id"])
    op.create_index("idx_stripe_customers_stripe_customer_id", "stripe_customers", ["stripe_customer_id"])

    # Create stripe_connected_accounts table - Instructor Stripe Connect accounts
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
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["instructor_profile_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instructor_profile_id", name="unique_instructor_stripe_account"),
        sa.UniqueConstraint("stripe_account_id", name="unique_stripe_account_id"),
        comment="Instructor Stripe Connect accounts for receiving payments",
    )

    # Create indexes for stripe_connected_accounts
    op.create_index(
        "idx_stripe_connected_accounts_instructor_profile_id", "stripe_connected_accounts", ["instructor_profile_id"]
    )
    op.create_index(
        "idx_stripe_connected_accounts_stripe_account_id", "stripe_connected_accounts", ["stripe_account_id"]
    )
    op.create_index(
        "idx_stripe_connected_accounts_onboarding_completed", "stripe_connected_accounts", ["onboarding_completed"]
    )

    # Create payment_intents table - Tracks Stripe payment intents for bookings
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, comment="Amount in cents"),
        sa.Column("application_fee", sa.Integer(), nullable=False, comment="Platform fee in cents"),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_payment_intent_id", name="unique_stripe_payment_intent_id"),
        comment="Stripe payment intents for booking payments",
    )

    # Create indexes for payment_intents
    op.create_index("idx_payment_intents_booking_id", "payment_intents", ["booking_id"])
    op.create_index("idx_payment_intents_stripe_payment_intent_id", "payment_intents", ["stripe_payment_intent_id"])
    op.create_index("idx_payment_intents_status", "payment_intents", ["status"])

    # Add check constraint for payment intent status
    op.create_check_constraint(
        "ck_payment_intents_status",
        "payment_intents",
        "status IN ('requires_payment_method', 'requires_confirmation', 'requires_action', 'processing', 'requires_capture', 'canceled', 'succeeded')",
    )

    # Create payment_methods table - Stores user payment methods
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
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="User payment methods (cards)",
    )

    # Create indexes for payment_methods
    op.create_index("idx_payment_methods_user_id", "payment_methods", ["user_id"])
    op.create_index("idx_payment_methods_is_default", "payment_methods", ["is_default"])

    # Create partial unique index: only one default payment method per user
    op.create_index(
        "idx_payment_methods_unique_default_per_user",
        "payment_methods",
        ["user_id", "is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    # Create payment_events table (Phase 1.1)
    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column(
            "event_type",
            sa.String(50),
            nullable=False,
            comment="Types: card_saved, auth_scheduled, auth_attempted, auth_succeeded, auth_failed, capture_scheduled, captured, capture_failed, payout_scheduled, paid_out",
        ),
        sa.Column("event_data", sa.JSON(), nullable=True, comment="Store stripe IDs, amounts, error messages"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Track all payment state changes for bookings",
    )

    # Create indexes for payment_events
    op.create_index("idx_payment_events_booking_id", "payment_events", ["booking_id"])
    op.create_index("idx_payment_events_event_type", "payment_events", ["event_type"])
    op.create_index("idx_payment_events_created_at", "payment_events", ["created_at"])

    # Create platform_credits table (Phase 1.3)
    op.create_table(
        "platform_credits",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column(
            "amount_cents", sa.Integer(), nullable=False, comment="Amount in cents to avoid float precision issues"
        ),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("source_booking_id", sa.String(26), nullable=True, comment="Booking that generated this credit"),
        sa.Column("used_booking_id", sa.String(26), nullable=True, comment="Booking where credit was used"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["used_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="Platform credits for 12-24 hour cancellations",
    )

    # Create indexes for platform_credits
    op.create_index("idx_platform_credits_user_id", "platform_credits", ["user_id"])
    op.create_index("idx_platform_credits_source_booking_id", "platform_credits", ["source_booking_id"])
    op.create_index("idx_platform_credits_used_booking_id", "platform_credits", ["used_booking_id"])
    op.create_index("idx_platform_credits_expires_at", "platform_credits", ["expires_at"])
    # Index for finding unused credits
    op.create_index(
        "idx_platform_credits_unused",
        "platform_credits",
        ["user_id", "expires_at"],
        postgresql_where=sa.text("used_at IS NULL"),
    )

    # Create instructor_payout_events table (analytics)
    op.create_table(
        "instructor_payout_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_profile_id", sa.String(26), nullable=False),
        sa.Column("stripe_account_id", sa.String(255), nullable=False),
        sa.Column("payout_id", sa.String(255), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("arrival_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("failure_message", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["instructor_profile_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Persist payout webhook analytics for instructors",
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

    print("Booking system tables created successfully!")
    print("- Created bookings table with self-contained design + payment fields")
    print("- NO reference to availability_slots for complete layer independence")
    print("- Added time-based conflict checking index")
    print("- Created password_reset_tokens table")
    print("- Created payment tables (stripe_customers, stripe_connected_accounts, payment_intents, payment_methods)")
    print("- Created payment_events table for event-based payment tracking")
    print("- Created platform_credits table for 12-24 hour cancellation credits")

    # ======== REVIEWS TABLES (added pre-launch; safe to include here) ========
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
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booking_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_service_id"], ["instructor_services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_reviews_booking"),
    )

    # Constraints and indexes for reviews
    op.create_check_constraint("ck_reviews_rating_range", "reviews", "rating >= 1 AND rating <= 5")
    op.create_check_constraint(
        "ck_reviews_text_length",
        "reviews",
        "(review_text IS NULL) OR (length(review_text) <= 500)",
    )
    op.create_index("idx_reviews_instructor", "reviews", ["instructor_id"])
    op.create_index("idx_reviews_instructor_service", "reviews", ["instructor_id", "instructor_service_id"])
    op.create_index("idx_reviews_created_at", "reviews", ["created_at"])

    # review_responses
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
    )
    op.create_check_constraint(
        "ck_review_responses_text_length",
        "review_responses",
        "(response_text IS NULL) OR (length(response_text) <= 500)",
    )
    op.create_index("idx_review_responses_review", "review_responses", ["review_id"])

    # review_tips
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
    )
    op.create_check_constraint("ck_review_tips_positive", "review_tips", "amount_cents > 0")
    op.create_index("idx_review_tips_review", "review_tips", ["review_id"])
    op.create_index("idx_review_tips_status", "review_tips", ["status"])


def downgrade() -> None:
    """Drop booking system tables."""
    print("Dropping booking system tables...")

    # ======== DROP PAYMENT TABLES (in reverse order) ========
    # Drop instructor_payout_events indexes and table first (due to FK to instructor_profiles)
    op.drop_index("idx_instructor_payout_events_payout_id", table_name="instructor_payout_events")
    op.drop_index("idx_instructor_payout_events_instructor_profile_id", table_name="instructor_payout_events")
    op.drop_table("instructor_payout_events")

    # Drop platform_credits indexes and table
    op.drop_index("idx_platform_credits_unused", table_name="platform_credits")
    op.drop_index("idx_platform_credits_expires_at", table_name="platform_credits")
    op.drop_index("idx_platform_credits_used_booking_id", table_name="platform_credits")
    op.drop_index("idx_platform_credits_source_booking_id", table_name="platform_credits")
    op.drop_index("idx_platform_credits_user_id", table_name="platform_credits")
    op.drop_table("platform_credits")

    # Drop payment_events indexes and table
    op.drop_index("idx_payment_events_created_at", table_name="payment_events")
    op.drop_index("idx_payment_events_event_type", table_name="payment_events")
    op.drop_index("idx_payment_events_booking_id", table_name="payment_events")
    op.drop_table("payment_events")

    # Drop payment_methods indexes and table
    op.drop_index("idx_payment_methods_unique_default_per_user", table_name="payment_methods")
    op.drop_index("idx_payment_methods_is_default", table_name="payment_methods")
    op.drop_index("idx_payment_methods_user_id", table_name="payment_methods")
    op.drop_table("payment_methods")

    # Drop payment_intents constraint, indexes and table
    op.drop_constraint("ck_payment_intents_status", "payment_intents", type_="check")
    op.drop_index("idx_payment_intents_status", table_name="payment_intents")
    op.drop_index("idx_payment_intents_stripe_payment_intent_id", table_name="payment_intents")
    op.drop_index("idx_payment_intents_booking_id", table_name="payment_intents")
    op.drop_table("payment_intents")

    # Drop stripe_connected_accounts indexes and table
    op.drop_index("idx_stripe_connected_accounts_onboarding_completed", table_name="stripe_connected_accounts")
    op.drop_index("idx_stripe_connected_accounts_stripe_account_id", table_name="stripe_connected_accounts")
    op.drop_index("idx_stripe_connected_accounts_instructor_profile_id", table_name="stripe_connected_accounts")
    op.drop_table("stripe_connected_accounts")

    # Drop stripe_customers indexes and table
    op.drop_index("idx_stripe_customers_stripe_customer_id", table_name="stripe_customers")
    op.drop_index("idx_stripe_customers_user_id", table_name="stripe_customers")
    op.drop_table("stripe_customers")

    # Drop user_favorites indexes and table (if they exist)
    try:
        op.drop_index("idx_favorites_instructor", table_name="user_favorites")
    except:
        pass  # Index might not exist
    try:
        op.drop_index("idx_favorites_student", table_name="user_favorites")
    except:
        pass  # Index might not exist
    try:
        op.drop_table("user_favorites")
    except:
        pass  # Table might not exist

    # Drop password_reset_tokens indexes and table
    op.drop_index("idx_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    # ======== DROP REVIEWS TABLES (in reverse order) ========
    # review_tips
    op.drop_index("idx_review_tips_status", table_name="review_tips")
    op.drop_index("idx_review_tips_review", table_name="review_tips")
    op.drop_constraint("ck_review_tips_positive", "review_tips", type_="check")
    op.drop_constraint("uq_review_tips_review", "review_tips", type_="unique")
    op.drop_table("review_tips")

    # review_responses
    op.drop_index("idx_review_responses_review", table_name="review_responses")
    op.drop_constraint("ck_review_responses_text_length", "review_responses", type_="check")
    op.drop_constraint("uq_review_responses_review", "review_responses", type_="unique")
    op.drop_table("review_responses")

    # reviews
    op.drop_index("idx_reviews_created_at", table_name="reviews")
    op.drop_index("idx_reviews_instructor_service", table_name="reviews")
    op.drop_index("idx_reviews_instructor", table_name="reviews")
    op.drop_constraint("ck_reviews_text_length", "reviews", type_="check")
    op.drop_constraint("ck_reviews_rating_range", "reviews", type_="check")
    op.drop_constraint("uq_reviews_booking", "reviews", type_="unique")
    op.drop_table("reviews")

    # Drop bookings constraints
    op.drop_constraint("ck_bookings_location_type", "bookings", type_="check")
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")

    # Drop bookings indexes
    op.drop_index("idx_bookings_rescheduled_from_id", table_name="bookings")
    op.drop_index("idx_bookings_cancelled_by_id", table_name="bookings")
    op.drop_index("idx_bookings_instructor_service_id", table_name="bookings")
    # NOTE: idx_bookings_student_status removed - now in 005_performance_indexes.py
    op.drop_index("idx_bookings_instructor_date_status", table_name="bookings")
    op.drop_index("idx_bookings_instructor_datetime", table_name="bookings")
    op.drop_index("idx_bookings_created_at", table_name="bookings")
    op.drop_index("idx_bookings_status", table_name="bookings")
    op.drop_index("idx_bookings_date", table_name="bookings")
    op.drop_index("idx_bookings_instructor_id", table_name="bookings")
    op.drop_index("idx_bookings_student_id", table_name="bookings")

    # Drop bookings table
    op.drop_table("bookings")

    print("Booking system tables dropped successfully!")
