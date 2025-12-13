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
import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import random
import re
import sys
from typing import TYPE_CHECKING, Tuple
import uuid

# Ensure backend/ is importable when called directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth import get_password_hash  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.enums import RoleName  # noqa: E402
from app.core.ulid_helper import generate_ulid  # noqa: E402

if TYPE_CHECKING:
    from reset_and_seed_yaml import DatabaseSeeder  # noqa: E402
from app.models.beta import BetaAccess  # noqa: E402
from app.models.rbac import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.beta_repository import (  # noqa: E402
    BetaAccessRepository,
    BetaSettingsRepository,
)

DEFAULT_ADMIN_PASSWORD = "Test1234!"
DEFAULT_ADMIN_ZIP = "10001"


# NYC neighborhood aliases for NL search parsing
# These map common shorthand/alternate names to canonical region names
NYC_NEIGHBORHOOD_ALIASES: dict[str, list[str]] = {
    # Manhattan
    "West Village": ["west village", "w village", "wv"],
    "East Village": ["east village", "ev", "e village"],
    "Greenwich Village": ["greenwich village", "the village", "greenwich"],
    "Upper West Side": ["uws", "upper west"],
    "Upper East Side": ["ues", "upper east"],
    "Midtown": ["midtown manhattan", "midtown nyc"],
    "SoHo": ["soho"],
    "TriBeCa": ["tribeca", "tri-beca"],
    "Harlem": ["harlem"],
    "Chelsea": ["chelsea"],
    "Financial District": ["fidi", "wall street", "financial district"],
    "Chinatown": ["chinatown"],
    "Little Italy": ["little italy"],
    "Lower East Side": ["les", "lower east side"],
    "NoHo": ["noho"],
    "Flatiron": ["flatiron", "flatiron district"],
    "Gramercy": ["gramercy", "gramercy park"],
    "Murray Hill": ["murray hill"],
    "Hell's Kitchen": ["hells kitchen", "hell's kitchen", "clinton"],
    "Washington Heights": ["washington heights", "wash heights"],
    "Inwood": ["inwood"],
    # Brooklyn
    "Williamsburg": ["wburg", "billyburg", "williamsburg"],
    "Park Slope": ["park slope", "the slope", "parkslope"],
    "Brooklyn Heights": ["brooklyn heights", "bk heights"],
    "DUMBO": ["dumbo"],
    "Bushwick": ["bushwick"],
    "Greenpoint": ["greenpoint"],
    "Bedford-Stuyvesant": ["bed stuy", "bed-stuy", "bedstuy"],
    "Crown Heights": ["crown heights"],
    "Prospect Heights": ["prospect heights"],
    "Fort Greene": ["fort greene"],
    "Cobble Hill": ["cobble hill"],
    "Carroll Gardens": ["carroll gardens"],
    "Red Hook": ["red hook"],
    "Sunset Park": ["sunset park"],
    "Bay Ridge": ["bay ridge"],
    # Queens
    "Astoria": ["astoria"],
    "Long Island City": ["long island city", "lic"],
    "Flushing": ["flushing"],
    "Jackson Heights": ["jackson heights"],
    "Forest Hills": ["forest hills"],
    "Sunnyside": ["sunnyside"],
    "Woodside": ["woodside"],
    "Bayside": ["bayside"],
    # Bronx
    "Riverdale": ["riverdale"],
    "Fordham": ["fordham"],
    "Mott Haven": ["mott haven"],
}

# Borough aliases (used in migration, kept here for reference)
NYC_BOROUGH_ALIASES: dict[str, list[str]] = {
    "Manhattan": ["nyc", "new york", "the city"],
    "Brooklyn": ["bk", "bklyn", "kings county"],
    "Queens": ["qns"],
    "Bronx": ["the bronx", "bx"],
    "Staten Island": ["si", "richmond county", "staten"],
}


