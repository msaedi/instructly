"""fix areas_of_service column type to varchar

Revision ID: 3c104525bb35
Revises: 15ea6e11292b
Create Date: 2025-06-11 21:00:39.297406

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c104525bb35"
down_revision: Union[str, None] = "15ea6e11292b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    """Convert areas_of_service from ARRAY to VARCHAR"""
    print("Converting areas_of_service from ARRAY to VARCHAR...")

    # Add a temporary column
    op.add_column(
        "instructor_profiles",
        sa.Column("areas_of_service_temp", sa.String(), nullable=True),
    )

    # Convert array data to comma-separated strings in the temp column
    op.execute(
        """
        UPDATE instructor_profiles
        SET areas_of_service_temp = array_to_string(areas_of_service, ', ')
        WHERE areas_of_service IS NOT NULL;
    """
    )

    # Drop the old column
    op.drop_column("instructor_profiles", "areas_of_service")

    # Rename temp column to the original name
    op.alter_column(
        "instructor_profiles",
        "areas_of_service_temp",
        new_column_name="areas_of_service",
    )

    print("Column type changed successfully!")


def downgrade():
    """Convert back to ARRAY if needed"""
    # Add temporary array column
    op.add_column(
        "instructor_profiles",
        sa.Column(
            "areas_of_service_temp", postgresql.ARRAY(sa.String()), nullable=True
        ),
    )

    # Convert strings back to arrays
    op.execute(
        """
        UPDATE instructor_profiles
        SET areas_of_service_temp = string_to_array(areas_of_service, ', ')
        WHERE areas_of_service IS NOT NULL;
    """
    )

    # Drop the string column
    op.drop_column("instructor_profiles", "areas_of_service")

    # Rename temp column back
    op.alter_column(
        "instructor_profiles",
        "areas_of_service_temp",
        new_column_name="areas_of_service",
    )
