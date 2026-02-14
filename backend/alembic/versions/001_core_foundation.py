# backend/alembic/versions/001_core_foundation.py
"""Core foundation - extensions, users, roles, permissions, platform config, audit

Revision ID: 001_core_foundation
Revises:
Create Date: 2025-02-10 00:00:00.000000

This migration creates the foundational schema for authentication and
system configuration, including extensions, RBAC tables, and audit logging.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

# Import enums for seed data
try:
    from app.core.enums import RoleName

    ROLE_ADMIN = RoleName.ADMIN.value
    ROLE_INSTRUCTOR = RoleName.INSTRUCTOR.value
    ROLE_STUDENT = RoleName.STUDENT.value
except ImportError:
    ROLE_ADMIN = "admin"
    ROLE_INSTRUCTOR = "instructor"
    ROLE_STUDENT = "student"


# revision identifiers, used by Alembic.
revision: str = "001_core_foundation"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_public_tables(exclude: list[str]) -> list[str]:
    """Return list of public schema base tables excluding given names."""

    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        """
        SELECT c.relname AS table_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' -- ordinary tables
          AND n.nspname = 'public'
          AND c.relname NOT IN (%s)
        ORDER BY c.relname
        """
        % ",".join(["'%s'" % name for name in exclude])
    ).fetchall()
    return [r[0] for r in rows]


def _enable_rls_with_permissive_policy(table_name: str) -> None:
    """Enable RLS and create an app role policy on the given table."""

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = '{table_name}' AND n.nspname = 'public' AND c.relrowsecurity = true
            ) THEN
                EXECUTE 'ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY';
            END IF;
        END$$;
        """
    )

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = '{table_name}' AND policyname = 'app_role_access'
            ) THEN
                EXECUTE 'CREATE POLICY app_role_access ON public.{table_name} FOR ALL USING (current_user IN (''postgres'', ''app_user'')) WITH CHECK (current_user IN (''postgres'', ''app_user''))';
            END IF;
        END$$;
        """
    )


def _drop_permissive_policy_and_disable_rls(table_name: str) -> None:
    """Drop app role policy and disable RLS on the given table (idempotent)."""

    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = '{table_name}' AND policyname = 'app_role_access'
            ) THEN
                EXECUTE 'DROP POLICY app_role_access ON public.{table_name}';
            END IF;
        END$$;
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = '{table_name}' AND n.nspname = 'public' AND c.relrowsecurity = true
            ) THEN
                EXECUTE 'ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY';
            END IF;
        END$$;
        """
    )