def sync_search_locations_from_regions(
    engine: "sa.Engine", verbose: bool = True, region_code: str = "nyc"
) -> int:
    """
    Sync search_locations table from region_boundaries for a specific region.

    This ensures the NL search parser has access to all neighborhoods
    that exist in region_boundaries (used for instructor service areas).

    Args:
        engine: SQLAlchemy engine
        verbose: Whether to print progress messages
        region_code: Region code to sync (default: nyc)

    Returns the number of locations synced.
    """
    synced = 0

    with Session(engine) as session:
        # Get all neighborhoods from region_boundaries
        result = session.execute(
            text("""
                SELECT
                    rb.region_name,
                    rb.parent_region,
                    ST_Y(ST_Centroid(rb.boundary)) as lat,
                    ST_X(ST_Centroid(rb.boundary)) as lng
                FROM region_boundaries rb
                WHERE rb.region_type = :region_code
                  AND rb.parent_region IS NOT NULL
            """),
            {"region_code": region_code},
        )
        neighborhoods = result.fetchall()

        if verbose:
            print(f"  Found {len(neighborhoods)} neighborhoods in region_boundaries")

        for row in neighborhoods:
            region_name = row[0]
            parent_region = row[1]
            lat = row[2] or 40.7128  # Default to NYC center if null
            lng = row[3] or -74.0060

            # Look up aliases from our dictionary
            # Try exact match first, then try normalized match
            aliases = NYC_NEIGHBORHOOD_ALIASES.get(region_name)
            if aliases is None:
                # Try to find by partial match (e.g., "Astoria (Central)" -> "Astoria")
                for key in NYC_NEIGHBORHOOD_ALIASES:
                    if key.lower() in region_name.lower() or region_name.lower() in key.lower():
                        aliases = NYC_NEIGHBORHOOD_ALIASES[key]
                        break

            # If still no aliases, create a basic one from the name
            if aliases is None:
                aliases = [region_name.lower()]

            # Generate a stable ID from the name
            location_id = f"loc_{region_code}_{region_name.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')[:30]}"

            try:
                session.execute(
                    text("""
                        INSERT INTO search_locations (id, region_code, country_code, name, type, parent_name, borough, aliases, lat, lng, is_active)
                        VALUES (:id, :region_code, :country_code, :name, :type, :parent_name, :borough, :aliases, :lat, :lng, true)
                        ON CONFLICT (id) DO UPDATE SET
                            aliases = EXCLUDED.aliases,
                            parent_name = EXCLUDED.parent_name,
                            lat = EXCLUDED.lat,
                            lng = EXCLUDED.lng
                    """),
                    {
                        "id": location_id,
                        "region_code": region_code,
                        "country_code": "us",
                        "name": region_name,
                        "type": "neighborhood",
                        "parent_name": parent_region,
                        "borough": parent_region,  # Keep for backward compat
                        "aliases": aliases,
                        "lat": lat,
                        "lng": lng,
                    },
                )
                synced += 1
            except Exception as e:
                if verbose:
                    print(f"    ⚠ Could not sync {region_name}: {e}")

        session.commit()

    if verbose:
        print(f"  ✓ Synced {synced} neighborhoods to search_locations ({region_code})")

    return synced


# Backward compatibility alias
sync_nyc_locations_from_regions = sync_search_locations_from_regions


def seed_region_settings(engine: "sa.Engine", verbose: bool = True) -> int:
    """
    Seed the region_settings table with initial region configurations.

    Returns the number of regions seeded.
    """
    import ulid

    regions = [
        {
            "id": f"region_{str(ulid.ULID())[:20]}",
            "region_code": "nyc",
            "region_name": "New York City",
            "country_code": "us",
            "timezone": "America/New_York",
            "price_floor_in_person": 50,
            "price_floor_remote": 40,
            "currency_code": "USD",
            "student_fee_percent": 12.0,
            "is_active": True,
            "launch_date": None,
        },
        # Future regions (inactive for now)
        {
            "id": f"region_{str(ulid.ULID())[:20]}",
            "region_code": "chicago",
            "region_name": "Chicago",
            "country_code": "us",
            "timezone": "America/Chicago",
            "price_floor_in_person": 45,
            "price_floor_remote": 35,
            "currency_code": "USD",
            "student_fee_percent": 12.0,
            "is_active": False,
            "launch_date": None,
        },
        {
            "id": f"region_{str(ulid.ULID())[:20]}",
            "region_code": "la",
            "region_name": "Los Angeles",
            "country_code": "us",
            "timezone": "America/Los_Angeles",
            "price_floor_in_person": 55,
            "price_floor_remote": 45,
            "currency_code": "USD",
            "student_fee_percent": 12.0,
            "is_active": False,
            "launch_date": None,
        },
    ]

    seeded = 0
    with Session(engine) as session:
        for region in regions:
            try:
                session.execute(
                    text("""
                        INSERT INTO region_settings (
                            id, region_code, region_name, country_code, timezone,
                            price_floor_in_person, price_floor_remote, currency_code,
                            student_fee_percent, is_active, launch_date
                        )
                        VALUES (
                            :id, :region_code, :region_name, :country_code, :timezone,
                            :price_floor_in_person, :price_floor_remote, :currency_code,
                            :student_fee_percent, :is_active, :launch_date
                        )
                        ON CONFLICT (region_code) DO UPDATE SET
                            region_name = EXCLUDED.region_name,
                            timezone = EXCLUDED.timezone,
                            price_floor_in_person = EXCLUDED.price_floor_in_person,
                            price_floor_remote = EXCLUDED.price_floor_remote,
                            student_fee_percent = EXCLUDED.student_fee_percent
                    """),
                    region,
                )
                seeded += 1
            except Exception as e:
                if verbose:
                    print(f"    ⚠ Could not seed region {region['region_code']}: {e}")

        session.commit()

    if verbose:
        print(f"  ✓ Seeded {seeded} region settings")

    return seeded


