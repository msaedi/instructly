# backend/tests/fixtures/taxonomy_fixtures.py
"""
Centralized taxonomy fixture that discovers seeded data at runtime.

Since all IDs are ULIDs generated at seed time, we never hardcode them.
Instead, we query the DB for known category/subcategory names from the
seed script (seed_taxonomy.py) and expose them via a typed dataclass.

Usage in tests:
    def test_something(self, db, taxonomy):
        repo = SomeRepository(db)
        result = repo.some_method(taxonomy.music_category.id)
        assert result is not None
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pytest
from sqlalchemy.orm import Session, joinedload

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory


@dataclass
class TaxonomyData:
    """Seeded taxonomy data discovered at runtime — never hardcode ULIDs."""

    # Categories
    music_category: ServiceCategory
    tutoring_category: ServiceCategory
    all_categories: List[ServiceCategory]

    # First subcategory under each
    music_first_subcategory: ServiceSubcategory
    tutoring_first_subcategory: ServiceSubcategory

    # First service under first music subcategory
    first_service: ServiceCatalog

    # A subcategory known to have filters (from Tutoring tree)
    subcategory_with_filters: ServiceSubcategory

    # A subcategory known to have NO filters (Music > Piano typically has none)
    subcategory_without_filters: Optional[ServiceSubcategory]


@pytest.fixture
def taxonomy(db: Session) -> TaxonomyData:
    """Discover seeded taxonomy — works regardless of ULID regeneration.

    Requires that seed_taxonomy.py has been run against the INT database.
    The fixture queries for known category names from the seed data:
      - "Music" and "Tutoring & Test Prep"
    and navigates the 3-level tree to provide test-friendly handles.
    """
    categories = (
        db.query(ServiceCategory)
        .options(
            joinedload(ServiceCategory.subcategories)
            .joinedload(ServiceSubcategory.services),
            joinedload(ServiceCategory.subcategories)
            .joinedload(ServiceSubcategory.subcategory_filters),
        )
        .order_by(ServiceCategory.display_order)
        .all()
    )

    music = next((c for c in categories if c.name == "Music"), None)
    tutoring = next((c for c in categories if c.name == "Tutoring & Test Prep"), None)

    if not music or not tutoring:
        pytest.skip(
            "Seeded taxonomy data not found (Music / Tutoring & Test Prep). "
            "Run: python scripts/seed_data/seed_taxonomy.py"
        )

    # First subcategory by display_order
    music_subs = sorted(music.subcategories, key=lambda s: s.display_order)
    tutoring_subs = sorted(tutoring.subcategories, key=lambda s: s.display_order)

    music_sub = music_subs[0]  # Piano (display_order=1)
    tutoring_sub = tutoring_subs[0]  # Math (display_order=1)

    # First service under first music subcategory
    music_services = sorted(music_sub.services, key=lambda s: s.display_order)
    first_service = music_services[0] if music_services else None
    if not first_service:
        pytest.skip("No services found under first Music subcategory")

    # Find subcategory WITH filters (Tutoring subcategories typically have filters)
    sub_with_filters = next(
        (s for s in tutoring_subs if s.subcategory_filters),
        tutoring_sub,
    )

    # Find subcategory WITHOUT filters
    # Check Music subcategories first (some may have no filters)
    sub_without_filters = next(
        (s for s in music_subs if not s.subcategory_filters),
        None,
    )

    return TaxonomyData(
        music_category=music,
        tutoring_category=tutoring,
        all_categories=categories,
        music_first_subcategory=music_sub,
        tutoring_first_subcategory=tutoring_sub,
        first_service=first_service,
        subcategory_with_filters=sub_with_filters,
        subcategory_without_filters=sub_without_filters,
    )
