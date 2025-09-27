"""add performance indexes for bookings and availability

Revision ID: 39c78a4af833
Revises: 07cedaa4fd25
Create Date: 2025-06-16 22:23:43.550568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "39c78a4af833"
down_revision: Union[str, None] = "07cedaa4fd25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add performance indexes for common queries."""
    conn = op.get_bind()

    # Helper function to check if index exists
    def index_exists(index_name: str) -> bool:
        result = conn.execute(
            text(
                """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname = '{index_name}'
        """
            )
        )
        return result.fetchone() is not None

    # Index for instructor dashboard queries
    if not index_exists("idx_bookings_instructor_date_status"):
        op.create_index(
            "idx_bookings_instructor_date_status",
            "bookings",
            ["instructor_id", "booking_date", "status"],
        )
        print("Created index: idx_bookings_instructor_date_status")
    else:
        print("Index idx_bookings_instructor_date_status already exists, skipping")

    # Partial index for slots that have bookings
    if not index_exists("idx_availability_slots_booking"):
        op.create_index(
            "idx_availability_slots_booking",
            "availability_slots",
            ["booking_id"],
            postgresql_where=sa.text("booking_id IS NOT NULL"),
        )
        print("Created index: idx_availability_slots_booking")
    else:
        print("Index idx_availability_slots_booking already exists, skipping")

    # Index for upcoming bookings - WITHOUT the mutable CURRENT_DATE
    # This index will still speed up queries filtering by date and status
    if not index_exists("idx_bookings_upcoming"):
        op.create_index(
            "idx_bookings_upcoming",
            "bookings",
            ["booking_date", "status"],
            postgresql_where=sa.text("status = 'CONFIRMED'"),
        )
        print("Created index: idx_bookings_upcoming")
    else:
        print("Index idx_bookings_upcoming already exists, skipping")

    # Index for student bookings
    if not index_exists("idx_bookings_student_date"):
        op.create_index("idx_bookings_student_date", "bookings", ["student_id", "booking_date"])
        print("Created index: idx_bookings_student_date")
    else:
        print("Index idx_bookings_student_date already exists, skipping")

    # Index for availability date queries
    if not index_exists("idx_availability_date"):
        op.create_index(
            "idx_availability_date",
            "instructor_availability",
            ["instructor_id", "date"],
            unique=False,  # There's already a unique constraint, this is for performance
        )
        print("Created index: idx_availability_date")
    else:
        print("Index idx_availability_date already exists, skipping")


def downgrade() -> None:
    """Remove performance indexes."""
    conn = op.get_bind()

    # Helper function to check if index exists before dropping
    def drop_index_if_exists(index_name: str, table_name: str):
        result = conn.execute(
            text(
                """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname = '{index_name}'
        """
            )
        )
        if result.fetchone():
            op.drop_index(index_name, table_name=table_name)
            print(f"Dropped index: {index_name}")
        else:
            print(f"Index {index_name} doesn't exist, skipping drop")

    drop_index_if_exists("idx_availability_date", "instructor_availability")
    drop_index_if_exists("idx_bookings_student_date", "bookings")
    drop_index_if_exists("idx_bookings_upcoming", "bookings")
    drop_index_if_exists("idx_availability_slots_booking", "availability_slots")
    drop_index_if_exists("idx_bookings_instructor_date_status", "bookings")