BADGE_SEED_DEFINITIONS = [
    {
        "slug": "welcome_aboard",
        "name": "Welcome Aboard",
        "criteria_type": "milestone",
        "description": "Complete your first lesson on iNSTAiNSTRU.",
        "criteria_config": {
            "counts": "completed_lessons",
            "goal": 1,
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 24,
            "instant": True,
        },
        "display_order": 1,
    },
    {
        "slug": "foundation_builder",
        "name": "Foundation Builder",
        "criteria_type": "milestone",
        "description": "Reach 3 completed lessons to build early momentum.",
        "criteria_config": {
            "counts": "completed_lessons",
            "goal": 3,
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 0,
            "instant": True,
        },
        "display_order": 2,
    },
    {
        "slug": "first_steps",
        "name": "First Steps",
        "criteria_type": "milestone",
        "description": "You earned this by completing 5 lessons.",
        "criteria_config": {
            "counts": "completed_lessons",
            "goal": 5,
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 0,
            "instant": True,
        },
        "display_order": 3,
    },
    {
        "slug": "dedicated_learner",
        "name": "Dedicated Learner",
        "criteria_type": "milestone",
        "description": "Complete 10 lessons to unlock this milestone.",
        "criteria_config": {
            "counts": "completed_lessons",
            "goal": 10,
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 0,
            "instant": True,
            "public": True,
        },
        "display_order": 4,
    },
    {
        "slug": "momentum_starter",
        "name": "Momentum Starter",
        "criteria_type": "velocity",
        "description": "Book your next lesson within 7 days and complete it within 21 days with the same instructor.",
        "criteria_config": {
            "window_days_to_book": 7,
            "window_days_to_complete": 21,
            "same_instructor_required": True,
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 0,
            "instant": True,
        },
        "display_order": 5,
    },
    {
        "slug": "consistent_learner",
        "name": "Consistent Learner",
        "criteria_type": "streak",
        "description": "Complete at least one lesson each week for 3 consecutive weeks (with a 1-day grace window).",
        "criteria_config": {
            "unit": "week",
            "consecutive_weeks": 3,
            "grace_days": 1,
            "grace_type": "fixed",
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 0,
            "instant": True,
        },
        "display_order": 6,
    },
    {
        "slug": "top_student",
        "name": "Top Student",
        "criteria_type": "quality",
        "description": "Earn outstanding feedback: high average rating with multiple reviews and reliable attendance.",
        "criteria_config": {
            "min_total_lessons": 10,
            "min_avg_rating": 4.8,
            "min_reviews": 3,
            "distinct_instructors_min": 2,
            "or_single_instructor_min_lessons": 8,
            "max_cancel_noshow_rate_pct_60d": 10,
            "hide_progress": True,
            "hold_hours": 336,
        },
        "display_order": 7,
    },
    {
        "slug": "explorer",
        "name": "Explorer",
        "criteria_type": "exploration",
        "description": "Take lessons across 3 different categories and rebook at least once in any category.",
        "criteria_config": {
            "distinct_categories": 3,
            "min_rebook_in_any_category": 1,
            "min_overall_avg_rating": 4.3,
            "show_after_total_lessons": 5,
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 0,
            "instant": True,
        },
        "display_order": 8,
    },
    {
        "slug": "favorite_partnership",
        "name": "Favorite Partnership",
        "criteria_type": "relationship",
        "description": "Complete 10 lessons with the same instructor.",
        "criteria_config": {
            "same_instructor_lessons": 10,
            "require_completion": True,
            "require_instructor_confirmation": True,
            "hold_hours": 0,
            "instant": True,
            "public": True,
        },
        "display_order": 9,
    },
    {
        "slug": "year_one_learner",
        "name": "Year-One Learner",
        "criteria_type": "loyalty",
        "description": "Be an active student for 12 months with 20+ total lessons and a recent lesson in the last 60 days.",
        "criteria_config": {
            "min_days_since_first_lesson": 365,
            "min_total_lessons": 20,
            "active_within_days": 60,
            "award_via_cron": True,
            "hold_hours": 0,
        },
        "display_order": 10,
    },
]

