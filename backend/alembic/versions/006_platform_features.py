# backend/alembic/versions/006_platform_features.py
"""Platform features - favorites, addresses, referrals, beta, alerts, jobs

Revision ID: 006_platform_features
Revises: 005_search
Create Date: 2025-02-10 00:00:05.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "006_platform_features"
down_revision: Union[str, None] = "005_search"
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
        WHERE c.relkind = 'r'
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


def upgrade() -> None:
    """Create platform feature tables and performance indexes."""
    print("Creating platform feature tables...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"
    json_type = JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    # Badge definitions
    op.create_table(
        "badge_definitions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("criteria_type", sa.String(50), nullable=True),
        sa.Column("criteria_config", postgresql.JSONB(), nullable=True),
        sa.Column("icon_key", sa.String(100), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_badge_definitions_slug"),
        comment="Catalog of badge definition metadata",
    )

    op.create_table(
        "student_badges",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("badge_id", sa.String(26), nullable=False),
        sa.Column(
            "awarded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("progress_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("hold_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["badge_id"],
            ["badge_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "badge_id", name="uq_student_badges_student_badge"),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','revoked')",
            name="ck_student_badges_status",
        ),
        comment="Badge instances awarded to students",
    )
    op.create_index("idx_student_badges_student_id", "student_badges", ["student_id"])
    op.create_index("idx_student_badges_badge_id", "student_badges", ["badge_id"])
    op.create_index(
        "idx_student_badges_status_hold_until",
        "student_badges",
        ["status", "hold_until"],
    )

    op.create_table(
        "badge_progress",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("badge_id", sa.String(26), nullable=False),
        sa.Column("current_progress", postgresql.JSONB(), nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["badge_id"],
            ["badge_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "badge_id", name="uq_badge_progress_student_badge"),
        comment="Progress snapshots toward earning badges",
    )
    op.create_index("idx_badge_progress_student_id", "badge_progress", ["student_id"])
    op.create_index("idx_badge_progress_badge_id", "badge_progress", ["badge_id"])

    # Favorites
    op.create_table(
        "user_favorites",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("student_id", sa.String(26), nullable=False),
        sa.Column("instructor_id", sa.String(26), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "instructor_id", name="unique_student_instructor_favorite"),
        comment="Students can favorite instructors",
    )
    op.create_index("idx_favorites_student", "user_favorites", ["student_id"])
    op.create_index("idx_favorites_instructor", "user_favorites", ["instructor_id"])

    # Addresses and spatial data
    class Geometry(sa.types.UserDefinedType):
        def __init__(self, geom_type: str = "POINT", srid: int = 4326):
            self.geom_type = geom_type
            self.srid = srid

        def get_col_spec(self, **kw):  # type: ignore[override]
            return f"GEOMETRY({self.geom_type}, {self.srid})"

    op.create_table(
        "user_addresses",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(20), nullable=True),
        sa.Column("custom_label", sa.String(50), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recipient_name", sa.String(100), nullable=True),
        sa.Column("street_line1", sa.String(255), nullable=False),
        sa.Column("street_line2", sa.String(255), nullable=True),
        sa.Column("locality", sa.String(100), nullable=False),
        sa.Column("administrative_area", sa.String(100), nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="US"),
        sa.Column("latitude", sa.Numeric(10, 8), nullable=True),
        sa.Column("longitude", sa.Numeric(11, 8), nullable=True),
        sa.Column("place_id", sa.String(255), nullable=True),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("normalized_payload", sa.JSON(), nullable=True),
        sa.Column("location", Geometry("POINT", 4326), nullable=True),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("neighborhood", sa.String(100), nullable=True),
        sa.Column("subneighborhood", sa.String(100), nullable=True),
        sa.Column("location_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_user_addresses_user_active", "user_addresses", ["user_id", "is_active"])
    if is_postgres:
        op.create_index(
            "ix_user_addresses_location",
            "user_addresses",
            ["location"],
            postgresql_using="gist",
        )
        op.create_index(
            "uq_user_default_address",
            "user_addresses",
            ["user_id"],
            unique=True,
            postgresql_where=sa.text("is_default = true"),
        )
    op.create_index("ix_user_addresses_postal_code", "user_addresses", ["postal_code"])
    op.create_check_constraint(
        "ck_user_addresses_label_values",
        "user_addresses",
        "label IS NULL OR label IN ('home','work','other')",
    )
    op.create_check_constraint(
        "ck_user_addresses_other_label_has_custom",
        "user_addresses",
        "label != 'other' OR custom_label IS NOT NULL",
    )

    # Referral program
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
            postgresql.ENUM(
                "active",
                "disabled",
                name="referral_code_status",
                create_type=False,
                validate_strings=True,
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
    op.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_codes_user_active "
            "ON referral_codes(referrer_user_id) WHERE status = 'active';"
        )
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
            postgresql.ENUM(
                "student",
                "instructor",
                name="reward_side",
                create_type=False,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "unlocked",
                "redeemed",
                "void",
                name="reward_status",
                create_type=False,
                validate_strings=True,
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
            postgresql.ENUM(
                "referral_credit",
                "fee_rebate",
                name="wallet_txn_type",
                create_type=False,
                validate_strings=True,
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

    op.create_table(
        "referral_config",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, unique=True),
        sa.Column(
            "effective_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("student_amount_cents", sa.Integer(), nullable=False),
        sa.Column("instructor_amount_cents", sa.Integer(), nullable=False),
        sa.Column("instructor_founding_bonus_cents", sa.Integer(), nullable=False),
        sa.Column("instructor_standard_bonus_cents", sa.Integer(), nullable=False),
        sa.Column("min_basket_cents", sa.Integer(), nullable=False),
        sa.Column("hold_days", sa.Integer(), nullable=False),
        sa.Column("expiry_months", sa.Integer(), nullable=False),
        sa.Column("student_global_cap", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("student_amount_cents >= 0"),
        sa.CheckConstraint("instructor_amount_cents >= 0"),
        sa.CheckConstraint("instructor_founding_bonus_cents >= 0"),
        sa.CheckConstraint("instructor_standard_bonus_cents >= 0"),
        sa.CheckConstraint("min_basket_cents >= 6000"),
        sa.CheckConstraint("hold_days BETWEEN 1 AND 14"),
        sa.CheckConstraint("expiry_months BETWEEN 1 AND 24"),
        sa.CheckConstraint("student_global_cap >= 0"),
    )
    op.create_index(
        "ix_referral_config_effective_at_desc",
        "referral_config",
        ["effective_at"],
        unique=False,
    )

    op.create_table(
        "instructor_referral_payouts",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column(
            "referrer_user_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_instructor_id",
            sa.String(26),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "triggering_booking_id",
            sa.String(26),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("was_founding_bonus", sa.Boolean(), nullable=False),
        sa.Column("stripe_transfer_id", sa.String(255), nullable=True),
        sa.Column(
            "stripe_transfer_status",
            sa.String(50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("transferred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        comment="Cash payouts for instructor referrals via Stripe transfers",
    )
    op.create_index(
        "ix_instructor_referral_payouts_referrer",
        "instructor_referral_payouts",
        ["referrer_user_id"],
    )
    op.create_index(
        "ix_instructor_referral_payouts_referred",
        "instructor_referral_payouts",
        ["referred_instructor_id"],
    )
    op.create_index(
        "ix_instructor_referral_payouts_unique_referred",
        "instructor_referral_payouts",
        ["referred_instructor_id"],
        unique=True,
    )

    # Platform credits
    op.create_table(
        "platform_credits",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="legacy"),
        sa.Column("source_booking_id", sa.String(26), nullable=True),
        sa.Column("used_booking_id", sa.String(26), nullable=True),
        sa.Column("reserved_amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_for_booking_id", sa.String(26), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forfeited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(500), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_reason", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["used_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reserved_for_booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_cents >= 0", name="ck_platform_credits_amount_positive"),
        sa.CheckConstraint("reserved_amount_cents >= 0", name="ck_platform_credits_reserved_positive"),
        comment="Credits issued from cancellations, usable on future bookings",
    )
    op.create_index("idx_platform_credits_user_id", "platform_credits", ["user_id"])
    op.create_index("idx_platform_credits_source_booking_id", "platform_credits", ["source_booking_id"])
    op.create_index("idx_platform_credits_used_booking_id", "platform_credits", ["used_booking_id"])
    op.create_index(
        "idx_platform_credits_reserved_booking_id",
        "platform_credits",
        ["reserved_for_booking_id"],
    )
    op.create_index("idx_platform_credits_status", "platform_credits", ["status"])
    op.create_index("idx_platform_credits_expires_at", "platform_credits", ["expires_at"])
    op.create_index(
        "idx_platform_credits_unused",
        "platform_credits",
        ["user_id", "expires_at"],
        postgresql_where=sa.text("status = 'available'"),
    )

    # Beta program tables
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="instructor_beta"),
        sa.Column("grant_founding_status", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_beta_invites_code"),
    )
    op.create_index("ix_beta_invites_code", "beta_invites", ["code"])
    op.create_index("ix_beta_invites_email", "beta_invites", ["email"])

    op.create_table(
        "beta_access",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column(
            "invited_by_code", sa.String(16), sa.ForeignKey("beta_invites.code", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False, server_default="instructor_only"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "role", "phase", name="uq_beta_access_user_role_phase"),
    )
    op.create_index("ix_beta_access_user", "beta_access", ["user_id"])

    op.create_table(
        "beta_settings",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("beta_disabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("beta_phase", sa.String(32), nullable=False, server_default="instructor_only"),
        sa.Column("allow_signup_without_invite", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Alert history
    op.create_table(
        "alert_history",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("email_sent", sa.Boolean(), nullable=False, default=False),
        sa.Column("github_issue_created", sa.Boolean(), nullable=False, default=False),
        sa.Column("github_issue_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_history_created_at", "alert_history", ["created_at"])
    op.create_index("ix_alert_history_alert_type", "alert_history", ["alert_type"])
    op.create_index("ix_alert_history_severity", "alert_history", ["severity"])

    # Webhook ledger
    webhook_status_default = sa.text("'received'")
    replay_count_default = sa.text("0")
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=True),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("headers", json_type, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=webhook_status_default),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("processing_duration_ms", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("related_entity_type", sa.String(50), nullable=True),
        sa.Column("related_entity_id", sa.String(26), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_of", sa.String(26), nullable=True),
        sa.Column("replay_count", sa.Integer(), nullable=False, server_default=replay_count_default),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "event_id", name="uq_webhook_events_source_event_id"),
    )
    op.create_index("ix_webhook_events_source", "webhook_events", ["source"])
    op.create_index("ix_webhook_events_event_type", "webhook_events", ["event_type"])
    op.create_index("ix_webhook_events_status", "webhook_events", ["status"])
    op.create_index("ix_webhook_events_received_at", "webhook_events", ["received_at"])
    op.create_index("ix_webhook_events_event_id", "webhook_events", ["event_id"])
    op.create_index(
        "ix_webhook_events_related_entity",
        "webhook_events",
        ["related_entity_type", "related_entity_id"],
    )

    # Notification outbox
    event_outbox_payload_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")
    notification_payload_default = sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")

    op.create_table(
        "event_outbox",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", json_type, nullable=False, server_default=event_outbox_payload_default),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_event_outbox_idempotency_key"),
    )
    op.create_index("ix_event_outbox_event_type", "event_outbox", ["event_type"])
    op.create_index("ix_event_outbox_status_next_attempt", "event_outbox", ["status", "next_attempt_at"])

    op.create_table(
        "notification_delivery",
        sa.Column("id", sa.String(length=26), primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", json_type, nullable=False, server_default=notification_payload_default),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_delivery_idempotency"),
    )
    op.create_index(
        "ix_notification_delivery_event_type_delivered_at",
        "notification_delivery",
        ["event_type", "delivered_at"],
    )

    # Notification preferences + inbox + push subscriptions
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "category",
            "channel",
            name="uq_notification_preferences_user_category_channel",
        ),
        sa.CheckConstraint(
            "category IN ('lesson_updates', 'messages', 'reviews', 'learning_tips', 'system_updates', 'promotional')",
            name="ck_notification_preferences_category",
        ),
        sa.CheckConstraint(
            "channel IN ('email', 'push', 'sms')",
            name="ck_notification_preferences_channel",
        ),
    )
    op.create_index(
        "ix_notification_preferences_user_id",
        "notification_preferences",
        ["user_id"],
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("data", json_type, nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "category IN ('lesson_updates', 'messages', 'reviews', 'learning_tips', 'system_updates', 'promotional')",
            name="ck_notifications_category",
        ),
    )
    op.create_index(
        "ix_notifications_user_read_at",
        "notifications",
        ["user_id", "read_at"],
    )
    op.create_index(
        "ix_notifications_user_created_at",
        "notifications",
        ["user_id", "created_at"],
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "ix_notifications_user_category",
        "notifications",
        ["user_id", "category"],
    )
    op.create_index(
        "ix_notifications_deleted_at",
        "notifications",
        ["deleted_at"],
    )
    op.create_index(
        "ix_notifications_type",
        "notifications",
        ["type"],
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.String(26), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh_key", sa.String(255), nullable=False),
        sa.Column("auth_key", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_user_endpoint"),
    )
    op.create_index(
        "ix_push_subscriptions_user_id",
        "push_subscriptions",
        ["user_id"],
    )

    # Background jobs
    payload_type = json_type
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_background_jobs_status_available",
        "background_jobs",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_background_jobs_type_status",
        "background_jobs",
        ["type", "status"],
    )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_background_jobs_pending "
            "ON background_jobs (status, available_at) WHERE status = 'pending'"
        )

    op.add_column(
        "bookings",
        sa.Column(
            "reminder_24h_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "reminder_1h_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "phone_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Performance indexes (from 005_performance_indexes)
    op.create_index(
        "idx_bookings_date_status",
        "bookings",
        ["booking_date", "status"],
    )
    op.create_index(
        "idx_bookings_upcoming",
        "bookings",
        ["booking_date", "status"],
        postgresql_where=sa.text("status = 'CONFIRMED'"),
    )
    op.create_index(
        "idx_bookings_student_date",
        "bookings",
        ["student_id", "booking_date"],
    )
    op.create_index(
        "idx_bookings_student_status",
        "bookings",
        ["student_id", "status", "booking_date"],
    )
    op.create_index(
        "idx_bookings_instructor_status",
        "bookings",
        ["instructor_id", "status", "booking_date"],
    )

    try:
        op.execute(
            """
            CREATE INDEX idx_users_name_gin
            ON users
            USING gin(to_tsvector('english', first_name || ' ' || last_name))
            """
        )
    except Exception:
        op.create_index("idx_users_last_name", "users", ["last_name"])
        op.create_index("idx_users_first_name", "users", ["first_name"])

    try:
        op.execute(
            """
            CREATE INDEX idx_instructor_profiles_bio_gin
            ON instructor_profiles
            USING gin(to_tsvector('english', bio))
            """
        )
    except Exception:
        pass

    op.create_index(
        "idx_service_catalog_name_lower",
        "service_catalog",
        [sa.text("LOWER(name)")],
    )
    op.create_index(
        "idx_instructor_services_active_price",
        "instructor_services",
        ["is_active", "hourly_rate"],
    )
    op.create_index(
        "idx_instructor_services_profile_active",
        "instructor_services",
        ["instructor_profile_id", "is_active"],
    )
    op.create_index(
        "idx_service_catalog_category_active",
        "service_catalog",
        ["category_id", "is_active"],
    )
    op.create_index(
        "idx_instructor_services_catalog_active",
        "instructor_services",
        ["service_catalog_id", "is_active"],
    )
    op.add_column(
        "instructor_services",
        sa.Column("offers_travel", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "instructor_services",
        sa.Column("offers_at_location", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "instructor_services",
        sa.Column("offers_online", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_reviews_booking_id", "reviews", ["booking_id"])
    op.create_index(
        "ix_reviews_instructor_id_created_at",
        "reviews",
        ["instructor_id", "created_at"],
    )

    # Missing indexes from review
    op.create_index("ix_reviews_student_id", "reviews", ["student_id"])
    op.create_index("ix_message_reactions_message_id", "message_reactions", ["message_id"])
    op.create_index("ix_search_clicks_instructor_id", "search_clicks", ["instructor_id"])

    op.create_table(
        "booking_notes",
        sa.Column("id", sa.String(26), nullable=False),
        sa.Column("booking_id", sa.String(26), nullable=False),
        sa.Column("created_by_id", sa.String(26), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False, server_default="internal"),
        sa.Column("category", sa.String(32), nullable=False, server_default="general"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="Admin notes attached to bookings",
    )
    op.create_index("idx_booking_notes_booking_id", "booking_notes", ["booking_id"])
    op.create_index("idx_booking_notes_created_by_id", "booking_notes", ["created_by_id"])
    op.create_index("idx_booking_notes_created_at", "booking_notes", ["created_at"])

    if is_postgres:
        exclude_tables = [
            "alembic_version",
            "spatial_ref_sys",
            "geometry_columns",
            "geography_columns",
        ]
        tables = _get_public_tables(exclude_tables)
        for table_name in tables:
            _enable_rls_with_permissive_policy(table_name)

        # =============================================================================
        # DATABASE ROLES FOR PRODUCTION SAFETY
        # =============================================================================

        # 1. app_user - Application runtime (limited permissions)
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                    CREATE ROLE app_user WITH LOGIN PASSWORD 'PLACEHOLDER_CHANGE_ME';
                END IF;
            END
            $$;

            GRANT USAGE ON SCHEMA public TO app_user;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_user;

            -- NOTE: safeupdate is already preloaded by Supabase globally
            """
        )

        # 2. backup_user - For pg_dump backups (read-only + BYPASSRLS)
        # CRITICAL: BYPASSRLS is required or backups will be silently incomplete when RLS is enabled
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'backup_user') THEN
                    CREATE ROLE backup_user WITH LOGIN PASSWORD 'PLACEHOLDER_CHANGE_ME' BYPASSRLS;
                END IF;
            END
            $$;

            GRANT USAGE ON SCHEMA public TO backup_user;
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO backup_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO backup_user;

            -- Also grant access to auth schema for complete backups
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth') THEN
                    EXECUTE 'GRANT USAGE ON SCHEMA auth TO backup_user';
                    EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA auth TO backup_user';
                END IF;
            END
            $$;
            """
        )

        # 3. readonly_user - For analytics/reporting (read-only, respects RLS)
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_user') THEN
                    CREATE ROLE readonly_user WITH LOGIN PASSWORD 'PLACEHOLDER_CHANGE_ME';
                END IF;
            END
            $$;

            GRANT USAGE ON SCHEMA public TO readonly_user;
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
            """
        )

        # 4. migration_user - For Alembic migrations (full DDL access)
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'migration_user') THEN
                    CREATE ROLE migration_user WITH LOGIN PASSWORD 'PLACEHOLDER_CHANGE_ME' CREATEDB;
                END IF;
            END
            $$;

            GRANT ALL PRIVILEGES ON SCHEMA public TO migration_user;
            GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO migration_user;
            GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO migration_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO migration_user;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO migration_user;
            """
        )

        # 5. Enable pgAudit extension for DDL/write audit logging
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pgaudit') THEN
                    CREATE EXTENSION IF NOT EXISTS pgaudit SCHEMA extensions;
                    ALTER ROLE app_user SET pgaudit.log = 'ddl, write';
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    """Drop platform features and indexes."""
    print("Dropping platform feature tables...")

    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "postgresql"
    is_postgres = dialect_name == "postgresql"

    if is_postgres:
        exclude_tables = [
            "alembic_version",
            "spatial_ref_sys",
            "geometry_columns",
            "geography_columns",
        ]
        tables = _get_public_tables(exclude_tables)
        for table_name in tables:
            _drop_permissive_policy_and_disable_rls(table_name)

    op.drop_index("idx_booking_notes_created_at", table_name="booking_notes")
    op.drop_index("idx_booking_notes_created_by_id", table_name="booking_notes")
    op.drop_index("idx_booking_notes_booking_id", table_name="booking_notes")
    op.drop_table("booking_notes")

    op.drop_column("bookings", "reminder_1h_sent")
    op.drop_column("bookings", "reminder_24h_sent")
    op.drop_column("users", "phone_verified")
    op.drop_column("instructor_services", "offers_online")
    op.drop_column("instructor_services", "offers_at_location")
    op.drop_column("instructor_services", "offers_travel")

    op.drop_index("ix_search_clicks_instructor_id", table_name="search_clicks")
    op.drop_index("ix_message_reactions_message_id", table_name="message_reactions")
    op.drop_index("ix_reviews_student_id", table_name="reviews")

    op.drop_index("ix_reviews_instructor_id_created_at", table_name="reviews")
    op.drop_index("ix_reviews_booking_id", table_name="reviews")
    op.drop_index("idx_instructor_services_catalog_active", table_name="instructor_services")
    op.drop_index("idx_service_catalog_category_active", table_name="service_catalog")
    op.drop_index("idx_instructor_services_profile_active", table_name="instructor_services")
    op.drop_index("idx_instructor_services_active_price", table_name="instructor_services")
    op.drop_index("idx_service_catalog_name_lower", table_name="service_catalog")

    try:
        op.execute("DROP INDEX IF EXISTS idx_instructor_profiles_bio_gin")
    except Exception:
        pass

    try:
        op.execute("DROP INDEX IF EXISTS idx_users_name_gin")
    except Exception:
        try:
            op.drop_index("idx_users_last_name", table_name="users")
            op.drop_index("idx_users_first_name", table_name="users")
        except Exception:
            pass

    op.drop_index("idx_bookings_instructor_status", table_name="bookings")
    op.drop_index("idx_bookings_student_status", table_name="bookings")
    op.drop_index("idx_bookings_student_date", table_name="bookings")
    op.drop_index("idx_bookings_upcoming", table_name="bookings")
    op.drop_index("idx_bookings_date_status", table_name="bookings")

    op.drop_index("ix_background_jobs_type_status", table_name="background_jobs")
    op.drop_index("ix_background_jobs_status_available", table_name="background_jobs")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_background_jobs_pending")
    op.drop_table("background_jobs")

    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")

    op.drop_index("ix_notifications_user_created_at", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_deleted_at", table_name="notifications")
    op.drop_index("ix_notifications_user_category", table_name="notifications")
    op.drop_index("ix_notifications_user_read_at", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_notification_preferences_user_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")

    op.drop_index("ix_notification_delivery_event_type_delivered_at", table_name="notification_delivery")
    op.drop_table("notification_delivery")

    op.drop_index("ix_event_outbox_status_next_attempt", table_name="event_outbox")
    op.drop_index("ix_event_outbox_event_type", table_name="event_outbox")
    op.drop_table("event_outbox")

    op.drop_index("ix_alert_history_severity", table_name="alert_history")
    op.drop_index("ix_alert_history_alert_type", table_name="alert_history")
    op.drop_index("ix_alert_history_created_at", table_name="alert_history")
    op.drop_table("alert_history")

    op.drop_index("ix_webhook_events_related_entity", table_name="webhook_events")
    op.drop_index("ix_webhook_events_event_id", table_name="webhook_events")
    op.drop_index("ix_webhook_events_received_at", table_name="webhook_events")
    op.drop_index("ix_webhook_events_status", table_name="webhook_events")
    op.drop_index("ix_webhook_events_event_type", table_name="webhook_events")
    op.drop_index("ix_webhook_events_source", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_table("beta_settings")
    op.drop_index("ix_beta_access_user", table_name="beta_access")
    op.drop_constraint("uq_beta_access_user_role_phase", "beta_access", type_="unique")
    op.drop_table("beta_access")
    op.drop_index("ix_beta_invites_email", table_name="beta_invites")
    op.drop_index("ix_beta_invites_code", table_name="beta_invites")
    op.drop_constraint("uq_beta_invites_code", "beta_invites", type_="unique")
    op.drop_table("beta_invites")

    op.drop_index("idx_platform_credits_expires_at", table_name="platform_credits")
    op.drop_index("idx_platform_credits_unused", table_name="platform_credits")
    op.drop_index("idx_platform_credits_status", table_name="platform_credits")
    op.drop_index("idx_platform_credits_reserved_booking_id", table_name="platform_credits")
    op.drop_index("idx_platform_credits_used_booking_id", table_name="platform_credits")
    op.drop_index("idx_platform_credits_source_booking_id", table_name="platform_credits")
    op.drop_index("idx_platform_credits_user_id", table_name="platform_credits")
    op.drop_table("platform_credits")

    op.drop_index(
        "ix_instructor_referral_payouts_unique_referred",
        table_name="instructor_referral_payouts",
    )
    op.drop_index(
        "ix_instructor_referral_payouts_referred",
        table_name="instructor_referral_payouts",
    )
    op.drop_index(
        "ix_instructor_referral_payouts_referrer",
        table_name="instructor_referral_payouts",
    )
    op.drop_table("instructor_referral_payouts")

    op.execute("DROP INDEX IF EXISTS ix_referral_config_effective_at_desc")
    op.execute("DROP TABLE IF EXISTS referral_config CASCADE")
    op.drop_table("referral_limits")

    op.drop_index("idx_wallet_transactions_user_created_at", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")

    op.drop_index("idx_referral_rewards_referred_side", table_name="referral_rewards")
    op.drop_index("idx_referral_rewards_referrer_status", table_name="referral_rewards")
    op.drop_table("referral_rewards")

    op.drop_table("referral_attributions")

    op.drop_index("idx_referral_clicks_code_ts", table_name="referral_clicks")
    op.drop_table("referral_clicks")

    op.execute(text("DROP INDEX IF EXISTS idx_referral_codes_user_active;"))
    op.drop_index("idx_referral_codes_referrer_user_id", table_name="referral_codes")
    op.drop_table("referral_codes")

    op.drop_index("idx_badge_progress_badge_id", table_name="badge_progress")
    op.drop_index("idx_badge_progress_student_id", table_name="badge_progress")
    op.drop_table("badge_progress")

    op.drop_index("idx_student_badges_status_hold_until", table_name="student_badges")
    op.drop_index("idx_student_badges_badge_id", table_name="student_badges")
    op.drop_index("idx_student_badges_student_id", table_name="student_badges")
    op.drop_table("student_badges")

    op.drop_table("badge_definitions")

    op.drop_constraint("ck_user_addresses_other_label_has_custom", "user_addresses", type_="check")
    op.drop_constraint("ck_user_addresses_label_values", "user_addresses", type_="check")
    op.drop_index("ix_user_addresses_postal_code", table_name="user_addresses")
    if is_postgres:
        op.drop_index("uq_user_default_address", table_name="user_addresses")
        op.drop_index("ix_user_addresses_location", table_name="user_addresses")
    op.drop_index("ix_user_addresses_user_active", table_name="user_addresses")
    op.drop_table("user_addresses")

    op.drop_index("idx_favorites_instructor", table_name="user_favorites")
    op.drop_index("idx_favorites_student", table_name="user_favorites")
    op.drop_table("user_favorites")
