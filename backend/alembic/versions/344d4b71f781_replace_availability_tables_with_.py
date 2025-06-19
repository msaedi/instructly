"""replace availability tables with cleaner design

Revision ID: 344d4b71f781
Revises: 9c712df431e8
Create Date: 2025-06-10 16:32:59.271839

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "344d4b71f781"
down_revision: Union[str, None] = "9c712df431e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Create new tables
    op.create_table(
        "recurring_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column(
            "day_of_week", sa.String(10), nullable=False
        ),  # Just use String instead of Enum
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instructor_id", "day_of_week", "start_time", name="unique_recurring_slot"
        ),
    )
    op.create_index(
        "idx_recurring_instructor_day",
        "recurring_availability",
        ["instructor_id", "day_of_week"],
    )

    op.create_table(
        "specific_date_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_cleared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("instructor_id", "date", name="unique_instructor_date"),
    )
    op.create_index(
        "idx_specific_date", "specific_date_availability", ["instructor_id", "date"]
    )

    op.create_table(
        "date_time_slots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date_override_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.ForeignKeyConstraint(
            ["date_override_id"], ["specific_date_availability.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Migrate data - update the cast to use string
    op.execute(
        """
        -- Migrate recurring availability
        INSERT INTO recurring_availability (instructor_id, day_of_week, start_time, end_time, created_at)
        SELECT instructor_id, day_of_week, start_time, end_time, created_at
        FROM availability_windows
        WHERE is_recurring = true AND day_of_week IS NOT NULL;

        -- Migrate specific date availability (cleared days)
        INSERT INTO specific_date_availability (instructor_id, date, is_cleared, created_at)
        SELECT DISTINCT instructor_id, specific_date, true, MIN(created_at)
        FROM availability_windows
        WHERE specific_date IS NOT NULL AND is_cleared = true
        GROUP BY instructor_id, specific_date;

        -- Migrate specific date availability (with time slots)
        WITH specific_dates AS (
            SELECT DISTINCT instructor_id, specific_date, MIN(created_at) as created_at
            FROM availability_windows
            WHERE specific_date IS NOT NULL AND is_cleared = false AND is_available = true
            GROUP BY instructor_id, specific_date
        )
        INSERT INTO specific_date_availability (instructor_id, date, is_cleared, created_at)
        SELECT instructor_id, specific_date, false, created_at
        FROM specific_dates;

        -- Migrate time slots
        INSERT INTO date_time_slots (date_override_id, start_time, end_time)
        SELECT sda.id, aw.start_time, aw.end_time
        FROM availability_windows aw
        JOIN specific_date_availability sda
            ON aw.instructor_id = sda.instructor_id
            AND aw.specific_date = sda.date
        WHERE aw.specific_date IS NOT NULL
            AND aw.is_cleared = false
            AND aw.is_available = true;
    """
    )

    # Drop old table
    op.drop_table("availability_windows")


def downgrade():
    # This is a one-way migration - we don't support downgrade
    raise NotImplementedError(
        "This migration cannot be reversed. Restore from backup if needed."
    )