BADGE_SEED_LOOKUP = {entry["slug"]: entry for entry in BADGE_SEED_DEFINITIONS}

DEMO_BADGE_SLUGS = [
    "first_steps",
    "momentum_starter",
    "top_student",
    "dedicated_learner",
    "explorer",
    "consistent_learner",
]

DEMO_BADGE_SAMPLE_LIMIT = 15



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


def _normalize_slug(raw_slug: str) -> str:
    cleaned = (raw_slug or "").strip().lower()
    if not cleaned:
        return cleaned
    cleaned = re.sub(r"[^a-z0-9_-]+", "_", cleaned)
    cleaned = cleaned.replace("-", "_")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_")


def seed_badge_definitions(engine, verbose: bool = True) -> None:
    if verbose:
        print("\n▶ Seeding badge definitions…")

    # Check if badge_definitions table exists (database-agnostic)
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if 'badge_definitions' not in inspector.get_table_names():
        if verbose:
            print("  ⚠ badge_definitions table not found; skipping badge seed")
        return

    metadata = sa.MetaData()
    badge_definitions = sa.Table(
        "badge_definitions",
        metadata,
        sa.Column("id", sa.String(26)),
        sa.Column("slug", sa.String(100)),
        sa.Column("name", sa.String(200)),
        sa.Column("description", sa.Text()),
        sa.Column("criteria_type", sa.String(50)),
        sa.Column("criteria_config", sa.JSON()),
        sa.Column("icon_key", sa.String(100)),
        sa.Column("display_order", sa.Integer()),
        sa.Column("is_active", sa.Boolean()),
    )

    with Session(engine) as session:

        # Normalize any legacy slugs to snake_case
        normalize_count = 0
        existing_rows = session.execute(
            sa.select(badge_definitions.c.id, badge_definitions.c.slug)
        ).all()
        for row in existing_rows:
            normalized = _normalize_slug(row.slug)
            if normalized and normalized != row.slug:
                conflict = session.execute(
                    sa.select(badge_definitions.c.id)
                    .where(badge_definitions.c.slug == normalized)
                    .where(badge_definitions.c.id != row.id)
                ).first()
                if conflict:
                    if verbose:
                        print(
                            f"  ⚠ Skipping slug normalization for '{row.slug}' -> '{normalized}' due to conflict"
                        )
                    continue
                session.execute(
                    badge_definitions.update()
                    .where(badge_definitions.c.id == row.id)
                    .values(slug=normalized)
                )
                normalize_count += 1

        created = 0
        updated = 0
        unchanged = 0

        for seed in BADGE_SEED_DEFINITIONS:
            slug = _normalize_slug(seed["slug"])
            seed_payload = {
                "name": seed["name"],
                "description": seed.get("description"),
                "criteria_type": seed["criteria_type"],
                "criteria_config": copy.deepcopy(seed["criteria_config"]),
                "icon_key": seed.get("icon_key"),
                "display_order": seed.get("display_order"),
                "is_active": seed.get("is_active", True),
            }

            existing = session.execute(
                sa.select(
                    badge_definitions.c.id,
                    badge_definitions.c.name,
                    badge_definitions.c.description,
                    badge_definitions.c.criteria_type,
                    badge_definitions.c.criteria_config,
                    badge_definitions.c.icon_key,
                    badge_definitions.c.display_order,
                    badge_definitions.c.is_active,
                ).where(badge_definitions.c.slug == slug)
            ).mappings().first()

            if existing is None:
                session.execute(
                    badge_definitions.insert().values(
                        id=generate_ulid(),
                        slug=slug,
                        name=seed_payload["name"],
                        description=seed_payload["description"],
                        criteria_type=seed_payload["criteria_type"],
                        criteria_config=seed_payload["criteria_config"],
                        icon_key=seed_payload["icon_key"],
                        display_order=seed_payload["display_order"],
                        is_active=seed_payload["is_active"],
                    )
                )
                created += 1
                continue

            updates: dict[str, object] = {}
            for field, new_value in seed_payload.items():
                current_value = existing.get(field)
                if field == "criteria_config":
                    current_value = current_value or {}
                    if current_value != new_value:
                        updates[field] = new_value
                else:
                    if current_value != new_value:
                        updates[field] = new_value

            if updates:
                session.execute(
                    badge_definitions.update()
                    .where(badge_definitions.c.id == existing["id"])
                    .values(**updates)
                )
                updated += 1
            else:
                unchanged += 1

        session.commit()

        if verbose:
            print(
                f"  → Badges normalized={normalize_count}, created={created}, "
                f"updated={updated}, unchanged={unchanged}"
            )


