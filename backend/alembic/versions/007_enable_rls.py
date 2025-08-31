# backend/alembic/versions/007_enable_rls.py
"""Enable Row Level Security (RLS) idempotently on application tables.

Revision ID: 007_enable_rls
Revises: 006_final_constraints
Create Date: 2025-08-30 00:00:01.000000

This migration enables RLS on all public application tables and creates a
permissive default policy (USING true, WITH CHECK true) so behavior does not
change for the application. This makes RLS state deterministic across
environments while remaining no-op functionally until stricter policies are
introduced in future migrations.

Notes:
- Excludes system/extension tables such as alembic_version, spatial_ref_sys,
  geometry_columns, geography_columns.
- Idempotent: checks existence before enabling or creating/dropping policies.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_enable_rls"
down_revision: Union[str, None] = "006_final_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_public_tables(exclude: list[str]) -> list[str]:
    """Return list of public schema base tables excluding given names.

    Excludes views and system tables. Uses pg_catalog for reliability.
    """
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
    """Enable RLS and create a permissive policy on the given table.

    Creates policy name 'all_access' FOR ALL TO PUBLIC USING (true) WITH CHECK (true).
    """
    # Enable RLS if not already enabled
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

    # Create permissive policy if not exists
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = '{table_name}' AND policyname = 'all_access'
            ) THEN
                EXECUTE 'CREATE POLICY all_access ON public.{table_name} FOR ALL TO PUBLIC USING (true) WITH CHECK (true)';
            END IF;
        END$$;
        """
    )


def _drop_permissive_policy_and_disable_rls(table_name: str) -> None:
    """Drop permissive policy and disable RLS on the given table (idempotent)."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public' AND tablename = '{table_name}' AND policyname = 'all_access'
            ) THEN
                EXECUTE 'DROP POLICY all_access ON public.{table_name}';
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
    """Enable RLS and add permissive policies on public application tables."""
    print("Enabling RLS (idempotent) with permissive policies on application tables...")
    # Skip list: alembic and PostGIS/system tables
    exclude_tables = [
        "alembic_version",
        "spatial_ref_sys",
        "geometry_columns",
        "geography_columns",
    ]
    tables = _get_public_tables(exclude_tables)
    for t in tables:
        _enable_rls_with_permissive_policy(t)
    print(f"RLS ensured on {len(tables)} tables (permissive policies created if missing)")


def downgrade() -> None:
    """Remove permissive policies and disable RLS on public application tables."""
    print("Disabling RLS and removing permissive policies (idempotent)...")
    exclude_tables = [
        "alembic_version",
        "spatial_ref_sys",
        "geometry_columns",
        "geography_columns",
    ]
    tables = _get_public_tables(exclude_tables)
    for t in tables:
        _drop_permissive_policy_and_disable_rls(t)
    print(f"RLS disabled on {len(tables)} tables (policies dropped if existed)")
