# backend/alembic/versions/002_instructor_system.py
"""Instructor system - Profiles and service catalog

Revision ID: 002_instructor_system
Revises: 001_initial_schema
Create Date: 2024-12-21 00:00:01.000000

This migration creates instructor-specific tables including profiles
and a three-table service catalog system:

1. service_categories - Categories like Music, Academic, Fitness
2. service_catalog - Predefined services with standardized names
3. instructor_services - Links instructors to catalog services with custom pricing

This replaces the simple services table with a proper catalog system for
better organization and search capabilities.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

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

    # Create service categories table
    op.create_table(
        "service_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("slug"),
        comment="Service categories for organizing the service catalog",
    )

    # Create indexes for service_categories
    op.create_index("ix_service_categories_id", "service_categories", ["id"])
    op.create_index("idx_service_categories_slug", "service_categories", ["slug"])
    op.create_index("idx_service_categories_display_order", "service_categories", ["display_order"])

    # Create service catalog table
    op.create_table(
        "service_catalog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("search_terms", sa.ARRAY(sa.String), nullable=True),
        sa.Column("typical_duration_options", sa.ARRAY(sa.Integer), nullable=False, server_default="{60}"),
        sa.Column("min_recommended_price", sa.Float(), nullable=True),
        sa.Column("max_recommended_price", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
            ["category_id"],
            ["service_categories.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        comment="Predefined service catalog with standardized service offerings",
    )

    # Create indexes for service_catalog
    op.create_index("ix_service_catalog_id", "service_catalog", ["id"])
    op.create_index("idx_service_catalog_category_id", "service_catalog", ["category_id"])
    op.create_index("idx_service_catalog_slug", "service_catalog", ["slug"])
    op.create_index("idx_service_catalog_is_active", "service_catalog", ["is_active"])

    # GIN index for search_terms array
    op.create_index(
        "idx_service_catalog_search_terms",
        "service_catalog",
        ["search_terms"],
        postgresql_using="gin",
    )

    # Create instructor services table (replaces old services table)
    op.create_table(
        "instructor_services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_profile_id", sa.Integer(), nullable=False),
        sa.Column("service_catalog_id", sa.Integer(), nullable=False),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_options", sa.ARRAY(sa.Integer), nullable=False, server_default="{60}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
            ["instructor_profile_id"],
            ["instructor_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["service_catalog_id"],
            ["service_catalog.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Instructor-specific service offerings linked to service catalog",
    )

    # Create indexes for instructor_services
    op.create_index("ix_instructor_services_id", "instructor_services", ["id"])
    op.create_index("idx_instructor_services_instructor_profile_id", "instructor_services", ["instructor_profile_id"])
    op.create_index("idx_instructor_services_service_catalog_id", "instructor_services", ["service_catalog_id"])

    # Create partial index for active services only
    op.create_index(
        "idx_instructor_services_active",
        "instructor_services",
        ["instructor_profile_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # Create unique constraint for active services only
    # This allows instructors to have multiple inactive services for the same catalog item
    op.create_index(
        "unique_instructor_catalog_service_active",
        "instructor_services",
        ["instructor_profile_id", "service_catalog_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    # Add constraints
    op.create_check_constraint("check_hourly_rate_positive", "instructor_services", "hourly_rate > 0")
    op.create_check_constraint(
        "check_duration_options_not_empty", "instructor_services", "array_length(duration_options, 1) > 0"
    )
    op.create_check_constraint(
        "check_duration_options_range",
        "instructor_services",
        "duration_options[1] >= 15 AND duration_options[1] <= 720",
    )
    op.create_check_constraint("check_min_price_positive", "service_catalog", "min_recommended_price > 0")
    op.create_check_constraint("check_max_price_positive", "service_catalog", "max_recommended_price > 0")
    op.create_check_constraint(
        "check_price_range_valid", "service_catalog", "min_recommended_price <= max_recommended_price"
    )

    print("Instructor system tables created successfully!")
    print("- Created instructor_profiles table with areas_of_service as VARCHAR")
    print("- Created service catalog system with three tables:")
    print("  - service_categories: Organize services by category")
    print("  - service_catalog: Predefined services with standardized names")
    print("  - instructor_services: Links instructors to catalog services")
    print("- Added unique constraint for active instructor services only")
    print("- Added constraints for pricing and duration validation")


def downgrade() -> None:
    """Drop instructor system tables."""
    print("Dropping instructor system tables...")

    # Drop instructor_services indexes and table
    op.drop_index("unique_instructor_catalog_service_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_service_catalog_id", table_name="instructor_services")
    op.drop_index("idx_instructor_services_instructor_profile_id", table_name="instructor_services")
    op.drop_index("ix_instructor_services_id", table_name="instructor_services")
    op.drop_table("instructor_services")

    # Drop service_catalog indexes and table
    op.drop_index("idx_service_catalog_search_terms", table_name="service_catalog")
    op.drop_index("idx_service_catalog_is_active", table_name="service_catalog")
    op.drop_index("idx_service_catalog_slug", table_name="service_catalog")
    op.drop_index("idx_service_catalog_category_id", table_name="service_catalog")
    op.drop_index("ix_service_catalog_id", table_name="service_catalog")
    op.drop_table("service_catalog")

    # Drop service_categories indexes and table
    op.drop_index("idx_service_categories_display_order", table_name="service_categories")
    op.drop_index("idx_service_categories_slug", table_name="service_categories")
    op.drop_index("ix_service_categories_id", table_name="service_categories")
    op.drop_table("service_categories")

    # Drop instructor_profiles constraint, indexes and table
    op.drop_constraint("check_years_experience_non_negative", "instructor_profiles", type_="check")
    op.drop_index("idx_instructor_profiles_user_id", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_id", table_name="instructor_profiles")
    op.drop_table("instructor_profiles")

    print("Instructor system tables dropped successfully!")
