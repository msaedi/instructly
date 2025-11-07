# backend/alembic/versions/003_availability_system.py
"""Availability system - Blackout dates

Revision ID: 003_availability_system
Revises: 002_instructor_system
Create Date: 2024-12-21 00:00:02.000000

This migration creates the blackout_dates table for instructor vacation/unavailable dates.
Note: Availability is now stored in availability_days table (bitmap format) created in migration 006.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_availability_system"
down_revision: Union[str, None] = "002_instructor_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create availability management tables."""
    print("Creating availability system tables...")

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

    # Create indexes for blackout_dates
    op.create_index("ix_blackout_dates_instructor_id", "blackout_dates", ["instructor_id"])
    op.create_index("ix_blackout_dates_date", "blackout_dates", ["date"])
    op.create_index(
        "idx_blackout_dates_instructor_date",
        "blackout_dates",
        ["instructor_id", "date"],
    )

    print("Availability system tables created successfully!")
    print("- Created blackout_dates table for vacation tracking")
    print("- Note: Availability data is stored in availability_days table (bitmap format)")


def downgrade() -> None:
    """Drop availability system tables."""
    print("Dropping availability system tables...")

    # Drop blackout_dates indexes and table
    op.drop_index("idx_blackout_dates_instructor_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_instructor_id", table_name="blackout_dates")
    op.drop_table("blackout_dates")

    print("Availability system tables dropped successfully!")
