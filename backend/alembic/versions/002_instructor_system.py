# backend/alembic/versions/002_instructor_system.py
"""Instructor system - Profiles, services, and background checks

Revision ID: 002_instructor_system
Revises: 001_core_foundation
Create Date: 2025-02-10 00:00:01.000000
"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "002_instructor_system"
down_revision: Union[str, None] = "001_core_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create instructor profiles and services tables."""
    print("Creating instructor system tables...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"
    json_type = sa.dialects.postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    # Create instructor_profiles table
    op.create_table(
        "instructor_profiles",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("min_advance_booking_hours", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("buffer_time_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_tier_pct", sa.Numeric(5, 2), nullable=False, server_default="15.00"),
        sa.Column(
            "is_founding_instructor", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("founding_granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tier_eval_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skills_configured", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identity_verification_session_id", sa.String(255), nullable=True),
        sa.Column("background_check_object_key", sa.String(512), nullable=True),
        sa.Column("background_check_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default="false"),
        # Background check fields
        sa.Column("bgc_status", sa.String(length=20), nullable=True),
        sa.Column("bgc_report_id", sa.Text(), nullable=True),
        sa.Column("bgc_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_env", sa.String(length=20), nullable=False, server_default="sandbox"),
        sa.Column("bgc_valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_includes_canceled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("bgc_in_dispute", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("bgc_dispute_note", sa.Text(), nullable=True),
        sa.Column("bgc_dispute_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_dispute_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_pre_adverse_notice_id", sa.String(length=26), nullable=True),
        sa.Column("bgc_pre_adverse_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_final_adverse_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_review_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bgc_report_result", sa.String(length=32), nullable=True),
        sa.Column("checkr_candidate_id", sa.String(length=64), nullable=True),
        sa.Column("checkr_invitation_id", sa.String(length=64), nullable=True),
        sa.Column("bgc_note", sa.Text(), nullable=True),
        # Slug for URL routing (e.g., "jane-doe-01hgr7kw")
        sa.Column("slug", sa.String(200), nullable=True),
        # Ranking signals
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("profile_completeness", sa.Numeric(3, 2), nullable=True),
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

    op.create_index("ix_instructor_profiles_id", "instructor_profiles", ["id"])
    op.create_index("idx_instructor_profiles_user_id", "instructor_profiles", ["user_id"])
    op.create_index("idx_instructor_profiles_is_live", "instructor_profiles", ["is_live"])
    op.create_index(
        "idx_instructor_profiles_identity_verified_at",
        "instructor_profiles",
        ["identity_verified_at"],
    )
    op.create_index(
        "ix_instructor_profiles_checkr_candidate_id",
        "instructor_profiles",
        ["checkr_candidate_id"],
    )
    op.create_index(
        "ix_instructor_profiles_checkr_invitation_id",
        "instructor_profiles",
        ["checkr_invitation_id"],
    )
    op.create_index(
        "ix_instructor_profiles_bgc_report_id",
        "instructor_profiles",
        ["bgc_report_id"],
    )

    # Partial index for founding instructor count queries (only indexes TRUE rows)
    op.create_index(
        "idx_instructor_profiles_founding_true",
        "instructor_profiles",
        ["is_founding_instructor"],
        postgresql_where=sa.text("is_founding_instructor = true"),
    )
    # Unique index for instructor slug (nullable until populated by seed)
    op.create_index(
        "idx_instructor_profile_slug",
        "instructor_profiles",
        ["slug"],
        unique=True,
    )

    op.create_check_constraint(
        "check_years_experience_non_negative",
        "instructor_profiles",
        "years_experience >= 0",
    )
    op.create_check_constraint(
        "ck_instructor_profiles_bgc_status",
        "instructor_profiles",
        "bgc_status IN ('pending','passed','review','failed','consider','canceled')",
    )
    op.create_check_constraint(
        "ck_instructor_profiles_bgc_env",
        "instructor_profiles",
        "bgc_env IN ('sandbox','production')",
    )
    op.create_check_constraint(
        "ck_live_requires_bgc_passed",
        "instructor_profiles",
        "(is_live = FALSE) OR (bgc_status = 'passed')",
    )

    # Create instructor lifecycle events table
    op.create_table(
        "instructor_lifecycle_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("metadata", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "event_type IN ('registered','profile_submitted','services_configured','bgc_initiated',"
            "'bgc_completed','identity_verified','went_live','paused','reactivated')",
            name="ck_instructor_lifecycle_event_type",
        ),
        comment="Append-only lifecycle events for instructor onboarding funnel",
    )

    op.create_index(
        "idx_lifecycle_events_user_id", "instructor_lifecycle_events", ["user_id"]
    )
    op.create_index(
        "idx_lifecycle_events_type_occurred",
        "instructor_lifecycle_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "idx_lifecycle_events_occurred",
        "instructor_lifecycle_events",
        ["occurred_at"],
    )

    # Create service categories table
    op.create_table(
        "service_categories",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("subtitle", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icon_name", sa.String(50), nullable=True),
        sa.Column("slug", sa.String(50), nullable=True),
        sa.Column("meta_title", sa.String(200), nullable=True),
        sa.Column("meta_description", sa.String(500), nullable=True),
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
        comment="Service categories for organizing the service catalog",
    )

    op.create_index("ix_service_categories_id", "service_categories", ["id"])
    op.create_index("idx_service_categories_display_order", "service_categories", ["display_order"])
    op.create_index(
        "idx_category_slug",
        "service_categories",
        ["slug"],
        unique=True,
    )

    # Create service subcategories table (middle tier of 3-level taxonomy)
    op.create_table(
        "service_subcategories",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("category_id", sa.String(26), nullable=False),
        sa.Column("slug", sa.String(100), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("meta_title", sa.String(200), nullable=True),
        sa.Column("meta_description", sa.String(500), nullable=True),
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
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "name", name="uq_subcategory_category_name"),
        comment="Subcategories within service categories (middle tier of 3-level taxonomy)",
    )

    op.create_index(
        "idx_subcategories_category_id",
        "service_subcategories",
        ["category_id"],
    )
    op.create_index(
        "idx_subcategory_active",
        "service_subcategories",
        ["is_active"],
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_subcategory_slug",
        "service_subcategories",
        ["slug"],
        unique=True,
    )

    # Create filter_definitions table
    op.create_table(
        "filter_definitions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("filter_type", sa.String(20), nullable=False, server_default="multi_select"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_filter_key"),
        sa.CheckConstraint(
            "filter_type IN ('single_select', 'multi_select')",
            name="ck_filter_definitions_type",
        ),
        comment="Global filter type definitions (e.g., grade_level, goal, style)",
    )

    # Create filter_options table
    op.create_table(
        "filter_options",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("filter_definition_id", sa.String(26), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["filter_definition_id"],
            ["filter_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "filter_definition_id", "value", name="uq_filter_option_definition_value"
        ),
        comment="Possible values for each filter definition",
    )

    op.create_index(
        "idx_filter_options_definition_id",
        "filter_options",
        ["filter_definition_id"],
    )

    # Create subcategory_filters table
    op.create_table(
        "subcategory_filters",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("subcategory_id", sa.String(26), nullable=False),
        sa.Column("filter_definition_id", sa.String(26), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["subcategory_id"],
            ["service_subcategories.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["filter_definition_id"],
            ["filter_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subcategory_id",
            "filter_definition_id",
            name="uq_subcategory_filter_definition",
        ),
        comment="Links subcategories to their available filter definitions",
    )

    op.create_index(
        "idx_subcategory_filters_subcategory_id",
        "subcategory_filters",
        ["subcategory_id"],
    )

    # Create subcategory_filter_options table
    op.create_table(
        "subcategory_filter_options",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("subcategory_filter_id", sa.String(26), nullable=False),
        sa.Column("filter_option_id", sa.String(26), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["subcategory_filter_id"],
            ["subcategory_filters.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["filter_option_id"],
            ["filter_options.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subcategory_filter_id",
            "filter_option_id",
            name="uq_subcategory_filter_option",
        ),
        comment="Curated filter option choices per subcategory-filter pair",
    )

    op.create_index(
        "idx_scfo_subcategory_filter_id",
        "subcategory_filter_options",
        ["subcategory_filter_id"],
    )
    op.create_index(
        "idx_sfo_option",
        "subcategory_filter_options",
        ["filter_option_id"],
    )

    # Create service catalog table
    op.create_table(
        "service_catalog",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("subcategory_id", sa.String(26), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(150), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("search_terms", sa.ARRAY(sa.String), nullable=True),
        sa.Column(
            "eligible_age_groups",
            sa.ARRAY(sa.String),
            nullable=False,
            server_default="{toddler,kids,teens,adults}",
        ),
        sa.Column("default_duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("price_floor_in_person_cents", sa.Integer(), nullable=True),
        sa.Column("price_floor_online_cents", sa.Integer(), nullable=True),
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
            ["subcategory_id"],
            ["service_subcategories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "default_duration_minutes BETWEEN 15 AND 480",
            name="chk_catalog_duration",
        ),
        comment="Predefined service catalog with standardized service offerings",
    )

    op.create_index("ix_service_catalog_id", "service_catalog", ["id"])
    op.create_index("idx_service_catalog_subcategory_id", "service_catalog", ["subcategory_id"])
    op.create_index(
        "idx_catalog_slug",
        "service_catalog",
        ["slug"],
        unique=True,
    )
    op.create_index("idx_service_catalog_is_active", "service_catalog", ["is_active"])
    op.create_index(
        "idx_service_catalog_search_terms",
        "service_catalog",
        ["search_terms"],
        postgresql_using="gin",
    )
    op.create_index("idx_service_catalog_display_order", "service_catalog", ["display_order"])
    op.create_index("idx_service_catalog_online_capable", "service_catalog", ["online_capable"])
    op.create_index(
        "idx_service_catalog_embedding",
        "service_catalog",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # Create instructor services table
    op.create_table(
        "instructor_services",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("instructor_profile_id", sa.String(26), nullable=False),
        sa.Column("service_catalog_id", sa.String(26), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("experience_level", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("duration_options", sa.ARRAY(sa.Integer), nullable=False, server_default="{60}"),
        sa.Column("equipment_required", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("levels_taught", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("age_groups", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("location_types", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("max_distance_miles", sa.Integer(), nullable=True),
        sa.Column(
            "filter_selections",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
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

    op.create_index("ix_instructor_services_id", "instructor_services", ["id"])
    op.create_index("idx_instructor_services_instructor_profile_id", "instructor_services", ["instructor_profile_id"])
    op.create_index("idx_instructor_services_service_catalog_id", "instructor_services", ["service_catalog_id"])
    op.create_index(
        "idx_instructor_services_active",
        "instructor_services",
        ["instructor_profile_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "unique_instructor_catalog_service_active",
        "instructor_services",
        ["instructor_profile_id", "service_catalog_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_instructor_services_filter_selections",
        "instructor_services",
        ["filter_selections"],
        postgresql_using="gin",
    )

    op.create_check_constraint("check_hourly_rate_positive", "instructor_services", "hourly_rate > 0")
    op.create_check_constraint(
        "check_duration_options_not_empty", "instructor_services", "array_length(duration_options, 1) > 0"
    )
    op.create_check_constraint(
        "check_duration_options_range",
        "instructor_services",
        "duration_options[1] >= 15 AND duration_options[1] <= 720",
    )

    print("Creating bgc_webhook_log table...")
    op.create_table(
        "bgc_webhook_log",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("delivery_id", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column(
            "payload_json",
            json_type,
            nullable=False,
        ),
        sa.Column("signature", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_bgc_webhook_log_event_type_created_at",
        "bgc_webhook_log",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_bgc_webhook_log_delivery_id",
        "bgc_webhook_log",
        ["delivery_id"],
    )
    op.create_index(
        "ix_bgc_webhook_log_http_status",
        "bgc_webhook_log",
        ["http_status", "created_at"],
    )

    print("Creating background_checks history table...")
    op.create_table(
        "background_checks",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("instructor_id", sa.String(length=26), nullable=False),
        sa.Column("report_id_enc", sa.Text(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("package", sa.Text(), nullable=True),
        sa.Column("env", sa.String(length=20), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_background_checks_report_id_enc",
        "background_checks",
        ["report_id_enc"],
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_background_checks_instructor_created_at_desc "
            "ON background_checks (instructor_id, created_at DESC);"
        )
    else:
        op.create_index(
            "ix_background_checks_instructor_created_at",
            "background_checks",
            ["instructor_id", "created_at"],
        )

    print("Creating bgc_adverse_action_events table...")
    op.create_table(
        "bgc_adverse_action_events",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("profile_id", sa.String(length=26), nullable=False),
        sa.Column("notice_id", sa.String(length=26), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_unique_constraint(
        "uq_bgc_adverse_action_events_profile_notice_type",
        "bgc_adverse_action_events",
        ["profile_id", "notice_id", "event_type"],
    )
    op.create_index(
        "ix_bgc_adverse_action_events_profile",
        "bgc_adverse_action_events",
        ["profile_id"],
    )

    print("Creating bgc_consent table...")
    op.create_table(
        "bgc_consent",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("instructor_id", sa.String(length=26), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("consent_version", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["instructor_id"], ["instructor_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bgc_consent_instructor_id", "bgc_consent", ["instructor_id"])


def downgrade() -> None:
    """Drop instructor system tables."""
    print("Dropping instructor system tables...")

    op.drop_index("idx_lifecycle_events_occurred", table_name="instructor_lifecycle_events")
    op.drop_index(
        "idx_lifecycle_events_type_occurred",
        table_name="instructor_lifecycle_events",
    )
    op.drop_index("idx_lifecycle_events_user_id", table_name="instructor_lifecycle_events")
    op.drop_table("instructor_lifecycle_events")

    op.drop_index("ix_bgc_consent_instructor_id", table_name="bgc_consent")
    op.drop_table("bgc_consent")

    op.drop_index("ix_bgc_adverse_action_events_profile", table_name="bgc_adverse_action_events")
    op.drop_constraint(
        "uq_bgc_adverse_action_events_profile_notice_type",
        "bgc_adverse_action_events",
        type_="unique",
    )
    op.drop_table("bgc_adverse_action_events")

    op.drop_index("ix_background_checks_report_id_enc", table_name="background_checks")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_background_checks_instructor_created_at_desc")
    else:
        op.drop_index("ix_background_checks_instructor_created_at", table_name="background_checks")
    op.drop_table("background_checks")

    op.drop_index("ix_bgc_webhook_log_http_status", table_name="bgc_webhook_log")
    op.drop_index("ix_bgc_webhook_log_delivery_id", table_name="bgc_webhook_log")
    op.drop_index("ix_bgc_webhook_log_event_type_created_at", table_name="bgc_webhook_log")
    op.drop_table("bgc_webhook_log")

    op.drop_constraint("check_duration_options_range", "instructor_services", type_="check")
    op.drop_constraint("check_duration_options_not_empty", "instructor_services", type_="check")
    op.drop_constraint("check_hourly_rate_positive", "instructor_services", type_="check")
    op.drop_index("idx_instructor_services_filter_selections", table_name="instructor_services")
    op.drop_index("unique_instructor_catalog_service_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_service_catalog_id", table_name="instructor_services")
    op.drop_index("idx_instructor_services_instructor_profile_id", table_name="instructor_services")
    op.drop_index("ix_instructor_services_id", table_name="instructor_services")
    op.drop_table("instructor_services")

    op.drop_index("idx_service_catalog_embedding", table_name="service_catalog")
    op.drop_index("idx_service_catalog_online_capable", table_name="service_catalog")
    op.drop_index("idx_service_catalog_display_order", table_name="service_catalog")
    op.drop_index("idx_service_catalog_search_terms", table_name="service_catalog")
    op.drop_index("idx_service_catalog_is_active", table_name="service_catalog")
    op.drop_index("idx_catalog_slug", table_name="service_catalog")
    op.drop_index("idx_service_catalog_subcategory_id", table_name="service_catalog")
    op.drop_index("ix_service_catalog_id", table_name="service_catalog")
    op.drop_table("service_catalog")

    # Drop filter tables (reverse order due to FKs)
    op.drop_index("idx_sfo_option", table_name="subcategory_filter_options")
    op.drop_index("idx_scfo_subcategory_filter_id", table_name="subcategory_filter_options")
    op.drop_table("subcategory_filter_options")
    op.drop_index("idx_subcategory_filters_subcategory_id", table_name="subcategory_filters")
    op.drop_table("subcategory_filters")
    op.drop_index("idx_filter_options_definition_id", table_name="filter_options")
    op.drop_table("filter_options")
    op.drop_table("filter_definitions")

    op.drop_index("idx_subcategory_slug", table_name="service_subcategories")
    op.drop_index("idx_subcategory_active", table_name="service_subcategories")
    op.drop_index("idx_subcategories_category_id", table_name="service_subcategories")
    op.drop_table("service_subcategories")

    op.drop_index("idx_category_slug", table_name="service_categories")
    op.drop_index("idx_service_categories_display_order", table_name="service_categories")
    op.drop_index("ix_service_categories_id", table_name="service_categories")
    op.drop_table("service_categories")

    op.drop_constraint("ck_live_requires_bgc_passed", "instructor_profiles", type_="check")
    op.drop_constraint("ck_instructor_profiles_bgc_env", "instructor_profiles", type_="check")
    op.drop_constraint("ck_instructor_profiles_bgc_status", "instructor_profiles", type_="check")
    op.drop_constraint("check_years_experience_non_negative", "instructor_profiles", type_="check")
    op.drop_index("idx_instructor_profile_slug", table_name="instructor_profiles")
    op.drop_index("idx_instructor_profiles_founding_true", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_bgc_report_id", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_checkr_invitation_id", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_checkr_candidate_id", table_name="instructor_profiles")
    op.drop_index("idx_instructor_profiles_identity_verified_at", table_name="instructor_profiles")
    op.drop_index("idx_instructor_profiles_is_live", table_name="instructor_profiles")
    op.drop_index("idx_instructor_profiles_user_id", table_name="instructor_profiles")
    op.drop_index("ix_instructor_profiles_id", table_name="instructor_profiles")
    op.drop_table("instructor_profiles")
