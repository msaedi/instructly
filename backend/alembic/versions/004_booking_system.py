# backend/alembic/versions/004_booking_system.py
"""Booking system - Instant bookings and password reset

Revision ID: 004_booking_system
Revises: 003_availability_system
Create Date: 2024-12-21 00:00:03.000000

This migration creates the booking system tables with instant booking
support and password reset functionality. All columns are in their
final form including location_type.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_booking_system"
down_revision: Union[str, None] = "003_availability_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create booking and password reset tables."""
    print("Creating booking system tables...")

    # Create bookings table with all final columns
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("availability_slot_id", sa.Integer(), nullable=True),
        # Booking snapshot data
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="CONFIRMED"),
        # Location details - including location_type from start
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
        sa.Column("cancelled_by_id", sa.Integer(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["availability_slot_id"], ["availability_slots.id"]),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="Instant booking records between students and instructors",
    )

    # Create all booking indexes
    op.create_index("idx_bookings_student_id", "bookings", ["student_id"])
    op.create_index("idx_bookings_instructor_id", "bookings", ["instructor_id"])
    op.create_index("idx_bookings_date", "bookings", ["booking_date"])
    op.create_index("idx_bookings_status", "bookings", ["status"])
    op.create_index("idx_bookings_created_at", "bookings", ["created_at"])
    op.create_index(
        "idx_bookings_instructor_date_status",
        "bookings",
        ["instructor_id", "booking_date", "status"],
    )
    op.create_index("idx_bookings_student_status", "bookings", ["student_id", "status"])
    op.create_index("idx_bookings_service_id", "bookings", ["service_id"])
    op.create_index("idx_bookings_availability_slot_id", "bookings", ["availability_slot_id"])
    op.create_index("idx_bookings_cancelled_by_id", "bookings", ["cancelled_by_id"])

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
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
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

    print("Booking system tables created successfully!")
    print("- Created bookings table with instant booking defaults")
    print("- Included location_type from start")
    print("- Created password_reset_tokens table")
    print("- Added all necessary check constraints")


def downgrade() -> None:
    """Drop booking system tables."""
    print("Dropping booking system tables...")

    # Drop password_reset_tokens indexes and table
    op.drop_index("idx_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    # Drop bookings constraints
    op.drop_constraint("ck_bookings_location_type", "bookings", type_="check")
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")

    # Drop bookings indexes
    op.drop_index("idx_bookings_cancelled_by_id", table_name="bookings")
    op.drop_index("idx_bookings_availability_slot_id", table_name="bookings")
    op.drop_index("idx_bookings_service_id", table_name="bookings")
    op.drop_index("idx_bookings_student_status", table_name="bookings")
    op.drop_index("idx_bookings_instructor_date_status", table_name="bookings")
    op.drop_index("idx_bookings_created_at", table_name="bookings")
    op.drop_index("idx_bookings_status", table_name="bookings")
    op.drop_index("idx_bookings_date", table_name="bookings")
    op.drop_index("idx_bookings_instructor_id", table_name="bookings")
    op.drop_index("idx_bookings_student_id", table_name="bookings")

    # Drop bookings table
    op.drop_table("bookings")

    print("Booking system tables dropped successfully!")
