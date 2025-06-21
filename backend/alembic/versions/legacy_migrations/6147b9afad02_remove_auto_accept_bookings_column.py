"""remove auto_accept_bookings column

Revision ID: 6147b9afad02
Revises: c7b9713e4d33
Create Date: 2025-06-12 00:11:11.369559

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6147b9afad02"
down_revision: Union[str, None] = "c7b9713e4d33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the auto_accept_bookings column as we're using instant booking only
    op.drop_column("instructor_profiles", "auto_accept_bookings")


def downgrade() -> None:
    # Re-add the column if we need to rollback
    op.add_column(
        "instructor_profiles",
        sa.Column("auto_accept_bookings", sa.Boolean(), nullable=False, server_default="true"),
    )
