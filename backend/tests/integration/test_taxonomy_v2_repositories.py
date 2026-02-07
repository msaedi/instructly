# backend/tests/integration/test_taxonomy_v2_repositories.py
"""
Integration tests for taxonomy v2 repositories.

These tests require the INT database with seeded taxonomy data.
Uses the `taxonomy` fixture from tests/fixtures/taxonomy_fixtures.py
to discover seeded ULIDs at runtime.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
import ulid as _ulid

from app.models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory
from app.repositories.category_repository import CategoryRepository
from app.repositories.service_catalog_repository import ServiceCatalogRepository
from app.repositories.subcategory_repository import SubcategoryRepository
from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
from tests.fixtures.taxonomy_fixtures import TaxonomyData

# ── Helpers ────────────────────────────────────────────────────

def _uid() -> str:
    return str(_ulid.ULID())


def _short_uid() -> str:
    """Return last 12 chars of a ULID (random portion) for unique slugs/keys."""
    return str(_ulid.ULID())[-12:].lower()


def _make_category(db: Session, **kw) -> ServiceCategory:
    cat = ServiceCategory(
        name=kw.get("name", f"RepoTestCat-{_short_uid()}"),
        slug=kw.get("slug"),
        display_order=kw.get("display_order", 0),
    )
    db.add(cat)
    db.flush()
    return cat


def _make_subcategory(
    db: Session, category_id: str, **kw
) -> ServiceSubcategory:
    sub = ServiceSubcategory(
        category_id=category_id,
        name=kw.get("name", f"RepoTestSub-{_short_uid()}"),
        slug=kw.get("slug"),
        display_order=kw.get("display_order", 0),
        is_active=kw.get("is_active", True),
    )
    db.add(sub)
    db.flush()
    return sub


def _make_service(
    db: Session, subcategory_id: str, **kw
) -> ServiceCatalog:
    svc = ServiceCatalog(
        subcategory_id=subcategory_id,
        name=kw.get("name", f"RepoTestSvc-{_short_uid()}"),
        slug=kw.get("slug", f"repo-svc-{_short_uid()}"),
        display_order=kw.get("display_order", 0),
        eligible_age_groups=kw.get(
            "eligible_age_groups",
            ["toddler", "kids", "teens", "adults"],
        ),
    )
    db.add(svc)
    db.flush()
    return svc


def _make_filter_chain(
    db: Session,
    subcategory_id: str,
    key: str = "test_filter",
    values: list[str] | None = None,
    is_required: bool = False,
) -> tuple[FilterDefinition, SubcategoryFilter, list[FilterOption]]:
    """Create FilterDefinition + options + SubcategoryFilter + SubcategoryFilterOptions."""
    values = values or ["opt_a", "opt_b"]

    fd = FilterDefinition(
        key=f"{key}_{_short_uid()}",
        display_name=key.replace("_", " ").title(),
        filter_type="multi_select",
    )
    db.add(fd)
    db.flush()

    options: list[FilterOption] = []
    for i, val in enumerate(values):
        fo = FilterOption(
            filter_definition_id=fd.id,
            value=val,
            display_name=val.replace("_", " ").title(),
            display_order=i,
        )
        db.add(fo)
        db.flush()
        options.append(fo)

    sf = SubcategoryFilter(
        subcategory_id=subcategory_id,
        filter_definition_id=fd.id,
        display_order=0,
        is_required=is_required,
    )
    db.add(sf)
    db.flush()

    for i, fo in enumerate(options):
        sfo = SubcategoryFilterOption(
            subcategory_filter_id=sf.id,
            filter_option_id=fo.id,
            display_order=i,
        )
        db.add(sfo)

    db.flush()
    return fd, sf, options


# ═══════════════════════════════════════════════════════════════
# CategoryRepository Tests
# ═══════════════════════════════════════════════════════════════


class TestCategoryRepositoryGetAllActive:
    def test_returns_ordered_categories(self, db: Session) -> None:
        _make_category(db, name="Cat B", display_order=2)
        _make_category(db, name="Cat A", display_order=1)
        db.commit()

        repo = CategoryRepository(db)
        cats = repo.get_all_active()

        orders = [c.display_order for c in cats]
        assert orders == sorted(orders)

    def test_include_subcategories(self, db: Session) -> None:
        cat = _make_category(db, name="Cat With Subs")
        _make_subcategory(db, cat.id, name="Sub 1")
        _make_subcategory(db, cat.id, name="Sub 2")
        db.commit()

        repo = CategoryRepository(db)
        cats = repo.get_all_active(include_subcategories=True)

        target = next(c for c in cats if c.id == cat.id)
        assert len(target.subcategories) == 2


class TestCategoryRepositoryGetBySlug:
    def test_finds_by_slug(self, db: Session) -> None:
        slug = f"cat-slug-{_short_uid()}"
        cat = _make_category(db, name="Slugged Cat", slug=slug)
        _make_subcategory(db, cat.id, name="Sub Under Slug")
        db.commit()

        repo = CategoryRepository(db)
        result = repo.get_by_slug(slug)

        assert result is not None
        assert result.id == cat.id
        assert len(result.subcategories) >= 1

    def test_returns_none_for_missing_slug(self, db: Session) -> None:
        repo = CategoryRepository(db)
        assert repo.get_by_slug("nonexistent-slug-xyz") is None


class TestCategoryRepositoryGetWithFullTree:
    def test_loads_full_tree(self, db: Session) -> None:
        cat = _make_category(db, name="TreeCat")
        sub = _make_subcategory(db, cat.id, name="TreeSub")
        _make_service(db, sub.id, name="TreeSvc")
        db.commit()

        repo = CategoryRepository(db)
        result = repo.get_with_full_tree(cat.id)

        assert result is not None
        assert len(result.subcategories) >= 1
        assert len(result.subcategories[0].services) >= 1

    def test_returns_none_for_missing_id(self, db: Session) -> None:
        repo = CategoryRepository(db)
        assert repo.get_with_full_tree("01NONEXISTENT0000000000000") is None


# ═══════════════════════════════════════════════════════════════
# SubcategoryRepository Tests
# ═══════════════════════════════════════════════════════════════


class TestSubcategoryRepositoryGetBySlug:
    def test_finds_by_slug(self, db: Session) -> None:
        cat = _make_category(db)
        slug = f"sub-slug-{_short_uid()}"
        sub = _make_subcategory(db, cat.id, name="Slugged Sub", slug=slug)
        _make_service(db, sub.id)
        db.commit()

        repo = SubcategoryRepository(db)
        result = repo.get_by_slug(slug)

        assert result is not None
        assert result.id == sub.id
        # Eagerly loaded
        assert result.category is not None
        assert len(result.services) >= 1

    def test_returns_none_for_missing(self, db: Session) -> None:
        repo = SubcategoryRepository(db)
        assert repo.get_by_slug("missing-sub-slug") is None


class TestSubcategoryRepositoryGetByCategory:
    def test_returns_ordered_subcategories(self, db: Session) -> None:
        cat = _make_category(db)
        _make_subcategory(db, cat.id, name="Second", display_order=2)
        _make_subcategory(db, cat.id, name="First", display_order=1)
        db.commit()

        repo = SubcategoryRepository(db)
        subs = repo.get_by_category(cat.id)

        orders = [s.display_order for s in subs]
        assert orders == sorted(orders)

    def test_respects_active_only(self, db: Session) -> None:
        cat = _make_category(db)
        _make_subcategory(db, cat.id, name="Active", is_active=True)
        _make_subcategory(db, cat.id, name="Inactive", is_active=False)
        db.commit()

        repo = SubcategoryRepository(db)
        active = repo.get_by_category(cat.id, active_only=True)
        all_subs = repo.get_by_category(cat.id, active_only=False)

        assert len(active) < len(all_subs)
        assert all(s.is_active for s in active)


class TestSubcategoryRepositoryGetWithFilters:
    def test_loads_filter_tree(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        _make_filter_chain(db, sub.id, key="grade", values=["elem", "middle"])
        db.commit()

        repo = SubcategoryRepository(db)
        result = repo.get_with_filters(sub.id)

        assert result is not None
        assert len(result.subcategory_filters) >= 1
        sf = result.subcategory_filters[0]
        assert sf.filter_definition is not None
        assert len(sf.filter_options) >= 1

    def test_returns_none_for_missing(self, db: Session) -> None:
        repo = SubcategoryRepository(db)
        assert repo.get_with_filters("01NONEXISTENT0000000000000") is None


class TestSubcategoryRepositoryGetByCategorySlug:
    def test_resolves_two_slug_url(self, db: Session) -> None:
        cat_slug = f"cat-{_short_uid()}"
        sub_slug = f"sub-{_short_uid()}"
        cat = _make_category(db, slug=cat_slug)
        sub = _make_subcategory(db, cat.id, slug=sub_slug)
        _make_service(db, sub.id)
        db.commit()

        repo = SubcategoryRepository(db)
        result = repo.get_by_category_slug(cat_slug, sub_slug)

        assert result is not None
        assert result.id == sub.id
        assert result.category is not None
        assert result.category.slug == cat_slug

    def test_returns_none_for_mismatched_slugs(self, db: Session) -> None:
        cat_slug = f"cat-{_short_uid()}"
        cat = _make_category(db, slug=cat_slug)
        _make_subcategory(db, cat.id, slug=f"sub-{_short_uid()}")
        db.commit()

        repo = SubcategoryRepository(db)
        result = repo.get_by_category_slug(cat_slug, "wrong-sub-slug")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# ServiceCatalogRepository Tests (new methods)
# ═══════════════════════════════════════════════════════════════


class TestServiceCatalogRepositoryGetBySlug:
    def test_finds_by_slug(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        slug = f"svc-slug-{_short_uid()}"
        svc = _make_service(db, sub.id, slug=slug, name="Slug Service")
        db.commit()

        repo = ServiceCatalogRepository(db)
        result = repo.get_by_slug(slug)

        assert result is not None
        assert result.id == svc.id
        # Eagerly loaded subcategory→category
        assert result.subcategory is not None

    def test_returns_none_for_missing(self, db: Session) -> None:
        repo = ServiceCatalogRepository(db)
        assert repo.get_by_slug("nonexistent-service-slug") is None


class TestServiceCatalogRepositoryGetBySubcategory:
    def test_returns_ordered_services(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        _make_service(db, sub.id, name="Second", display_order=2)
        _make_service(db, sub.id, name="First", display_order=1)
        db.commit()

        repo = ServiceCatalogRepository(db)
        services = repo.get_by_subcategory(sub.id)

        orders = [s.display_order for s in services]
        assert orders == sorted(orders)


class TestServiceCatalogRepositorySearchByName:
    def test_typeahead_search(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        unique = _short_uid()
        _make_service(db, sub.id, name=f"UniqueService{unique}")
        db.commit()

        repo = ServiceCatalogRepository(db)
        results = repo.search_services_by_name(f"UniqueService{unique}")

        assert len(results) >= 1
        assert any(f"UniqueService{unique}" in s.name for s in results)


class TestServiceCatalogRepositoryGetByAgeGroup:
    def test_array_containment_query(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        _make_service(
            db,
            sub.id,
            name="Kids Only Svc",
            eligible_age_groups=["kids"],
        )
        _make_service(
            db,
            sub.id,
            name="Adults Only Svc",
            eligible_age_groups=["adults"],
        )
        db.commit()

        repo = ServiceCatalogRepository(db)
        kids_services = repo.get_services_by_eligible_age_group("kids")

        names = [s.name for s in kids_services]
        assert "Kids Only Svc" in names
        assert "Adults Only Svc" not in names


# ═══════════════════════════════════════════════════════════════
# TaxonomyFilterRepository Tests
# ═══════════════════════════════════════════════════════════════


class TestTaxonomyFilterRepoGetFiltersForSubcategory:
    def test_returns_filters_with_options(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        _make_filter_chain(
            db, sub.id, key="grade", values=["elem", "middle", "high"]
        )
        db.commit()

        repo = TaxonomyFilterRepository(db)
        filters = repo.get_filters_for_subcategory(sub.id)

        assert len(filters) >= 1
        f = filters[0]
        assert "filter_key" in f
        assert "options" in f
        assert len(f["options"]) == 3

    def test_empty_for_subcategory_without_filters(
        self, db: Session
    ) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        db.commit()

        repo = TaxonomyFilterRepository(db)
        filters = repo.get_filters_for_subcategory(sub.id)

        assert filters == []


class TestTaxonomyFilterRepoValidateSelections:
    def test_accepts_valid_selections(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd, sf, options = _make_filter_chain(
            db, sub.id, key="level", values=["beginner", "advanced"]
        )
        db.commit()

        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            sub.id, {fd.key: ["beginner"]}
        )

        assert is_valid is True
        assert errors == []

    def test_rejects_invalid_selections(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd, sf, options = _make_filter_chain(
            db, sub.id, key="level", values=["beginner", "advanced"]
        )
        db.commit()

        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            sub.id, {fd.key: ["nonexistent_option"]}
        )

        assert is_valid is False
        assert len(errors) >= 1

    def test_rejects_unknown_filter_key(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        db.commit()

        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(
            sub.id, {"bogus_key": ["value"]}
        )

        assert is_valid is False
        assert any("Unknown filter key" in e for e in errors)

    def test_accepts_empty_selections(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        db.commit()

        repo = TaxonomyFilterRepository(db)
        is_valid, errors = repo.validate_filter_selections(sub.id, {})

        assert is_valid is True
        assert errors == []


class TestTaxonomyFilterRepoGetAllDefinitions:
    def test_returns_definitions_with_options(self, db: Session) -> None:
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        _make_filter_chain(db, sub.id, key="defs_test", values=["a", "b"])
        db.commit()

        repo = TaxonomyFilterRepository(db)
        defs = repo.get_all_definitions()

        assert len(defs) >= 1
        # Each definition should have options loaded
        for d in defs:
            assert hasattr(d, "options")

    def test_active_only_filter(self, db: Session) -> None:
        fd_active = FilterDefinition(
            key=f"active_{_short_uid()}",
            display_name="Active Filter",
            filter_type="multi_select",
            is_active=True,
        )
        fd_inactive = FilterDefinition(
            key=f"inactive_{_short_uid()}",
            display_name="Inactive Filter",
            filter_type="multi_select",
            is_active=False,
        )
        db.add_all([fd_active, fd_inactive])
        db.commit()

        repo = TaxonomyFilterRepository(db)
        active_defs = repo.get_all_definitions(active_only=True)
        all_defs = repo.get_all_definitions(active_only=False)

        active_keys = {d.key for d in active_defs}
        all_keys = {d.key for d in all_defs}

        assert fd_active.key in active_keys
        assert fd_inactive.key not in active_keys
        assert fd_inactive.key in all_keys


# ═══════════════════════════════════════════════════════════════
# Seeded Data Tests (using taxonomy fixture)
# ═══════════════════════════════════════════════════════════════


class TestWithSeededData:
    """Tests that exercise repos against real seed data."""

    def test_category_repo_finds_music(
        self, db: Session, taxonomy: TaxonomyData
    ) -> None:
        repo = CategoryRepository(db)
        cats = repo.get_all_active(include_subcategories=True)

        music = next(
            (c for c in cats if c.id == taxonomy.music_category.id), None
        )
        assert music is not None
        assert len(music.subcategories) > 0

    def test_subcategory_repo_by_category(
        self, db: Session, taxonomy: TaxonomyData
    ) -> None:
        repo = SubcategoryRepository(db)
        subs = repo.get_by_category(taxonomy.music_category.id)

        assert len(subs) > 0
        assert all(
            s.category_id == taxonomy.music_category.id for s in subs
        )

    def test_service_catalog_repo_by_subcategory(
        self, db: Session, taxonomy: TaxonomyData
    ) -> None:
        repo = ServiceCatalogRepository(db)
        services = repo.get_by_subcategory(
            taxonomy.music_first_subcategory.id
        )

        assert len(services) > 0

    def test_filter_repo_on_subcategory_with_filters(
        self, db: Session, taxonomy: TaxonomyData
    ) -> None:
        repo = TaxonomyFilterRepository(db)
        filters = repo.get_filters_for_subcategory(
            taxonomy.subcategory_with_filters.id
        )

        # The Tutoring subcategory should have seeded filters
        assert len(filters) >= 1
