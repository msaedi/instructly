"""remove old booking system

Revision ID: de6ba296eafc
Revises: ba513588428b
Create Date: 2025-06-10 21:12:46.042675

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "de6ba296eafc"
down_revision: Union[str, None] = "ba513588428b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Drop the bookings table (this will also drop the foreign key constraint)
    op.drop_table("bookings")

    # Drop the time_slots table if it still exists
    op.execute("DROP TABLE IF EXISTS time_slots CASCADE")

    # Remove any other old booking-related tables
    # Add any other cleanup here


def downgrade():
    # We won't implement downgrade for this cleanup migration
    pass
