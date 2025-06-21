# backend/alembic/versions/001_initial_schema.py
"""Initial schema - Users and authentication

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-12-21 00:00:00.000000

This migration creates the foundational tables for user authentication
and role management. All columns are created in their final form to
avoid future modifications.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial user authentication schema."""
    print("Creating initial schema for users and authentication...")

    # Create UserRole ENUM type for PostgreSQL with existence check
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE userrole AS ENUM ('instructor', 'student');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """
    )

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
            postgresql.ENUM("instructor", "student", name="userrole", create_type=False),
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

    print("Initial schema created successfully!")
    print("- Created UserRole ENUM type (or skipped if exists)")
    print("- Created users table with authentication fields")
    print("- Created indexes for email lookups")


def downgrade() -> None:
    """Drop all tables and types created in upgrade."""
    print("Dropping initial schema...")

    # Drop indexes first
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")

    # Drop tables
    op.drop_table("users")

    # Drop ENUM type if no other tables are using it
    op.execute(
        """
        DO $$ BEGIN
            DROP TYPE IF EXISTS userrole;
        EXCEPTION
            WHEN dependent_objects_still_exist THEN null;
        END $$;
    """
    )

    print("Initial schema dropped successfully!")
