# backend/alembic/versions/001_initial_schema.py
"""Initial schema - Users and authentication

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-12-21 00:00:00.000000

This migration creates the foundational tables for user authentication
and role management. All columns are created in their final form to
avoid future modifications.

UPDATED: Using VARCHAR for role instead of ENUM to avoid SQLAlchemy issues
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial user authentication schema."""
    print("Creating initial schema for users and authentication...")

    # NO LONGER CREATING ENUM TYPE - Using VARCHAR instead

    # Create users table with all final columns
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column(
            "role",
            sa.String(10),  # VARCHAR(10) instead of ENUM
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Main user table for authentication and role management",
    )

    # Create indexes for users table
    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_users_id",
        "users",
        ["id"],
        unique=False,
    )
    op.create_index(
        "idx_users_email",
        "users",
        ["email"],
        unique=False,
    )

    # Add check constraint for role values
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('instructor', 'student')",
    )

    print("Initial schema created successfully!")
    print("- Created users table with VARCHAR role field")
    print("- Added check constraint for role values")
    print("- Created indexes for email lookups")


def downgrade() -> None:
    """Drop all tables and types created in upgrade."""
    print("Dropping initial schema...")

    # Drop check constraint first
    op.drop_constraint("ck_users_role", "users", type_="check")

    # Drop indexes first
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")

    # Drop tables
    op.drop_table("users")

    # No enum type to drop anymore

    print("Initial schema dropped successfully!")
