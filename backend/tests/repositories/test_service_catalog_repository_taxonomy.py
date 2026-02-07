# backend/tests/repositories/test_service_catalog_repository_taxonomy.py
"""
Integration tests for ServiceCatalogRepository taxonomy methods.

Tests the 7 new repository methods added in Phase 3 for the
3-level taxonomy (Category → Subcategory → Service).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
import ulid as _ulid

from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.repositories.service_catalog_repository import ServiceCatalogRepository


def _uid() -> str:
    return str(_ulid.ULID()).lower()[:10]


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def taxonomy_tree(db: Session):
    """Build a 2-category taxonomy tree for repo tests."""
    uid = _uid()

    # Category A with 2 subcategories, each with services
    cat_a = ServiceCategory(name=f"Repo Cat A {uid}", display_order=0)
    db.add(cat_a)
    db.flush()

    sub_a1 = ServiceSubcategory(category_id=cat_a.id, name=f"Repo Sub A1 {uid}", display_order=0)
    sub_a2 = ServiceSubcategory(category_id=cat_a.id, name=f"Repo Sub A2 {uid}", display_order=1)
    db.add_all([sub_a1, sub_a2])
    db.flush()

    slug_a1_1 = f"repo-a1-1-{uid}"
    slug_a1_2 = f"repo-a1-2-{uid}"
    slug_a2_1 = f"repo-a2-1-{uid}"

    svc_a1_1 = ServiceCatalog(
        subcategory_id=sub_a1.id,
        name=f"Repo Svc A1-1 {uid}",
        slug=slug_a1_1,
        display_order=0,
        is_active=True,
        eligible_age_groups=["kids", "teens"],
    )
    svc_a1_2 = ServiceCatalog(
        subcategory_id=sub_a1.id,
        name=f"Repo Svc A1-2 {uid}",
        slug=slug_a1_2,
        display_order=1,
        is_active=True,
        eligible_age_groups=["adults"],
    )
    svc_a2_1 = ServiceCatalog(
        subcategory_id=sub_a2.id,
        name=f"Repo Svc A2-1 {uid}",
        slug=slug_a2_1,
        display_order=0,
        is_active=True,
        eligible_age_groups=["kids", "teens", "adults"],
    )
    db.add_all([svc_a1_1, svc_a1_2, svc_a2_1])
    db.flush()

    # Category B with 1 subcategory, 1 inactive service
    cat_b = ServiceCategory(name=f"Repo Cat B {uid}", display_order=1)
    db.add(cat_b)
    db.flush()

    sub_b1 = ServiceSubcategory(category_id=cat_b.id, name=f"Repo Sub B1 {uid}", display_order=0)
    db.add(sub_b1)
    db.flush()

    slug_b1 = f"repo-b1-inactive-{uid}"
    svc_b1_inactive = ServiceCatalog(
        subcategory_id=sub_b1.id,
        name=f"Repo Svc B1 Inactive {uid}",
        slug=slug_b1,
        display_order=0,
        is_active=False,
        eligible_age_groups=["toddler"],
    )
    db.add(svc_b1_inactive)
    db.commit()

    return {
        "cat_a": cat_a,
        "cat_b": cat_b,
        "sub_a1": sub_a1,
        "sub_a2": sub_a2,
        "sub_b1": sub_b1,
        "svc_a1_1": svc_a1_1,
        "svc_a1_2": svc_a1_2,
        "svc_a2_1": svc_a2_1,
        "svc_b1_inactive": svc_b1_inactive,
        "slug_a1_1": slug_a1_1,
        "slug_a1_2": slug_a1_2,
        "slug_a2_1": slug_a2_1,
        "slug_b1": slug_b1,
    }


# ── Tests ──────────────────────────────────────────────────────


class TestGetCategoriesWithSubcategories:
    def test_returns_categories_with_subcategories_loaded(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        categories = repo.get_categories_with_subcategories()

        # Find our test categories
        cat_a = next((c for c in categories if c.id == taxonomy_tree["cat_a"].id), None)
        assert cat_a is not None
        assert len(cat_a.subcategories) == 2

    def test_ordered_by_display_order(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        categories = repo.get_categories_with_subcategories()

        ids = [c.id for c in categories]
        assert ids.index(taxonomy_tree["cat_a"].id) < ids.index(taxonomy_tree["cat_b"].id)


class TestGetCategoryTree:
    def test_full_3level_tree(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        tree = repo.get_category_tree(taxonomy_tree["cat_a"].id)

        assert tree is not None
        assert tree.id == taxonomy_tree["cat_a"].id
        assert len(tree.subcategories) == 2

        sub_a1 = next(s for s in tree.subcategories if s.id == taxonomy_tree["sub_a1"].id)
        assert len(sub_a1.services) == 2

    def test_nonexistent_category_returns_none(self, db: Session):
        repo = ServiceCatalogRepository(db)
        result = repo.get_category_tree("01JNONEXISTENT000000000000")
        assert result is None


class TestGetSubcategoryWithServices:
    def test_loads_services(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        sub = repo.get_subcategory_with_services(taxonomy_tree["sub_a1"].id)

        assert sub is not None
        assert sub.id == taxonomy_tree["sub_a1"].id
        assert len(sub.services) == 2

    def test_nonexistent_returns_none(self, db: Session):
        repo = ServiceCatalogRepository(db)
        result = repo.get_subcategory_with_services("01JNONEXISTENT000000000000")
        assert result is None


class TestGetSubcategoriesByCategory:
    def test_returns_ordered_subcategories(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        subs = repo.get_subcategories_by_category(taxonomy_tree["cat_a"].id)

        assert len(subs) == 2
        assert subs[0].id == taxonomy_tree["sub_a1"].id
        assert subs[1].id == taxonomy_tree["sub_a2"].id

    def test_empty_for_nonexistent_category(self, db: Session):
        repo = ServiceCatalogRepository(db)
        subs = repo.get_subcategories_by_category("01JNONEXISTENT000000000000")
        assert subs == []


class TestGetServiceWithSubcategory:
    def test_eager_loads_subcategory_and_category(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        svc = repo.get_service_with_subcategory(taxonomy_tree["svc_a1_1"].id)

        assert svc is not None
        assert svc.subcategory is not None
        assert svc.subcategory.id == taxonomy_tree["sub_a1"].id
        assert svc.subcategory.category is not None
        assert svc.subcategory.category.id == taxonomy_tree["cat_a"].id

    def test_nonexistent_returns_none(self, db: Session):
        repo = ServiceCatalogRepository(db)
        result = repo.get_service_with_subcategory("01JNONEXISTENT000000000000")
        assert result is None


class TestGetServicesByEligibleAgeGroup:
    def test_kids_returns_matching_services(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        services = repo.get_services_by_eligible_age_group("kids", limit=1000)

        slugs = {s.slug for s in services}
        assert taxonomy_tree["slug_a1_1"] in slugs  # kids + teens
        assert taxonomy_tree["slug_a2_1"] in slugs  # kids + teens + adults
        assert taxonomy_tree["slug_a1_2"] not in slugs  # adults only

    def test_adults_returns_matching_services(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        services = repo.get_services_by_eligible_age_group("adults", limit=1000)

        slugs = {s.slug for s in services}
        # Verify filtering works: adults-only service is included
        assert taxonomy_tree["slug_a1_2"] in slugs
        assert taxonomy_tree["slug_a2_1"] in slugs
        # kids+teens only service is excluded
        assert taxonomy_tree["slug_a1_1"] not in slugs

    def test_inactive_excluded(self, db: Session, taxonomy_tree):
        """Inactive services are filtered out even if age group matches."""
        repo = ServiceCatalogRepository(db)
        services = repo.get_services_by_eligible_age_group("toddler")

        slugs = {s.slug for s in services}
        assert taxonomy_tree["slug_b1"] not in slugs

    def test_nonexistent_age_group_returns_empty(self, db: Session, taxonomy_tree):
        repo = ServiceCatalogRepository(db)
        services = repo.get_services_by_eligible_age_group("nonexistent_group_xyz")
        ids = {s.id for s in services}
        # None of our test services should match
        assert taxonomy_tree["svc_a1_1"].id not in ids
        assert taxonomy_tree["svc_a1_2"].id not in ids
