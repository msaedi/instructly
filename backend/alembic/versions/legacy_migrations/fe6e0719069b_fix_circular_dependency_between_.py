"""fix circular dependency between bookings and availability_slots

Revision ID: fe6e0719069b
Revises: f9d91cce968c
Create Date: 2025-06-20 19:08:06.909605

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "fe6e0719069b"
down_revision: Union[str, None] = "f9d91cce968c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove circular dependency by dropping booking_id from availability_slots."""
    print("Removing circular dependency between bookings and availability_slots...")

    # Drop the foreign key constraint (using the correct name from database)
    op.drop_constraint("fk_availability_slots_booking", "availability_slots", type_="foreignkey")

    # Drop the indexes
    op.drop_index("idx_availability_slots_booking_id", table_name="availability_slots")
    op.drop_index("idx_availability_slots_booking", table_name="availability_slots")

    # Drop the column
    op.drop_column("availability_slots", "booking_id")

    print("Circular dependency removed successfully!")
    print("Note: The relationship is now one-way: bookings → availability_slots")


def downgrade() -> None:
    """Re-add booking_id column if needed (not recommended)."""
    # Add column back
    op.add_column("availability_slots", sa.Column("booking_id", sa.Integer(), nullable=True))

    # Add foreign key with the original name
    op.create_foreign_key("fk_availability_slots_booking", "availability_slots", "bookings", ["booking_id"], ["id"])

    # Re-create indexes
    op.create_index("idx_availability_slots_booking_id", "availability_slots", ["booking_id"])
    op.create_index(
        "idx_availability_slots_booking",
        "availability_slots",
        ["booking_id"],
        postgresql_where=sa.text("booking_id IS NOT NULL"),
    )
