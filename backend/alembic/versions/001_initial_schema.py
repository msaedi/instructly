# backend/alembic/versions/001_initial_schema.py
"""Initial schema - Users and authentication

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-12-21 00:00:00.000000

This migration creates the foundational tables for user authentication
and role management. All columns are created in their final form to
avoid future modifications.

UPDATED: Using VARCHAR for role instead of ENUM to avoid SQLAlchemy issues
UPDATED: Added account_status field for lifecycle management (active, suspended, deactivated)
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
            "account_status",
            sa.String(20),
            nullable=False,
            server_default="active",
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

    # Add check constraint for account_status values
    op.create_check_constraint(
        "ck_users_account_status",
        "users",
        "account_status IN ('active', 'suspended', 'deactivated')",
    )

    # Create search_history table for tracking user searches (deduplicated for UX)
    op.create_table(
        "search_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),  # Now nullable for guest searches
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column(
            "search_type",
            sa.String(20),
            nullable=False,
            server_default="natural_language",
        ),
        sa.Column("results_count", sa.Integer(), nullable=True),
        # New hybrid model columns
        sa.Column("search_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.Column(
            "last_searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        # Soft delete support
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Guest session tracking
        sa.Column("guest_session_id", sa.String(36), nullable=True),  # UUID as string
        sa.Column("converted_to_user_id", sa.Integer(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["converted_to_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Tracks deduplicated user search history for clean UX",
    )

    # Create search_events table for analytics (append-only)
    op.create_table(
        "search_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_session_id", sa.String(36), nullable=True),
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column(
            "search_type",
            sa.String(20),
            nullable=False,
            server_default="natural_language",
        ),
        sa.Column("results_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column(
            "searched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(36), nullable=True),  # Browser session tracking
        sa.Column("referrer", sa.String(255), nullable=True),
        sa.Column("search_context", sa.JSON(), nullable=True),  # JSONB for PostgreSQL
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Append-only event log for search analytics",
    )

    # Create indexes for search_history
    op.create_index(
        "idx_search_history_user_last_searched",
        "search_history",
        ["user_id", "last_searched_at"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"last_searched_at": "DESC"},
    )

    # Add indexes for analytics
    op.create_index(
        "idx_search_history_deleted",
        "search_history",
        ["deleted_at"],
        unique=False,
    )

    op.create_index(
        "idx_search_history_guest_session",
        "search_history",
        ["guest_session_id"],
        unique=False,
    )

    op.create_index(
        "idx_search_history_conversion",
        "search_history",
        ["converted_to_user_id", "converted_at"],
        unique=False,
    )

    # Add unique constraint to prevent duplicate searches
    # Modified to include guest_session_id for uniqueness
    op.create_unique_constraint(
        "uq_search_history_user_guest_query",
        "search_history",
        ["user_id", "guest_session_id", "search_query"],
    )

    # Add check constraint for search_type values
    op.create_check_constraint(
        "ck_search_history_type",
        "search_history",
        "search_type IN ('natural_language', 'category', 'service_pill', 'filter', 'search_history')",
    )

    # Add check constraint to ensure either user_id OR guest_session_id is present
    op.create_check_constraint(
        "ck_search_history_user_or_guest",
        "search_history",
        "(user_id IS NOT NULL) OR (guest_session_id IS NOT NULL)",
    )

    # Create indexes for search_events table
    op.create_index(
        "idx_search_events_user_id",
        "search_events",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "idx_search_events_guest_session",
        "search_events",
        ["guest_session_id"],
        unique=False,
    )

    op.create_index(
        "idx_search_events_searched_at",
        "search_events",
        ["searched_at"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"searched_at": "DESC"},
    )

    op.create_index(
        "idx_search_events_query",
        "search_events",
        ["search_query"],
        unique=False,
    )

    op.create_index(
        "idx_search_events_session_id",
        "search_events",
        ["session_id"],
        unique=False,
    )

    # Add check constraint for search_type values in search_events
    op.create_check_constraint(
        "ck_search_events_type",
        "search_events",
        "search_type IN ('natural_language', 'category', 'service_pill', 'filter', 'search_history')",
    )

    print("Initial schema created successfully!")
    print("- Created users table with VARCHAR role field and account_status")
    print("- Added check constraints for role and account_status values")
    print("- Created indexes for email lookups")
    print("- Created search_history table for tracking deduplicated user searches")
    print("- Created search_events table for append-only analytics tracking")


def downgrade() -> None:
    """Drop all tables and types created in upgrade."""
    print("Dropping initial schema...")

    # Drop search tables if they exist
    # Using execute to handle if table doesn't exist
    op.execute("DROP TABLE IF EXISTS search_events CASCADE")
    op.execute("DROP TABLE IF EXISTS search_history CASCADE")

    # Drop check constraints first
    op.drop_constraint("ck_users_account_status", "users", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")

    # Drop indexes first
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")

    # Drop tables
    op.drop_table("users")

    # No enum type to drop anymore

    print("Initial schema dropped successfully!")
