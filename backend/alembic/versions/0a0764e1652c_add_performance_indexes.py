"""add performance indexes

Revision ID: 0a0764e1652c
Revises: a0469231e46a
Create Date: 2025-06-10 18:57:41.170347

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a0764e1652c"
down_revision: Union[str, None] = "a0469231e46a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Indexes for frequent lookups
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index(
        "idx_instructor_profiles_user_id", "instructor_profiles", ["user_id"]
    )
    op.create_index(
        "idx_services_instructor_profile_id", "services", ["instructor_profile_id"]
    )
    op.create_index(
        "idx_recurring_availability_instructor_id",
        "recurring_availability",
        ["instructor_id"],
    )
    op.create_index(
        "idx_recurring_availability_day",
        "recurring_availability",
        ["instructor_id", "day_of_week"],
    )
    op.create_index(
        "idx_specific_date_availability_instructor_date",
        "specific_date_availability",
        ["instructor_id", "date"],
    )
    op.create_index(
        "idx_date_time_slots_date_override_id", "date_time_slots", ["date_override_id"]
    )
    op.create_index(
        "idx_blackout_dates_instructor_date",
        "blackout_dates",
        ["instructor_id", "date"],
    )
    op.create_index(
        "idx_bookings_instructor_date", "bookings", ["instructor_id", "start_time"]
    )
    op.create_index("idx_bookings_student_id", "bookings", ["student_id"])


def downgrade():
    op.drop_index("idx_users_email")
    op.drop_index("idx_instructor_profiles_user_id")
    op.drop_index("idx_services_instructor_profile_id")
    op.drop_index("idx_recurring_availability_instructor_id")
    op.drop_index("idx_recurring_availability_day")
    op.drop_index("idx_specific_date_availability_instructor_date")
    op.drop_index("idx_date_time_slots_date_override_id")
    op.drop_index("idx_blackout_dates_instructor_date")
    op.drop_index("idx_bookings_instructor_date")
    op.drop_index("idx_bookings_student_id")
