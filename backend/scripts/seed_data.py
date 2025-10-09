#!/usr/bin/env python3
"""
Unified seeding CLI for Preview and Production databases.

Usage examples:

  # Preview database (full mock data)
  SITE_MODE=preview python scripts/seed_data.py --include-mock-users

  # Production database (system/reference data only)
  SITE_MODE=prod python scripts/seed_data.py --system-only

Notes:
- Always seeds system/reference data (roles, service catalog, regions)
- Only seeds mock users/instructors/bookings/availability when --include-mock-users is passed
- Idempotent where possible; roles and catalog use upsert/skip patterns
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Tuple

# Ensure backend/ is importable when called directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth import get_password_hash  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.enums import RoleName  # noqa: E402
from app.models.rbac import Role  # noqa: E402
from app.models.user import User  # noqa: E402

DEFAULT_ADMIN_PASSWORD = "Test1234!"
DEFAULT_ADMIN_ZIP = "10001"


def _get_admin_seed_credentials() -> Tuple[str, str, str]:
    site_mode = (settings.site_mode or "").strip().lower()
    email = (settings.admin_email or "admin@instainstru.com").strip().lower()
    name = settings.admin_name or "Instainstru Admin"
    password = settings.admin_password or ""
    if site_mode == "prod" and not password:
        raise RuntimeError("ADMIN_PASSWORD is required when seeding in production")
    if not password:
        password = DEFAULT_ADMIN_PASSWORD
    return email, password, name


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [p for p in (full_name or '').strip().split() if p]
    if not parts:
        return "Admin", "User"
    if len(parts) == 1:
        return parts[0], "Admin"
    return parts[0], " ".join(parts[1:])


def seed_admin_user(
    session: Session,
    *,
    email: str,
    password_plain: str,
    name: str | None,
    now: datetime,
    verbose: bool = True,
) -> None:
    """Create or refresh the baseline admin/superuser account."""

    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise ValueError("ADMIN_EMAIL must be provided for admin seeding")

    first_name, last_name = _split_name(name or "")
    hashed_password = get_password_hash(password_plain)

    admin_role = session.execute(select(Role).where(Role.name == RoleName.ADMIN.value)).scalar_one_or_none()
    if admin_role is None:
        if verbose:
            print("⚠️  Admin role not found; skipping admin user seed")
        return

    user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    created = False
    if user is None:
        user = User(
            email=normalized_email,
            hashed_password=hashed_password,
            first_name=first_name,
            last_name=last_name,
            zip_code=DEFAULT_ADMIN_ZIP,
            is_active=True,
            account_status="active",
        )
        session.add(user)
        created = True
    else:
        if user.first_name != first_name:
            user.first_name = first_name
        if user.last_name != last_name:
            user.last_name = last_name
        if not user.is_active:
            user.is_active = True
        if user.account_status != "active":
            user.account_status = "active"
        user.hashed_password = hashed_password

    # Ensure admin role assignment
    if admin_role not in user.roles:
        user.roles.append(admin_role)

    session.commit()
    if verbose:
        action = "Created" if created else "Updated"
        print(f"✅ {action} baseline admin user '{normalized_email}' at {now.isoformat()}")


def _print_banner():
    import os

    from app.core.database_config import DatabaseConfig  # lazy import to avoid heavy init early

    cfg = DatabaseConfig()
    url = cfg.get_database_url()

    # Resolve environment selection from SITE_MODE or detection
    env_sel = (os.getenv("SITE_MODE") or "").strip().lower()
    if not env_sel:
        try:
            env_sel = cfg._detect_environment()  # best-effort; private but stable
        except Exception:
            env_sel = "int"

    print("\n" + "=" * 60)
    print("Seeding database")
    print("=" * 60)
    print(f"Target URL: {cfg._mask_url(url)}")
    print(f"Environment: {env_sel}")
    print("=" * 60 + "\n")


def seed_system_data(verbose: bool = True) -> None:
    """Seed system/reference data: roles/permissions, service catalog, regions."""
    if verbose:
        print("\n▶ Seeding roles and permissions…")
    from seed_roles_permissions import seed_roles_and_permissions  # noqa: E402

    seed_roles_and_permissions()

    if verbose:
        print("\n▶ Seeding service catalog (categories + services)…")
    from seed_catalog_only import seed_catalog  # noqa: E402

    # Use the resolved database URL so the seeder prints clearly
    seed_catalog(db_url=settings.get_database_url(), verbose=verbose)

    if verbose:
        print("\n▶ Loading region boundaries (NYC)…")
    from load_region_boundaries import load_city  # noqa: E402

    try:
        load_city("nyc")
    except Exception as e:
        print(f"  ⚠ Skipping region boundaries load: {e}")

    # Seed baseline admin account
    admin_email, admin_password, admin_name = _get_admin_seed_credentials()

    engine = create_engine(settings.get_database_url())
    with Session(engine) as session:
        seed_admin_user(
            session,
            email=admin_email,
            password_plain=admin_password,
            name=admin_name,
            now=datetime.now(timezone.utc),
            verbose=verbose,
        )


def seed_mock_data(verbose: bool = True) -> None:
    """Seed mock users, instructors, availability, bookings, reviews."""
    from reset_and_seed_yaml import DatabaseSeeder  # noqa: E402

    seeder = DatabaseSeeder()

    # Clean previous mock/test data (users with @example.com, seeded catalog, etc.)
    # This keeps the database schema intact and avoids dropping real data in prod.
    if verbose:
        print("\n▶ Cleaning previous mock data (idempotent)…")
    seeder.reset_database()

    # After cleaning, we must re-seed catalog for mapping instructor services
    if verbose:
        print("\n▶ Reseeding service catalog required for mock instructors…")
    from seed_catalog_only import seed_catalog  # noqa: E402

    seed_catalog(db_url=settings.get_database_url(), verbose=verbose)

    if verbose:
        print("\n▶ Creating mock users and instructors…")
    seeder.create_students()
    seeder.create_instructors()

    if verbose:
        print("\n▶ Creating availability and coverage areas…")
    seeder.create_availability()
    seeder.create_coverage_areas()

    if verbose:
        print("\n▶ Creating bookings and reviews…")
    seeder.create_bookings()
    seeder.create_sample_platform_credits()
    seeder.create_reviews()
    seeder.print_summary()

    engine = create_engine(settings.get_database_url())
    admin_email, admin_password, admin_name = _get_admin_seed_credentials()
    with Session(engine) as session:
        seed_admin_user(
            session,
            email=admin_email,
            password_plain=admin_password,
            name=admin_name,
            now=datetime.now(timezone.utc),
            verbose=verbose,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed database with system and optional mock data")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--system-only", action="store_true", help="Seed only system/reference data")
    group.add_argument("--include-mock-users", action="store_true", help="Seed mock users/instructors/bookings")
    parser.add_argument("--quiet", "-q", action="store_true", help="Reduce output verbosity")
    args = parser.parse_args()

    _print_banner()
    verbose = not args.quiet

    # Always seed system/reference data first
    seed_system_data(verbose=verbose)

    # Only seed mock data if requested
    if args.include_mock_users:
        seed_mock_data(verbose=verbose)
    else:
        if verbose:
            print("\nℹ️  Skipping mock users/instructors/bookings (use --include-mock-users to add them)")

    print("\n✅ Seeding complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