def seed_demo_student_badges(
    engine,
    *,
    verbose: bool = True,
    sample_limit: int = DEMO_BADGE_SAMPLE_LIMIT,
) -> None:
    if verbose:
        print("\n▶ Awarding demo student badges for UI smoke tests…")

    metadata = sa.MetaData()
    badge_definitions = sa.Table(
        "badge_definitions",
        metadata,
        sa.Column("id", sa.String(26)),
        sa.Column("slug", sa.String(100)),
        sa.Column("criteria_config", sa.JSON()),
    )
    student_badges = sa.Table(
        "student_badges",
        metadata,
        sa.Column("id", sa.String(26)),
        sa.Column("student_id", sa.String(26)),
        sa.Column("badge_id", sa.String(26)),
        sa.Column("awarded_at", sa.DateTime(timezone=True)),
        sa.Column("progress_snapshot", sa.JSON()),
        sa.Column("status", sa.String(16)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("hold_until", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )

    with Session(engine) as session:
        student_badges_present = session.execute(
            sa.text("SELECT to_regclass('public.student_badges')")
        ).scalar()
        if student_badges_present is None:
            if verbose:
                print("  ⚠ student_badges table not found; skipping demo badge awards")
            return 0

        badge_rows = session.execute(
            sa.select(
                badge_definitions.c.id,
                badge_definitions.c.slug,
                badge_definitions.c.criteria_config,
            ).where(badge_definitions.c.slug.in_(DEMO_BADGE_SLUGS))
        ).all()

        badge_lookup = {
            row.slug: {"id": row.id, "criteria_config": row.criteria_config}
            for row in badge_rows
        }

        missing_slugs = sorted(set(DEMO_BADGE_SLUGS) - set(badge_lookup.keys()))
        if missing_slugs and verbose:
            print(
                "  ⚠ Missing badge definitions for: "
                + ", ".join(missing_slugs)
                + " (skipping those awards)"
            )

        if not badge_lookup:
            if verbose:
                print("  ⚠ No badge definitions available for demo awards; skipping")
            return 0

        student_role = session.execute(
            select(Role).where(Role.name == RoleName.STUDENT.value)
        ).scalar_one_or_none()
        if student_role is None:
            if verbose:
                print("  ⚠ Student role not found; skipping demo badge awards")
            return 0

        students = (
            session.execute(
                select(User)
                .join(User.roles)
                .where(Role.id == student_role.id)
            )
            .scalars()
            .unique()
            .all()
        )

        if not students:
            if verbose:
                print("  ⚠ No student users found for demo badge awards")
            return 0

        target_email = "emma.johnson@example.com"
        emma_user = next(
            (user for user in students if (user.email or "").lower() == target_email),
            None,
        )
        if emma_user is None and verbose:
            print("  ⚠ emma.johnson@example.com not found among students; continuing without")

        other_students = [user for user in students if emma_user is None or user.id != emma_user.id]
        approx_sample = int(len(other_students) * 0.1)
        if approx_sample == 0 and other_students:
            approx_sample = 1
        sample_size = min(sample_limit, approx_sample)
        if sample_size > len(other_students):
            sample_size = len(other_students)

        sampled_students = random.sample(other_students, sample_size) if sample_size else []

        selected_students = []
        if emma_user is not None:
            selected_students.append(emma_user)
        selected_students.extend(sampled_students)

        if not selected_students:
            if verbose:
                print("  ⚠ No students selected for demo badge awards")
            return 0

        badge_ids = [info["id"] for info in badge_lookup.values()]
        existing_pairs = session.execute(
            sa.select(student_badges.c.student_id, student_badges.c.badge_id)
            .where(student_badges.c.student_id.in_([student.id for student in selected_students]))
            .where(student_badges.c.badge_id.in_(badge_ids))
        ).all()
        existing_set = {(row.student_id, row.badge_id) for row in existing_pairs}

        awarded = 0
        skipped_existing = 0

        for student in selected_students:
            available_slugs = list(badge_lookup.keys())
            if not available_slugs:
                break

            desired_count = 3 if emma_user and student.id == emma_user.id else random.randint(2, 3)
            desired_count = max(2, min(desired_count, len(available_slugs)))
            chosen_slugs = random.sample(available_slugs, desired_count)

            for slug in chosen_slugs:
                badge_info = badge_lookup.get(slug)
                if not badge_info:
                    continue
                pair = (student.id, badge_info["id"])
                if pair in existing_set:
                    skipped_existing += 1
                    continue

                criteria_config = badge_info.get("criteria_config") or {}
                goal_value = None
                if isinstance(criteria_config, dict):
                    goal_value = criteria_config.get("goal")
                if isinstance(goal_value, (int, float)):
                    snapshot = {"current": goal_value, "goal": goal_value}
                else:
                    snapshot = {"status": "complete"}

                timestamp = datetime.now(timezone.utc)

                session.execute(
                    student_badges.insert().values(
                        id=generate_ulid(),
                        student_id=student.id,
                        badge_id=badge_info["id"],
                        awarded_at=timestamp,
                        progress_snapshot=snapshot,
                        status="confirmed",
                        hold_until=None,
                        confirmed_at=timestamp,
                        revoked_at=None,
                    )
                )
                existing_set.add(pair)
                awarded += 1

        session.commit()

        if verbose:
            print(
                f"  → Demo badge awards: students={len(selected_students)}, "
                f"created={awarded}, skipped_existing={skipped_existing}"
            )
        return awarded



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


def seed_referral_config(engine, site_mode: str, actor: str = "seed") -> None:
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM referral_config LIMIT 1")).first()
        if exists:
            print("[SEED][referral_config] already present; no-op")
            return

        normalized_mode = (site_mode or "local").strip().lower()
        cap = 20 if normalized_mode in {"local", "int"} else 50 if normalized_mode == "preview" else 200

        conn.execute(
            text(
                """
                INSERT INTO referral_config
                  (id, version, enabled, student_amount_cents, instructor_amount_cents,
                   min_basket_cents, hold_days, expiry_months, student_global_cap,
                   updated_by, note)
                VALUES
                  (:id, 1, TRUE, 2000, 5000,
                   8000, 7, 6, :cap,
                   :actor, 'initial seed')
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "cap": cap,
                "actor": actor,
            },
        )
        print("[SEED][referral_config] inserted version=1")


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

    engine = create_engine(settings.get_database_url())

    # Seed region settings for multi-city support
    if verbose:
        print("\n▶ Seeding region settings…")
    try:
        seed_region_settings(engine, verbose=verbose)
    except Exception as e:
        print(f"  ⚠ Skipping region_settings seed: {e}")

    # Sync search_locations from region_boundaries for NL search
    if verbose:
        print("\n▶ Syncing search locations for NL search…")
    try:
        sync_search_locations_from_regions(engine, verbose=verbose, region_code="nyc")
    except Exception as e:
        print(f"  ⚠ Skipping search_locations sync: {e}")
    seed_badge_definitions(engine, verbose=verbose)

    # Seed baseline admin account
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

    seed_referral_config(engine, site_mode=settings.site_mode, actor="seed-system")


def seed_mock_data_phases(
    *,
    verbose: bool = True,
    include_reviews: bool = True,
    include_credits: bool = True,
    include_badges: bool = True,
    print_summary: bool = True,
) -> tuple["DatabaseSeeder", dict[str, int]]:
    """Seed mock data in phases, returning the seeder and aggregate stats."""
    from reset_and_seed_yaml import DatabaseSeeder  # noqa: E402
    from seed_catalog_only import seed_catalog  # noqa: E402

    stats = {
        "students_seeded": 0,
        "instructors_seeded": 0,
        "bookings_created": 0,
        "reviews_created": 0,
        "reviews_skipped": False,
        "credits_created": 0,
        "badges_awarded": 0,
    }

    seeder = DatabaseSeeder()

    # Clean previous mock/test data (users with @example.com, seeded catalog, etc.)
    # This keeps the database schema intact and avoids dropping real data in prod.
    if verbose:
        print("\n▶ Cleaning previous mock data (idempotent)…")
    seeder.reset_database()

    # After cleaning, we must re-seed catalog for mapping instructor services
    if verbose:
        print("\n▶ Reseeding service catalog required for mock instructors…")
    seed_catalog(db_url=settings.get_database_url(), verbose=verbose)

    if verbose:
        print("\n▶ Creating mock users and instructors…")
    seeder.create_students()
    seeder.create_instructors()
    stats["students_seeded"] = len(seeder.loader.get_students())
    stats["instructors_seeded"] = len(seeder.loader.get_instructors())

    if verbose:
        print("\n▶ Creating availability and coverage areas…")
    seeder.create_availability()
    seeder.create_coverage_areas()

    if verbose:
        print("\n▶ Creating bookings and reviews…")
    stats["bookings_created"] = seeder.create_bookings() or 0

    # Check if bitmap pipeline completed before seeding reviews
    bitmap_pipeline_completed = os.getenv("BITMAP_PIPELINE_COMPLETED") == "1"
    if not bitmap_pipeline_completed:
        if verbose:
            print("  ⚠️  Bitmap pipeline not marked as completed; reviews may skip due to missing bitmap coverage.")
            print("  ℹ️  Reviews will check bitmap coverage and skip if empty.")

    if include_reviews:
        stats["reviews_created"] = seeder.create_reviews(strict=False) or 0  # Don't fail if bitmap coverage is missing
    else:
        stats["reviews_skipped"] = True

    if include_credits:
        stats["credits_created"] = seeder.create_sample_platform_credits() or 0

    if print_summary:
        seeder.print_summary()

    engine = seeder.engine
    if include_badges:
        badges = seed_demo_student_badges(engine, verbose=verbose)
        stats["badges_awarded"] = badges or 0

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

    return seeder, stats


def seed_mock_data(verbose: bool = True, *, return_stats: bool = False) -> dict[str, int] | None:
    """Seed mock users, instructors, availability, bookings, reviews."""
    seeder, stats = seed_mock_data_phases(
        verbose=verbose,
        include_reviews=True,
        include_credits=True,
        include_badges=True,
        print_summary=True,
    )
    # seed_mock_data_phases already prints summary; dispose engine to free resources
    seeder.engine.dispose()
    if return_stats:
        return stats
    return None


def seed_beta_access_for_instructors(session: Session) -> tuple[int, int]:
    """Grant beta access rows for all instructor-role users lacking one.

    Returns a tuple ``(created_count, existing_count)`` where
    ``existing_count`` reflects instructors that already had a matching grant
    before this helper ran.
    """

    instructor_role = session.execute(
        select(Role).where(Role.name == RoleName.INSTRUCTOR.value)
    ).scalar_one_or_none()
    if instructor_role is None:
        return 0, 0

    instructor_ids = session.execute(
        select(User.id)
        .join(User.roles)
        .where(Role.id == instructor_role.id)
    ).scalars().all()
    if not instructor_ids:
        return 0, 0

    existing_user_ids = set(
        session.execute(
            select(BetaAccess.user_id).where(
                BetaAccess.role == "instructor",
                BetaAccess.user_id.in_(instructor_ids),
            )
        ).scalars()
    )

    beta_repo = BetaAccessRepository(session)
    settings_repo = BetaSettingsRepository(session)
    # Ensure beta settings row exists (repository creates default if missing)
    settings_repo.get_singleton()

    created = 0
    for user_id in instructor_ids:
        if user_id in existing_user_ids:
            continue
        beta_repo.grant_access(
            user_id=user_id,
            role="instructor",
            phase="instructor_only",
            invited_by_code=None,
        )
        created += 1

    session.commit()
    existing_count = len(existing_user_ids)
    return created, existing_count


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

    # Only seed mock data if requested (and not when explicitly system-only)
    if args.include_mock_users:
        seed_mock_data(verbose=verbose)
    elif not args.system_only and verbose:
        print("\nℹ️  Skipping mock users/instructors/bookings (use --include-mock-users to add them)")

    print("\n✅ Seeding complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
