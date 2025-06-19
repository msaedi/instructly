"""Update booking model for direct time storage

Revision ID: dd2f2efabf3b
Revises: 4d311e06410f
Create Date: 2025-06-09 00:07:52.799199

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd2f2efabf3b"
down_revision: Union[str, None] = "4d311e06410f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add new columns
    op.add_column(
        "bookings", sa.Column("start_time", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("end_time", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("duration_minutes", sa.Integer(), nullable=True)
    )
    op.add_column(
        "bookings", sa.Column("adjusted_total_price", sa.Float(), nullable=True)
    )

    # Migrate existing data from timeslot to direct time storage
    op.execute(
        """
        UPDATE bookings b
        SET
            start_time = ts.start_time,
            end_time = ts.end_time,
            duration_minutes = EXTRACT(EPOCH FROM (ts.end_time - ts.start_time)) / 60,
            original_duration = COALESCE(original_duration, EXTRACT(EPOCH FROM (ts.end_time - ts.start_time)) / 60)
        FROM time_slots ts
        WHERE b.timeslot_id = ts.id
    """
    )

    # Make new columns non-nullable after data migration
    op.alter_column("bookings", "start_time", nullable=False)
    op.alter_column("bookings", "end_time", nullable=False)
    op.alter_column("bookings", "duration_minutes", nullable=False)

    # Note: We're keeping timeslot_id for now to maintain backwards compatibility


def downgrade():
    # Make columns nullable before dropping
    op.alter_column("bookings", "start_time", nullable=True)
    op.alter_column("bookings", "end_time", nullable=True)
    op.alter_column("bookings", "duration_minutes", nullable=True)

    # Drop the new columns
    op.drop_column("bookings", "adjusted_total_price")
    op.drop_column("bookings", "duration_minutes")
    op.drop_column("bookings", "end_time")
    op.drop_column("bookings", "start_time")
