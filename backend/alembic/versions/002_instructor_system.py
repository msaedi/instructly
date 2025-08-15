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
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_instructor_system"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create instructor profiles and services tables."""
    print("Creating instructor system tables...")

    # Enable pgvector extension for semantic search
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create instructor_profiles table
    op.create_table(
        "instructor_profiles",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
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
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("subtitle", sa.String(100), nullable=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icon_name", sa.String(50), nullable=True),
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
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("category_id", sa.String(26), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("search_terms", sa.ARRAY(sa.String), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="999"),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("related_services", sa.ARRAY(sa.String(26)), nullable=True),
        sa.Column("online_capable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("requires_certification", sa.Boolean(), nullable=False, server_default="false"),
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

    # Add indexes for new columns
    op.create_index("idx_service_catalog_display_order", "service_catalog", ["display_order"])
    op.create_index("idx_service_catalog_online_capable", "service_catalog", ["online_capable"])

    # Index for vector similarity search
    op.create_index(
        "idx_service_catalog_embedding",
        "service_catalog",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Create instructor services table (replaces old services table)
    op.create_table(
        "instructor_services",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_profile_id", sa.String(26), nullable=False),
        sa.Column("service_catalog_id", sa.String(26), nullable=False),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("experience_level", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("duration_options", sa.ARRAY(sa.Integer), nullable=False, server_default="{60}"),
        sa.Column("equipment_required", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("levels_taught", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("age_groups", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("location_types", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("max_distance_miles", sa.Integer(), nullable=True),
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

    # Create service analytics table
    op.create_table(
        "service_analytics",
        sa.Column("service_catalog_id", sa.String(26), nullable=False),
        sa.Column("search_count_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_count_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("booking_count_7d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("booking_count_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_to_view_rate", sa.Float(), nullable=True),
        sa.Column("view_to_booking_rate", sa.Float(), nullable=True),
        sa.Column("avg_price_booked", sa.Float(), nullable=True),
        sa.Column("price_percentile_25", sa.Float(), nullable=True),
        sa.Column("price_percentile_50", sa.Float(), nullable=True),
        sa.Column("price_percentile_75", sa.Float(), nullable=True),
        sa.Column("most_booked_duration", sa.Integer(), nullable=True),
        sa.Column("duration_distribution", sa.JSON(), nullable=True),
        sa.Column("peak_hours", sa.JSON(), nullable=True),
        sa.Column("peak_days", sa.JSON(), nullable=True),
        sa.Column("seasonality_index", sa.JSON(), nullable=True),
        sa.Column("avg_rating", sa.Float(), nullable=True),
        sa.Column("completion_rate", sa.Float(), nullable=True),
        sa.Column("active_instructors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_weekly_hours", sa.Float(), nullable=True),
        sa.Column("supply_demand_ratio", sa.Float(), nullable=True),
        sa.Column(
            "last_calculated",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_catalog_id"],
            ["service_catalog.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("service_catalog_id"),
        comment="Analytics and intelligence data for each service in the catalog",
    )

    # Create indexes for service_analytics
    op.create_index("idx_service_analytics_search_count_7d", "service_analytics", ["search_count_7d"])
    op.create_index("idx_service_analytics_booking_count_30d", "service_analytics", ["booking_count_30d"])
    op.create_index("idx_service_analytics_last_calculated", "service_analytics", ["last_calculated"])

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

    print("Instructor system tables created successfully!")
    print("- Enabled pgvector extension for semantic search")
    print("- Created instructor_profiles table with areas_of_service as VARCHAR")
    print("- Enhanced service catalog system with:")
    print("  - service_categories: Categories with icon_name support")
    print("  - service_catalog: Services with embeddings, display_order, and online capability")
    print("  - instructor_services: Enhanced with experience level, requirements, and location info")
    print("  - service_analytics: Intelligence data for demand signals and pricing")
    print("- Added vector similarity search index for natural language queries")
    print("- Added constraints for pricing and duration validation")

    # Now that service_catalog exists, create search_event_candidates table (observability)
    op.create_table(
        "search_event_candidates",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("search_event_id", sa.String(26), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False, comment="1-based rank in candidate list"),
        sa.Column("service_catalog_id", sa.String(26), nullable=True),
        sa.Column("score", sa.Float(), nullable=True, comment="primary score used for ordering (e.g., hybrid)"),
        sa.Column("vector_score", sa.Float(), nullable=True, comment="raw vector similarity if available"),
        sa.Column(
            "lexical_score", sa.Float(), nullable=True, comment="text/trigram or token overlap score if available"
        ),
        sa.Column("source", sa.String(20), nullable=True, comment="vector|trgm|exact|hybrid"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["search_event_id"], ["search_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_catalog_id"], ["service_catalog.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="Top-N candidates considered for a search event (observability)",
    )
    op.create_index(
        "idx_search_event_candidates_event_position",
        "search_event_candidates",
        ["search_event_id", "position"],
        unique=True,
    )
    op.create_index(
        "idx_search_event_candidates_service_created",
        "search_event_candidates",
        ["service_catalog_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop instructor system tables."""
    print("Dropping instructor system tables...")

    # Drop observability table and indexes first due to FKs
    op.drop_index("idx_search_event_candidates_service_created", table_name="search_event_candidates")
    op.drop_index("idx_search_event_candidates_event_position", table_name="search_event_candidates")
    op.drop_table("search_event_candidates")

    # Drop service_analytics indexes and table
    op.drop_index("idx_service_analytics_last_calculated", table_name="service_analytics")
    op.drop_index("idx_service_analytics_booking_count_30d", table_name="service_analytics")
    op.drop_index("idx_service_analytics_search_count_7d", table_name="service_analytics")
    op.drop_table("service_analytics")

    # Drop instructor_services indexes and table
    op.drop_index("unique_instructor_catalog_service_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_service_catalog_id", table_name="instructor_services")
    op.drop_index("idx_instructor_services_instructor_profile_id", table_name="instructor_services")
    op.drop_index("ix_instructor_services_id", table_name="instructor_services")
    op.drop_table("instructor_services")

    # Drop service_catalog indexes and table
    op.drop_index("idx_service_catalog_embedding", table_name="service_catalog")
    op.drop_index("idx_service_catalog_online_capable", table_name="service_catalog")
    op.drop_index("idx_service_catalog_display_order", table_name="service_catalog")
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

    # Drop pgvector extension
    op.execute("DROP EXTENSION IF EXISTS vector")

    print("Instructor system tables dropped successfully!")
