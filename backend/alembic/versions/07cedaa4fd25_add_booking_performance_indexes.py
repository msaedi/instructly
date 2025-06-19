"""add booking performance indexes

Revision ID: 07cedaa4fd25
Revises: 069646e41eb3
Create Date: 2025-06-16 19:59:54.174851

"""
from typing import Sequence, Union

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07cedaa4fd25"
down_revision: Union[str, None] = "069646e41eb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Get the connection to check existing indexes
    conn = op.get_bind()

    # Check if idx_bookings_date_status already exists
    result = conn.execute(
        text(
            """
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname = 'idx_bookings_date_status'
    """
        )
    )
    if not result.fetchone():
        op.create_index(
            "idx_bookings_date_status", "bookings", ["booking_date", "status"]
        )
        print("Created index: idx_bookings_date_status")
    else:
        print("Index idx_bookings_date_status already exists, skipping")

    # Check if idx_availability_slots_booking_id already exists
    result = conn.execute(
        text(
            """
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname = 'idx_availability_slots_booking_id'
    """
        )
    )
    if not result.fetchone():
        op.create_index(
            "idx_availability_slots_booking_id", "availability_slots", ["booking_id"]
        )
        print("Created index: idx_availability_slots_booking_id")
    else:
        print("Index idx_availability_slots_booking_id already exists, skipping")


def downgrade():
    # Drop indexes if they exist
    conn = op.get_bind()

    # Check and drop idx_bookings_date_status
    result = conn.execute(
        text(
            """
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname = 'idx_bookings_date_status'
    """
        )
    )
    if result.fetchone():
        op.drop_index("idx_bookings_date_status", table_name="bookings")

    # Check and drop idx_availability_slots_booking_id
    result = conn.execute(
        text(
            """
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname = 'idx_availability_slots_booking_id'
    """
        )
    )
    if result.fetchone():
        op.drop_index(
            "idx_availability_slots_booking_id", table_name="availability_slots"
        )