def _create_extension_prefer_extensions_schema(extension_name: str) -> None:
    """Create extension using extensions schema when available."""

    bind = op.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return

    op.execute(
        f"""
        DO $$
        DECLARE
            extensions_schema_exists BOOLEAN;
            extension_installed BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM pg_namespace WHERE nspname = 'extensions'
            ) INTO extensions_schema_exists;

            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = '{extension_name}'
            ) INTO extension_installed;

            IF NOT extension_installed THEN
                IF extensions_schema_exists THEN
                    EXECUTE 'CREATE EXTENSION IF NOT EXISTS {extension_name} WITH SCHEMA extensions';
                ELSE
                    EXECUTE 'CREATE EXTENSION IF NOT EXISTS {extension_name}';
                END IF;
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    """Create core foundation schema."""
    print("Creating core foundation schema...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    if is_postgres:
        print("Setting database connection safety parameters...")
        try:
            op.execute("ALTER DATABASE postgres SET idle_in_transaction_session_timeout = '60s'")
        except Exception:
            pass

        print("Checking/Enabling PostGIS extension (if not already enabled)...")
        conn = op.get_bind()
        try:
            res = conn.exec_driver_sql(
                "SELECT 1 FROM pg_available_extensions WHERE name='postgis' AND installed_version IS NOT NULL"
            )
            already_installed = res.first() is not None
        except Exception:
            already_installed = False
        if not already_installed:
            try:
                _create_extension_prefer_extensions_schema("postgis")
                print("PostGIS extension created")
            except Exception as e:
                raise RuntimeError(
                    "PostGIS extension is not installed on this PostgreSQL instance. "
                    "Install PostGIS and re-run migrations. Original error: %s" % str(e)
                )

        print("Ensuring pg_trgm extension...")
        _create_extension_prefer_extensions_schema("pg_trgm")

        print("Ensuring pgvector extension...")
        _create_extension_prefer_extensions_schema("vector")

    print("ULID generation will be handled by Python models...")

    if is_postgres:
        enum_definitions = {
            "referral_code_status": ("active", "disabled"),
            "reward_side": ("student", "instructor"),
            "reward_status": ("pending", "unlocked", "redeemed", "void"),
            "wallet_txn_type": ("referral_credit", "fee_rebate"),
        }

        for enum_name, values in enum_definitions.items():
            value_list = ", ".join(f"'{value}'" for value in values)
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
                        CREATE TYPE {enum_name} AS ENUM ({value_list});
                    END IF;
                END$$;
                """
            )
            for value in values:
                op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}';")

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
        # 2FA fields
        sa.Column("totp_secret", sa.String(255), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("totp_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backup_codes", postgresql.JSONB(), nullable=True),
        sa.Column("two_factor_setup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("two_factor_last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column(
            "account_status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("account_locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("account_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_locked_reason", sa.String(500), nullable=True),
        sa.Column("credit_balance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credit_balance_frozen", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("account_restricted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("account_restricted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_restricted_reason", sa.String(500), nullable=True),
        sa.Column(
            "timezone",
            sa.String(50),
            nullable=False,
            server_default="America/New_York",
        ),
        # Profile picture metadata
        sa.Column("profile_picture_key", sa.String(255), nullable=True),
        sa.Column("profile_picture_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile_picture_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
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
    op.create_index(
        "ix_users_totp_enabled",
        "users",
        ["totp_enabled"],
        unique=False,
    )

    op.create_check_constraint(
        "ck_users_account_status",
        "users",
        "account_status IN ('active', 'suspended', 'deactivated')",
    )

    # Create RBAC tables
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

    op.create_table(
        "permissions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.timezone("UTC", sa.func.now()),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="System permissions for granular access control",
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("role_id", sa.String(26), nullable=False),
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

    op.create_index("idx_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("idx_user_roles_role_id", "user_roles", ["role_id"])

    json_type = JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    print("Creating platform_config table...")
    op.create_table(
        "platform_config",
        sa.Column("key", sa.Text(), primary_key=True, nullable=False),
        sa.Column("value_json", json_type, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    print("Creating audit_log table...")
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("actor_role", sa.String(length=30), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("before", json_type, nullable=True),
        sa.Column("after", json_type, nullable=True),
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_audit_log_entity ON audit_log (entity_type, entity_id);"
        )
        op.execute(
            "CREATE INDEX ix_audit_log_occurred ON audit_log (occurred_at);"
        )
        op.execute(
            "CREATE INDEX ix_audit_log_actor ON audit_log (actor_id, occurred_at DESC);"
        )
        op.execute(
            "CREATE INDEX ix_audit_log_action ON audit_log (action, occurred_at DESC);"
        )
    else:
        op.create_index(
            "ix_audit_log_entity",
            "audit_log",
            ["entity_type", "entity_id"],
        )
        op.create_index(
            "ix_audit_log_occurred",
            "audit_log",
            ["occurred_at"],
        )
        op.create_index(
            "ix_audit_log_actor",
            "audit_log",
            ["actor_id", "occurred_at"],
        )
        op.create_index(
            "ix_audit_log_action",
            "audit_log",
            ["action", "occurred_at"],
        )

    print("Creating audit_logs table...")
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("actor_ip", sa.String(length=45), nullable=True),
        sa.Column("actor_user_agent", sa.String(length=500), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=26), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("changes", json_type, nullable=True),
        sa.Column("metadata", json_type, nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="success",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_actor_email", "audit_logs", ["actor_email"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])

    # Password reset tokens
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Password reset token management",
    )

    op.create_index("ix_password_reset_tokens_token", "password_reset_tokens", ["token"], unique=True)
    op.create_index("idx_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    """Drop core foundation schema."""
    print("Dropping core foundation schema...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    op.drop_index("idx_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_audit_log_entity;")
        op.execute("DROP INDEX IF EXISTS ix_audit_log_occurred;")
        op.execute("DROP INDEX IF EXISTS ix_audit_log_actor;")
        op.execute("DROP INDEX IF EXISTS ix_audit_log_action;")
        op.execute("DROP TABLE IF EXISTS audit_log;")
    else:
        op.drop_index("ix_audit_log_action", table_name="audit_log")
        op.drop_index("ix_audit_log_actor", table_name="audit_log")
        op.drop_index("ix_audit_log_occurred", table_name="audit_log")
        op.drop_index("ix_audit_log_entity", table_name="audit_log")
        op.drop_table("audit_log")

    op.drop_index("ix_audit_logs_request_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_resource", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_email", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_timestamp", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_table("platform_config")

    op.drop_index("idx_user_roles_role_id", table_name="user_roles")
    op.drop_index("idx_user_roles_user_id", table_name="user_roles")

    op.drop_table("user_permissions")
    op.drop_table("role_permissions")
    op.drop_table("user_roles")
    op.drop_table("permissions")
    op.drop_table("roles")

    op.drop_index("ix_users_totp_enabled", table_name="users")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    if is_postgres:
        for enum_name in ["referral_code_status", "reward_side", "reward_status", "wallet_txn_type"]:
            op.execute(f"DROP TYPE IF EXISTS {enum_name}")
        op.execute("DROP EXTENSION IF EXISTS vector")
        op.execute("DROP EXTENSION IF EXISTS pg_trgm")
        op.execute("DROP EXTENSION IF EXISTS postgis")
