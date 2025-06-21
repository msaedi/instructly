"""remove unused time_slots table

Revision ID: a0469231e46a
Revises: 344d4b71f781
Create Date: 2025-06-10 17:50:07.101658

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a0469231e46a"
down_revision: Union[str, None] = "344d4b71f781"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # First, drop the foreign key constraint from bookings to time_slots
    op.drop_constraint("bookings_timeslot_id_fkey", "bookings", type_="foreignkey")

    # Drop the timeslot_id column from bookings
    op.drop_column("bookings", "timeslot_id")

    # Drop the old adjustment tracking columns if they exist
    op.drop_column("bookings", "original_duration")
    op.drop_column("bookings", "adjusted_duration")
    op.drop_column("bookings", "adjustment_reason")
    op.drop_column("bookings", "adjusted_total_price")

    # Drop the time_slots table
    op.drop_table("time_slots")

    # Make the time fields non-nullable (assuming they were populated in previous migration)
    op.alter_column("bookings", "start_time", nullable=False)
    op.alter_column("bookings", "end_time", nullable=False)
    op.alter_column("bookings", "duration_minutes", nullable=False)


def downgrade():
    # Recreate time_slots table
    op.create_table(
        "time_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_time_slots_id"), "time_slots", ["id"], unique=False)

    # Re-add columns to bookings
    op.add_column("bookings", sa.Column("timeslot_id", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("original_duration", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("adjusted_duration", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("adjustment_reason", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("adjusted_total_price", sa.Float(), nullable=True))

    # Add back the foreign key
    op.create_foreign_key("bookings_timeslot_id_fkey", "bookings", "time_slots", ["timeslot_id"], ["id"])

    # Make time fields nullable again
    op.alter_column("bookings", "start_time", nullable=True)
    op.alter_column("bookings", "end_time", nullable=True)
    op.alter_column("bookings", "duration_minutes", nullable=True)
