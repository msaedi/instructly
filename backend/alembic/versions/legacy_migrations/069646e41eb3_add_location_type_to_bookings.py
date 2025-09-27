"""add location type to bookings

Revision ID: 069646e41eb3
Revises: 6147b9afad02
Create Date: 2025-06-14 14:28:14.151325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "069646e41eb3"
down_revision: Union[str, None] = "6147b9afad02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """
    Add location_type column to bookings table to support the enhanced
    calendar preview feature. This allows instructors to see at a glance
    where lessons will take place.

    Location types:
    - 'student_home': Lesson at student's location
    - 'instructor_location': Lesson at instructor's studio/home
    - 'neutral': Public location (cafe, park, etc.)
    """
    op.add_column(
        "bookings",
        sa.Column(
            "location_type",
            sa.String(50),
            nullable=True,
            comment="Type of meeting location: student_home, instructor_location, or neutral",
        ),
    )

    # Set a default value for existing bookings based on service area
    # This is a reasonable assumption - if service_area is set, it's likely student's home
    op.execute(
        """
        UPDATE bookings
        SET location_type = CASE
            WHEN service_area IS NOT NULL AND service_area != '' THEN 'student_home'
            ELSE 'neutral'
        END
        WHERE location_type IS NULL
    """
    )

    # Add a check constraint to ensure only valid location types
    op.create_check_constraint(
        "ck_bookings_location_type",
        "bookings",
        "location_type IN ('student_home', 'instructor_location', 'neutral')",
    )


def downgrade():
    """Remove location_type column and its constraint."""
    op.drop_constraint("ck_bookings_location_type", "bookings", type_="check")
    op.drop_column("bookings", "location_type")
