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
from pathlib import Path
import sys

# Ensure backend/ is importable when called directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings  # noqa: E402


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
