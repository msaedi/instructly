# backend/alembic/versions/003_availability_system.py
"""Availability system - Date-specific availability and blackout dates

Revision ID: 003_availability_system
Revises: 002_instructor_system
Create Date: 2024-12-21 00:00:02.000000

This migration creates the availability management tables including
instructor_availability, availability_slots, and blackout_dates.
Note: No booking_id in availability_slots (correct one-way relationship).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_availability_system"
down_revision: Union[str, None] = "002_instructor_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create availability management tables."""
    print("Creating availability system tables...")

    # Create instructor_availability table (formerly specific_date_availability)
    op.create_table(
        "instructor_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_cleared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instructor_id", "date", name="unique_instructor_date"),
        comment="Instructor availability for specific dates",
    )

    # Create indexes for instructor_availability
    op.create_index(
        "idx_instructor_availability_instructor_date",
        "instructor_availability",
        ["instructor_id", "date"],
    )
    op.create_index(
        "idx_availability_date",
        "instructor_availability",
        ["instructor_id", "date"],
    )

    # Create availability_slots table (formerly date_time_slots)
    # IMPORTANT: No booking_id column - one-way relationship only
    op.create_table(
        "availability_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("availability_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(
            ["availability_id"],
            ["instructor_availability.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Time slots within a specific date's availability",
    )

    # Create index for availability_slots
    op.create_index(
        "idx_availability_slots_availability_id",
        "availability_slots",
        ["availability_id"],
    )

    # Create blackout_dates table for instructor vacations/unavailable dates
    op.create_table(
        "blackout_dates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
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

    # Create indexes for blackout_dates
    op.create_index("ix_blackout_dates_instructor_id", "blackout_dates", ["instructor_id"])
    op.create_index("ix_blackout_dates_date", "blackout_dates", ["date"])
    op.create_index(
        "idx_blackout_dates_instructor_date",
        "blackout_dates",
        ["instructor_id", "date"],
    )

    print("Availability system tables created successfully!")
    print("- Created instructor_availability table with is_cleared flag")
    print("- Created availability_slots WITHOUT booking_id (one-way relationship)")
    print("- Created blackout_dates table for vacation tracking")


def downgrade() -> None:
    """Drop availability system tables."""
    print("Dropping availability system tables...")

    # Drop blackout_dates indexes and table
    op.drop_index("idx_blackout_dates_instructor_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_instructor_id", table_name="blackout_dates")
    op.drop_table("blackout_dates")

    # Drop availability_slots index and table
    op.drop_index("idx_availability_slots_availability_id", table_name="availability_slots")
    op.drop_table("availability_slots")

    # Drop instructor_availability indexes and table
    op.drop_index("idx_availability_date", table_name="instructor_availability")
    op.drop_index("idx_instructor_availability_instructor_date", table_name="instructor_availability")
    op.drop_table("instructor_availability")

    print("Availability system tables dropped successfully!")
