# backend/alembic/versions/003_availability_system.py
"""Availability system - Single-table design for time slots and blackout dates

Revision ID: 003_availability_system
Revises: 002_instructor_system
Create Date: 2024-12-21 00:00:02.000000

This migration creates the availability management tables using a
single-table design for availability_slots (no intermediate
instructor_availability table).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_availability_system"
down_revision: Union[str, None] = "002_instructor_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create availability management tables."""
    print("Creating availability system tables...")

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # Create availability_slots table with single-table design
    op.create_table(
        "availability_slots",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column("specific_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column(
            "slot_span",
            postgresql.TSRANGE(),
            sa.Computed(
                "tsrange("
                "(specific_date::timestamp + start_time), "
                "CASE "
                "WHEN end_time = time '00:00:00' AND start_time <> time '00:00:00' "
                "THEN (specific_date::timestamp + interval '1 day') "
                "ELSE (specific_date::timestamp + end_time) "
                "END, "
                "'[)'"
                ")",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Instructor availability time slots - single table design",
    )

    # Create indexes for availability_slots
    op.create_index(
        "idx_availability_instructor_date",
        "availability_slots",
        ["instructor_id", "specific_date"],
    )
    op.create_index(
        "idx_availability_date",
        "availability_slots",
        ["specific_date"],
    )
    op.create_index(
        "idx_availability_instructor_id",
        "availability_slots",
        ["instructor_id"],
    )

    # Create unique constraint to prevent duplicate slots
    op.create_index(
        "unique_instructor_date_time_slot",
        "availability_slots",
        ["instructor_id", "specific_date", "start_time", "end_time"],
        unique=True,
    )

    op.create_exclude_constraint(
        "availability_no_overlap",
        "availability_slots",
        ("instructor_id", "="),
        ("specific_date", "="),
        ("slot_span", "&&"),
        where=sa.text("deleted_at IS NULL"),
        using="gist",
    )

    # Create blackout_dates table (UNCHANGED from original)
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
    print("- Created availability_slots with single-table design")
    print("- No intermediate instructor_availability table")
    print("- Created blackout_dates table for vacation tracking")


def downgrade() -> None:
    """Drop availability system tables."""
    print("Dropping availability system tables...")

    # Drop blackout_dates indexes and table
    op.drop_index("idx_blackout_dates_instructor_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_date", table_name="blackout_dates")
    op.drop_index("ix_blackout_dates_instructor_id", table_name="blackout_dates")
    op.drop_table("blackout_dates")

    # Drop availability_slots indexes and table
    op.drop_constraint("availability_no_overlap", "availability_slots", type_="exclude")
    op.drop_column("availability_slots", "slot_span")
    op.drop_column("availability_slots", "deleted_at")
    op.drop_index("unique_instructor_date_time_slot", table_name="availability_slots")
    op.drop_index("idx_availability_instructor_id", table_name="availability_slots")
    op.drop_index("idx_availability_date", table_name="availability_slots")
    op.drop_index("idx_availability_instructor_date", table_name="availability_slots")
    op.drop_table("availability_slots")

    print("Availability system tables dropped successfully!")
