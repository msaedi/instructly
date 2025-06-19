"""add missing foreign key indexes

Revision ID: 915707400fb1
Revises: 39c78a4af833
Create Date: 2025-06-18 20:41:20.872600

"""
from typing import Sequence, Union

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "915707400fb1"
down_revision: Union[str, None] = "39c78a4af833"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ONLY the missing foreign key indexes identified."""
    conn = op.get_bind()

    # Helper to check if index exists
    def index_exists(index_name: str) -> bool:
        result = conn.execute(
            text(
                f"""
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname = '{index_name}'
        """
            )
        )
        return result.fetchone() is not None

    # Only create indexes that are actually missing
    if not index_exists("idx_bookings_availability_slot_id"):
        op.create_index(
            "idx_bookings_availability_slot_id", "bookings", ["availability_slot_id"]
        )
        print("Created index: idx_bookings_availability_slot_id")

    if not index_exists("idx_bookings_service_id"):
        op.create_index("idx_bookings_service_id", "bookings", ["service_id"])
        print("Created index: idx_bookings_service_id")

    if not index_exists("idx_bookings_cancelled_by_id"):
        op.create_index("idx_bookings_cancelled_by_id", "bookings", ["cancelled_by_id"])
        print("Created index: idx_bookings_cancelled_by_id")

    if not index_exists("idx_password_reset_tokens_user_id"):
        op.create_index(
            "idx_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
        )
        print("Created index: idx_password_reset_tokens_user_id")

    # This one might have different names, check both
    if not index_exists("idx_availability_slots_availability_id") and not index_exists(
        "idx_availability_slots_availability"
    ):
        op.create_index(
            "idx_availability_slots_availability_id",
            "availability_slots",
            ["availability_id"],
        )
        print("Created index: idx_availability_slots_availability_id")


def downgrade() -> None:
    """Remove the indexes we added."""
    # Only drop indexes we actually created
    op.drop_index(
        "idx_availability_slots_availability_id",
        table_name="availability_slots",
        if_exists=True,
    )
    op.drop_index(
        "idx_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
        if_exists=True,
    )
    op.drop_index("idx_bookings_cancelled_by_id", table_name="bookings", if_exists=True)
    op.drop_index("idx_bookings_service_id", table_name="bookings", if_exists=True)
    op.drop_index(
        "idx_bookings_availability_slot_id", table_name="bookings", if_exists=True
    )
