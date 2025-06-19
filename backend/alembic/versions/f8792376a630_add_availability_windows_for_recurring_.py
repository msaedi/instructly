"""Add availability windows for recurring schedules

Revision ID: f8792376a630
Revises: dd2f2efabf3b
Create Date: 2025-06-09 21:20:21.729333

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8792376a630"
down_revision: Union[str, None] = "dd2f2efabf3b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Create enum type for days of week
    op.execute(
        "CREATE TYPE day_of_week AS ENUM ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')"
    )

    # Create availability_windows table
    op.create_table(
        "availability_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column(
            "day_of_week",
            sa.Enum(
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                name="day_of_week",
                create_constraint=False,
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("specific_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(day_of_week IS NOT NULL AND specific_date IS NULL) OR (day_of_week IS NULL AND specific_date IS NOT NULL)",
            name="check_day_or_date",
        ),
        sa.CheckConstraint("end_time > start_time", name="check_time_order"),
    )

    op.create_index(
        op.f("ix_availability_windows_instructor_id"),
        "availability_windows",
        ["instructor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_availability_windows_day_of_week"),
        "availability_windows",
        ["day_of_week"],
        unique=False,
    )
    op.create_index(
        op.f("ix_availability_windows_specific_date"),
        "availability_windows",
        ["specific_date"],
        unique=False,
    )

    # Create blackout_dates table for vacation/unavailable dates
    op.create_table(
        "blackout_dates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instructor_id", "date", name="unique_instructor_blackout_date"
        ),
    )

    op.create_index(
        op.f("ix_blackout_dates_instructor_id"),
        "blackout_dates",
        ["instructor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_blackout_dates_date"), "blackout_dates", ["date"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_blackout_dates_date"), table_name="blackout_dates")
    op.drop_index(op.f("ix_blackout_dates_instructor_id"), table_name="blackout_dates")
    op.drop_table("blackout_dates")

    op.drop_index(
        op.f("ix_availability_windows_specific_date"), table_name="availability_windows"
    )
    op.drop_index(
        op.f("ix_availability_windows_day_of_week"), table_name="availability_windows"
    )
    op.drop_index(
        op.f("ix_availability_windows_instructor_id"), table_name="availability_windows"
    )
    op.drop_table("availability_windows")

    op.execute("DROP TYPE day_of_week")
