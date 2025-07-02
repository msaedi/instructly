# backend/alembic/versions/005_performance_indexes.py
"""Performance indexes - Query optimization

Revision ID: 005_performance_indexes
Revises: 004_booking_system
Create Date: 2024-12-21 00:00:04.000000

This migration adds all performance-related indexes that weren't
created with their base tables. These are primarily composite
and partial indexes for common query patterns.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_performance_indexes"
down_revision: Union[str, None] = "004_booking_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create performance indexes for common query patterns."""
    print("Creating performance indexes...")

    # Booking performance indexes
    op.create_index(
        "idx_bookings_date_status",
        "bookings",
        ["booking_date", "status"],
    )

    # Partial index for upcoming bookings (confirmed only)
    op.create_index(
        "idx_bookings_upcoming",
        "bookings",
        ["booking_date", "status"],
        postgresql_where=sa.text("status = 'CONFIRMED'"),
    )

    # Index for student's bookings by date
    op.create_index(
        "idx_bookings_student_date",
        "bookings",
        ["student_id", "booking_date"],
    )

    # Note: The following indexes were already created in 004_booking_system.py
    # but are listed here for documentation purposes:
    # - idx_bookings_instructor_date_status (composite index for instructor dashboard)
    # - idx_bookings_availability_slot_id (foreign key index)
    # - idx_bookings_service_id (foreign key index)
    # - idx_bookings_cancelled_by_id (foreign key index)

    print("Performance indexes created successfully!")
    print("- Added composite indexes for common query patterns")
    print("- Added partial index for upcoming bookings")


def downgrade() -> None:
    """Drop performance indexes."""
    print("Dropping performance indexes...")

    op.drop_index("idx_bookings_student_date", table_name="bookings")
    op.drop_index("idx_bookings_upcoming", table_name="bookings")
    op.drop_index("idx_bookings_date_status", table_name="bookings")

    print("Performance indexes dropped successfully!")
