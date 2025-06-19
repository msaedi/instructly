"""Add duration and buffer settings for booking system

Revision ID: 4d311e06410f
Revises: 435556c30c6b
Create Date: 2025-06-08 22:31:24.464482

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4d311e06410"
down_revision: Union[str, None] = "435556c30c6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to instructor_profiles
    op.add_column(
        "instructor_profiles",
        sa.Column(
            "default_session_duration",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("buffer_time", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "instructor_profiles",
        sa.Column("minimum_advance_hours", sa.Integer(), nullable=False, server_default="2"),
    )

    # Add duration override to services
    op.add_column("services", sa.Column("duration_override", sa.Integer(), nullable=True))

    # Add adjustment fields to bookings
    op.add_column("bookings", sa.Column("original_duration", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("adjusted_duration", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("adjustment_reason", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "adjustment_reason")
    op.drop_column("bookings", "adjusted_duration")
    op.drop_column("bookings", "original_duration")
    op.drop_column("services", "duration_override")
    op.drop_column("instructor_profiles", "minimum_advance_hours")
    op.drop_column("instructor_profiles", "buffer_time")
    op.drop_column("instructor_profiles", "default_session_duration")
