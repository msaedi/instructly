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
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# Import enums for seed data
try:
    from app.core.enums import RoleName

    # Use enums if available
    ROLE_ADMIN = RoleName.ADMIN.value
    ROLE_INSTRUCTOR = RoleName.INSTRUCTOR.value
    ROLE_STUDENT = RoleName.STUDENT.value
except ImportError:
    # Fallback to strings if running in isolation
    ROLE_ADMIN = "admin"
    ROLE_INSTRUCTOR = "instructor"
    ROLE_STUDENT = "student"

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


referral_code_status_enum = sa.Enum(
    "active",
    "disabled",
    name="referral_code_status",
    native_enum=True,
)


reward_side_enum = sa.Enum(
    "student",
    "instructor",
    name="reward_side",
    native_enum=True,
)


reward_status_enum = sa.Enum(
    "pending",
    "unlocked",
    "redeemed",
    "void",
    name="reward_status",
    native_enum=True,
)


wallet_txn_type_enum = sa.Enum(
    "referral_credit",
    "fee_rebate",
    name="wallet_txn_type",
    native_enum=True,
)


def upgrade() -> None:
    """Create initial user authentication schema."""
    print("Creating initial schema for users and authentication...")

    # For ULID generation, we'll rely on Python defaults in the models
    # No need for a complex PostgreSQL function
    print("ULID generation will be handled by Python models...")

    # NO LONGER CREATING ENUM TYPE - Using VARCHAR instead

    # Create users table with all final columns
    op.create_table(
        "users",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(50), nullable=False),
        sa.Column("last_name", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("zip_code", sa.String(10), nullable=False),
        # 2FA fields (final form in initial migration)
        sa.Column("totp_secret", sa.String(255), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("totp_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backup_codes", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("two_factor_setup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("two_factor_last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column(
            "account_status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "timezone",
            sa.String(50),
            nullable=False,
            server_default="America/New_York",
        ),
        # Profile picture metadata (added in initial migration to avoid future migrations)
        sa.Column("profile_picture_key", sa.String(255), nullable=True),
        sa.Column("profile_picture_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_picture_version", sa.Integer(), nullable=False, server_default="0"),
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
    # Filter/index for 2FA-enabled lookups
    op.create_index(
        "ix_users_totp_enabled",
        "users",
        ["totp_enabled"],
        unique=False,
    )

    # Add check constraint for account_status values
    op.create_check_constraint(
        "ck_users_account_status",
        "users",
        "account_status IN ('active', 'suspended', 'deactivated')",
    )

    # Create RBAC tables
    print("Creating RBAC tables...")

    # Create roles table
    op.create_table(
        "roles",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="User roles for access control",
    )

    # Create permissions table
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resource", sa.String(50), nullable=True),
        sa.Column("action", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="System permissions for granular access control",
    )

    # Create user_roles junction table
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("role_id", sa.String(26), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        comment="User-to-role mapping",
    )

    # Create role_permissions junction table
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(26), nullable=False),
        sa.Column("permission_id", sa.String(26), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
        comment="Role-to-permission mapping",
    )

    # Create user_permissions for individual overrides
    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("permission_id", sa.String(26), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "permission_id"),
        comment="Individual permission overrides",
    )

    # Create indexes for RBAC tables
    op.create_index("idx_roles_name", "roles", ["name"], unique=True)
    op.create_index("idx_permissions_name", "permissions", ["name"], unique=True)
    op.create_index("idx_permissions_resource_action", "permissions", ["resource", "action"])
    op.create_index("idx_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("idx_user_roles_role_id", "user_roles", ["role_id"])

    # NOTE: Seed data removed from migration
    # Roles and permissions need to be seeded with ULIDs by the application
    print("Skipping seed data - will be handled by application seeding script")

    # Original seed code commented out:
    # op.execute(
    #     f"""
    #     INSERT INTO roles (name, description) VALUES
    #     ('{ROLE_ADMIN}', 'Full system access'),
    #     ('{ROLE_INSTRUCTOR}', 'Can manage own profile and availability'),
    #     ('{ROLE_STUDENT}', 'Can search and book instructors')
    # """
    # )

    # Permissions seed data commented out - will be handled by application

    # Original permissions seed:
    # op.execute(
    #     """
    #     INSERT INTO permissions (name, description, resource, action) VALUES
    #     -- Shared permissions (all authenticated users)
    #     ('manage_own_profile', 'Manage own profile information', 'profile', 'manage'),
    #     ('view_own_bookings', 'View own bookings', 'bookings', 'view'),
    #     ('view_own_search_history', 'View own search history', 'search', 'view'),
    #     ('change_own_password', 'Change own password', 'account', 'update'),
    #     ('delete_own_account', 'Delete own account', 'account', 'delete'),
    #
    #     -- Student-specific permissions
    #     ('view_instructors', 'View instructor profiles', 'instructors', 'view'),
    #     ('view_instructor_availability', 'View instructor availability', 'availability', 'view'),
    #     ('create_bookings', 'Create new bookings', 'bookings', 'create'),
    #     ('cancel_own_bookings', 'Cancel own bookings', 'bookings', 'cancel'),
    #     ('view_booking_details', 'View booking details', 'bookings', 'view'),
    #     ('send_messages', 'Send messages in booking chats', 'messages', 'send'),
    #     ('view_messages', 'View messages in booking chats', 'messages', 'view'),
    #
    #     -- Instructor-specific permissions
    #     ('manage_instructor_profile', 'Manage instructor profile', 'instructor_profile', 'manage'),
    #     ('manage_services', 'Manage offered services', 'services', 'manage'),
    #     ('manage_availability', 'Manage availability schedule', 'availability', 'manage'),
    #     ('view_incoming_bookings', 'View incoming bookings', 'bookings', 'view'),
    #     ('complete_bookings', 'Mark bookings as completed', 'bookings', 'complete'),
    #     ('cancel_student_bookings', 'Cancel student bookings', 'bookings', 'cancel'),
    #     ('view_own_instructor_analytics', 'View own instructor analytics', 'analytics', 'view'),
    #     ('suspend_own_instructor_account', 'Suspend own instructor account', 'account', 'suspend'),
    #
    #     -- Admin permissions
    #     ('view_all_users', 'View all users', 'users', 'view'),
    #     ('manage_users', 'Manage all users', 'users', 'manage'),
    #     ('view_system_analytics', 'View system-wide analytics', 'analytics', 'view'),
    #     ('export_analytics', 'Export analytics data', 'analytics', 'export'),
    #     ('view_all_bookings', 'View all bookings', 'bookings', 'view'),
    #     ('manage_all_bookings', 'Manage all bookings', 'bookings', 'manage'),
    #     ('access_monitoring', 'Access monitoring endpoints', 'monitoring', 'access'),
    #     ('moderate_content', 'Moderate user content', 'content', 'moderate'),
    #     ('moderate_messages', 'Moderate chat messages', 'messages', 'moderate'),
    #     ('view_financials', 'View financial data', 'financials', 'view'),
    #     ('manage_financials', 'Manage financial data', 'financials', 'manage'),
    #     ('manage_roles', 'Manage user roles', 'roles', 'manage'),
    #     ('manage_permissions', 'Manage permissions', 'permissions', 'manage')
    #     """
    # )
    #
    # # Assign permissions to roles
    # # Admin gets everything
    # op.execute(
    #     f"""
    #     INSERT INTO role_permissions (role_id, permission_id)
    #     SELECT r.id, p.id
    #     FROM roles r, permissions p
    #     WHERE r.name = '{ROLE_ADMIN}'
    #     """
    # )
    #
    # # Instructor permissions
    # op.execute(
    #     f"""
    #     INSERT INTO role_permissions (role_id, permission_id)
    #     SELECT r.id, p.id
    #     FROM roles r, permissions p
    #     WHERE r.name = '{ROLE_INSTRUCTOR}'
    #     AND p.name IN (
    #         -- Shared permissions
    #         'manage_own_profile', 'view_own_bookings', 'view_own_search_history',
    #         'change_own_password', 'delete_own_account',
    #         -- Instructor-specific permissions
    #         'manage_instructor_profile', 'manage_services', 'manage_availability',
    #         'view_incoming_bookings', 'complete_bookings', 'cancel_student_bookings',
    #         'view_own_instructor_analytics', 'suspend_own_instructor_account',
    #         'send_messages', 'view_messages'
    #     )
    #     """
    # )
    #
    # # Student permissions
    # op.execute(
    #     f"""
    #     INSERT INTO role_permissions (role_id, permission_id)
    #     SELECT r.id, p.id
    #     FROM roles r, permissions p
    #     WHERE r.name = '{ROLE_STUDENT}'
    #     AND p.name IN (
    #         -- Shared permissions
    #         'manage_own_profile', 'view_own_bookings', 'view_own_search_history',
    #         'change_own_password', 'delete_own_account',
    #         -- Student-specific permissions
    #         'view_instructors', 'view_instructor_availability', 'create_bookings',
    #         'cancel_own_bookings', 'view_booking_details',
    #         'send_messages', 'view_messages'
    #     )
    #     """
    # )

    # Create search_history table for tracking user searches (deduplicated for UX)
    op.create_table(
        "search_history",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=True),  # Now nullable for guest searches
        sa.Column("search_query", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.String(), nullable=False),  # For deduplication
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
        sa.Column("converted_to_user_id", sa.String(26), nullable=True),
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
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=True),
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
        # Enhanced analytics columns
        sa.Column("ip_address", sa.String(45), nullable=True),  # Support IPv6
        sa.Column("ip_address_hash", sa.String(64), nullable=True),  # SHA-256 hash
        sa.Column("geo_data", sa.JSON(), nullable=True),
        sa.Column("device_type", sa.String(20), nullable=True),
        sa.Column("browser_info", sa.JSON(), nullable=True),
        sa.Column("connection_type", sa.String(20), nullable=True),
        sa.Column("page_view_count", sa.Integer(), nullable=True),
        sa.Column("session_duration", sa.Integer(), nullable=True),
        sa.Column("is_returning_user", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("consent_given", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("consent_type", sa.String(50), nullable=True),
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

    # Add index on normalized_query for performance
    op.create_index(
        "idx_search_history_normalized_query",
        "search_history",
        ["normalized_query"],
        unique=False,
    )

    # Add unique constraints to prevent race conditions
    # We need actual constraints, not partial indexes, for ON CONFLICT to work
    # First, create a regular unique index for user searches
    op.create_index(
        "uq_search_history_user_normalized_query",
        "search_history",
        ["user_id", "normalized_query"],
        unique=True,
    )

    # Create a regular unique index for guest searches
    op.create_index(
        "uq_search_history_guest_normalized_query",
        "search_history",
        ["guest_session_id", "normalized_query"],
        unique=True,
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

    # Create search_interactions table
    op.create_table(
        "search_interactions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("search_event_id", sa.String(26), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("interaction_type", sa.String(50), nullable=False),  # 'click', 'hover', 'bookmark'
        sa.Column("instructor_id", sa.String(26), nullable=True),
        sa.Column("result_position", sa.Integer(), nullable=True),
        sa.Column("time_to_interaction", sa.Float(), nullable=True),
        sa.Column("interaction_duration", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["search_event_id"],
            ["search_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Tracks user interactions with search results",
    )

    # Create indexes for search_interactions
    op.create_index("idx_search_interactions_event_id", "search_interactions", ["search_event_id"])
    op.create_index("idx_search_interactions_type", "search_interactions", ["interaction_type"])
    op.create_index("idx_search_interactions_instructor", "search_interactions", ["instructor_id"])

    # Add analytics-specific indexes for search_events
    op.create_index("idx_search_events_geo_country", "search_events", [sa.text("(geo_data->>'country_code')")])
    op.create_index("idx_search_events_geo_borough", "search_events", [sa.text("(geo_data->>'borough')")])
    op.create_index("idx_search_events_geo_postal", "search_events", [sa.text("(geo_data->>'postal_code')")])
    op.create_index("idx_search_events_device_type", "search_events", ["device_type"])
    op.create_index(
        "idx_search_events_created_at",
        "search_events",
        ["created_at"],
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index("idx_search_events_user_date", "search_events", ["user_id", "created_at"])

    # ------------------------------------------------------------------
    # Referral program schema (Theta Park Slope Beta)
    # ------------------------------------------------------------------
    print("Creating referral program enums and tables...")
    bind = op.get_bind()
    referral_code_status_enum.create(bind, checkfirst=True)
    reward_side_enum.create(bind, checkfirst=True)
    reward_status_enum.create(bind, checkfirst=True)
    wallet_txn_type_enum.create(bind, checkfirst=True)

    op.create_table(
        "referral_codes",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("vanity_slug", sa.String(64), nullable=True, unique=True),
        sa.Column(
            "referrer_user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "disabled",
                name="referral_code_status",
                native_enum=True,
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Referral codes issued to referrers",
    )

    op.create_index(
        "idx_referral_codes_referrer_user_id",
        "referral_codes",
        ["referrer_user_id"],
    )

    op.create_table(
        "referral_clicks",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "code_id",
            UUID(as_uuid=True),
            sa.ForeignKey("referral_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_fp_hash", sa.String(64), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("ua_hash", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Referral link clicks with coarse device attribution",
    )

    op.create_index(
        "idx_referral_clicks_code_ts",
        "referral_clicks",
        ["code_id", "ts"],
        postgresql_using="btree",
        postgresql_ops={"ts": "DESC"},
    )

    op.create_table(
        "referral_attributions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "code_id",
            UUID(as_uuid=True),
            sa.ForeignKey("referral_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_id", "referred_user_id", name="uq_referral_attribution_pair"),
        comment="Attribution of a referred user to a referral code",
    )

    op.create_table(
        "referral_rewards",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "referrer_user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "side",
            sa.Enum(
                "student",
                "instructor",
                name="reward_side",
                native_enum=True,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "unlocked",
                "redeemed",
                "void",
                name="reward_status",
                native_enum=True,
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("unlock_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expire_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rule_version", sa.String(16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_cents >= 0", name="ck_referral_rewards_amount_non_negative"),
        comment="Reward units generated by referrals",
    )

    op.create_index(
        "idx_referral_rewards_referrer_status",
        "referral_rewards",
        ["referrer_user_id", "status"],
    )
    op.create_index(
        "idx_referral_rewards_referred_side",
        "referral_rewards",
        ["referred_user_id", "side"],
    )

    op.create_table(
        "wallet_transactions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.Enum(
                "referral_credit",
                "fee_rebate",
                name="wallet_txn_type",
                native_enum=True,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column(
            "related_reward_id",
            UUID(as_uuid=True),
            sa.ForeignKey("referral_rewards.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_cents >= 0", name="ck_wallet_transactions_amount_non_negative"),
        comment="Ledger of wallet transactions generated by referral system",
    )

    op.create_index(
        "idx_wallet_transactions_user_created_at",
        "wallet_transactions",
        ["user_id", "created_at"],
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},
    )

    op.create_table(
        "referral_limits",
        sa.Column(
            "user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("daily_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weekly_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("month_cap", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trust_score", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
        comment="Rate limits and trust scores for referral program",
    )

    print("Initial schema created successfully!")
    print("- Created users table WITHOUT role field (using RBAC)")
    print("- Created RBAC tables: roles, permissions, user_roles, role_permissions, user_permissions")
    print("- Seeded initial roles (admin, instructor, student) and permissions")
    print("- Created search_history table for tracking deduplicated user searches")
    print("- Created search_events table with enhanced analytics columns")
    print("- Created search_interactions table for tracking result interactions")
    print("- Added analytics-specific indexes for performance")


def downgrade() -> None:
    """Drop all tables and types created in upgrade."""
    print("Dropping initial schema...")

    bind = op.get_bind()

    # Drop referral program tables and enums first (added after initial schema)
    op.drop_table("referral_limits")

    op.drop_index("idx_wallet_transactions_user_created_at", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")

    op.drop_index("idx_referral_rewards_referred_side", table_name="referral_rewards")
    op.drop_index("idx_referral_rewards_referrer_status", table_name="referral_rewards")
    op.drop_table("referral_rewards")

    op.drop_table("referral_attributions")

    op.drop_index("idx_referral_clicks_code_ts", table_name="referral_clicks")
    op.drop_table("referral_clicks")

    op.drop_index("idx_referral_codes_referrer_user_id", table_name="referral_codes")
    op.drop_table("referral_codes")

    wallet_txn_type_enum.drop(bind, checkfirst=True)
    reward_status_enum.drop(bind, checkfirst=True)
    reward_side_enum.drop(bind, checkfirst=True)
    referral_code_status_enum.drop(bind, checkfirst=True)

    # Drop ULID function and extension
    op.execute("DROP FUNCTION IF EXISTS generate_ulid()")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")

    # Drop search tables if they exist
    # Using execute to handle if table doesn't exist
    op.execute("DROP TABLE IF EXISTS search_event_candidates CASCADE")
    op.execute("DROP TABLE IF EXISTS search_interactions CASCADE")
    op.execute("DROP TABLE IF EXISTS search_events CASCADE")
    op.execute("DROP TABLE IF EXISTS search_history CASCADE")

    # Drop RBAC tables
    op.execute("DROP TABLE IF EXISTS user_permissions CASCADE")
    op.execute("DROP TABLE IF EXISTS role_permissions CASCADE")
    op.execute("DROP TABLE IF EXISTS user_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS permissions CASCADE")
    op.execute("DROP TABLE IF EXISTS roles CASCADE")

    # Drop check constraints first
    op.drop_constraint("ck_users_account_status", "users", type_="check")

    # Drop indexes first
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_totp_enabled", table_name="users")

    # Drop tables
    op.drop_table("users")

    # No enum type to drop anymore

    print("Initial schema dropped successfully!")
