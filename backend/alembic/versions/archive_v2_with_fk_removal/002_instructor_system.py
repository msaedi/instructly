# backend/alembic/versions/002_instructor_system.py
"""Instructor system - Profiles and services

Revision ID: 002_instructor_system
Revises: 001_initial_schema
Create Date: 2024-12-21 00:00:01.000000

This migration creates instructor-specific tables including profiles
and services. Services include the is_active flag for soft delete
functionality from the start.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_instructor_system"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create instructor profiles and services tables."""
    print("Creating instructor system tables...")

    # Create instructor_profiles table
    op.create_table(
        "instructor_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("areas_of_service", sa.String(), nullable=True),  # VARCHAR from start, not ARRAY
        sa.Column("min_advance_booking_hours", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("buffer_time_minutes", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        comment="Instructor-specific profile information and preferences",
    )

    # Create indexes for instructor_profiles
    op.create_index("ix_instructor_profiles_id", "instructor_profiles", ["id"])
    op.create_index("idx_instructor_profiles_user_id", "instructor_profiles", ["user_id"])

    # Add check constraint for non-negative years of experience
    op.create_check_constraint(
        "check_years_experience_non_negative",
        "instructor_profiles",
        "years_experience >= 0",
    )

    # Create services table with soft delete support
    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_profile_id", sa.Integer(), nullable=True),
        sa.Column("skill", sa.String(), nullable=False),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("duration_override", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(
            ["instructor_profile_id"],
            ["instructor_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Services offered by instructors with soft delete support",
    )

    # Create indexes for services
    op.create_index("ix_services_id", "services", ["id"])
    op.create_index("idx_services_instructor_profile_id", "services", ["instructor_profile_id"])

    # Create partial index for active services only
    op.create_index(
        "idx_services_active",
        "services",
        ["instructor_profile_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # Create unique constraint for active services only
    # This allows instructors to have multiple inactive services with same skill name
    op.create_index(
        "unique_instructor_skill_active",
        "services",
        ["instructor_profile_id", "skill"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    print("Instructor system tables created successfully!")
    print("- Created instructor_profiles table with areas_of_service as VARCHAR")
    print("- Created services table with is_active flag for soft delete")
    print("- Created unique constraint for active services only")


def downgrade() -> None:
    """Drop instructor system tables."""
    print("Dropping instructor system tables...")

    # Drop services indexes and table
    op.drop_index("unique_instructor_skill_active", table_name="services")
    op.drop_index("idx_services_active", table_name="services")
    op.drop_index("idx_services_instructor_profile_id", table_name="services")
    op.drop_index("ix_services_id", table_name="services")
    op.drop_table("services")

    # Drop instructor_profiles constraint, indexes and table
    op.drop_constraint("check_years_experience_non_negative", "instructor_profiles", type_="check")
    op.drop_index("idx_instructor_profiles_user_id", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_id", table_name="instructor_profiles")
    op.drop_table("instructor_profiles")

    print("Instructor system tables dropped successfully!")
