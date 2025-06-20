"""add is_active to services for soft delete

Revision ID: f9d91cce968c
Revises: 915707400fb1
Create Date: 2025-06-20 09:19:22.580407

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9d91cce968c"
down_revision: Union[str, None] = "915707400fb1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add is_active column with default True
    op.add_column("services", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))

    # Create index for active services (performance optimization)
    op.create_index(
        "idx_services_active",
        "services",
        ["instructor_profile_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # Drop old unique constraint if it exists
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'unique_instructor_skill'
            ) THEN
                ALTER TABLE services DROP CONSTRAINT unique_instructor_skill;
            END IF;
        END $$;
    """
    )

    # Create new unique index for active services only
    # This allows same skill name for inactive services
    op.create_index(
        "unique_instructor_skill_active",
        "services",
        ["instructor_profile_id", "skill"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade():
    # Drop the new indexes
    op.drop_index("unique_instructor_skill_active", table_name="services")
    op.drop_index("idx_services_active", table_name="services")

    # Recreate original unique constraint
    # First, ensure no duplicates exist
    op.execute(
        """
        DELETE FROM services s1
        USING services s2
        WHERE s1.id > s2.id
        AND s1.instructor_profile_id = s2.instructor_profile_id
        AND s1.skill = s2.skill
    """
    )

    # Now create the constraint
    op.create_unique_constraint("unique_instructor_skill", "services", ["instructor_profile_id", "skill"])

    # Remove the column
    op.drop_column("services", "is_active")
