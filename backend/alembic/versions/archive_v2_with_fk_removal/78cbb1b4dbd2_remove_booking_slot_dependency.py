# backend/alembic/versions/78cbb1b4dbd2_remove_booking_slot_dependency.py
"""remove_booking_slot_dependency

Revision ID: 78cbb1b4dbd2
Revises: 006_final_constraints
Create Date: 2025-07-01 18:18:06.010271

This migration removes the foreign key constraint between bookings and
availability_slots to implement true layer independence per Work Stream #9.

The availability and booking layers should be independent - bookings are
commitments that exist regardless of availability changes.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "78cbb1b4dbd2"
down_revision: Union[str, None] = "006_final_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the FK constraint to implement layer independence."""
    # Remove the foreign key constraint
    # The constraint name follows PostgreSQL naming convention
    op.drop_constraint("bookings_availability_slot_id_fkey", "bookings", type_="foreignkey")

    # The column is already nullable in the model, so no need to alter it
    # We're keeping the column for historical reference but removing the constraint


def downgrade() -> None:
    """Re-add the FK constraint (not recommended - violates architecture)."""
    # Re-add the foreign key constraint
    op.create_foreign_key(
        "bookings_availability_slot_id_fkey", "bookings", "availability_slots", ["availability_slot_id"], ["id"]
    )
