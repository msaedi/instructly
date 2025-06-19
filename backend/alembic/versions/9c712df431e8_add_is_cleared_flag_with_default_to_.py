"""add is_cleared flag with default to availability_windows

Revision ID: 9c712df431e8
Revises: f8792376a630
Create Date: 2025-06-10 14:59:25.678109

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c712df431e8"
down_revision: Union[str, None] = "f8792376a630"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column with default value
    op.add_column(
        "availability_windows",
        sa.Column("is_cleared", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Update existing markers to have is_cleared=True
    op.execute(
        """
        UPDATE availability_windows
        SET is_cleared = true
        WHERE start_time = '00:00:00'
        AND end_time = '00:01:00'
        AND is_available = false
    """
    )


def downgrade() -> None:
    op.drop_column("availability_windows", "is_cleared")
