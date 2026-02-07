# backend/tests/integration/test_taxonomy_v2_migration.py
"""
Integration tests for taxonomy v2 migration schema contract.

Validates that all 6 new/modified tables have the correct columns,
constraints, indexes, and FK relationships per the spec.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
import ulid as _ulid

from app.models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory

# ── Helpers ────────────────────────────────────────────────────

_uid_counter = 0


def _uid() -> str:
    global _uid_counter
    _uid_counter += 1
    return f"{str(_ulid.ULID()).lower()[:8]}{_uid_counter:02d}"


def _make_category(db, **kw) -> ServiceCategory:
    cat = ServiceCategory(
        name=kw.get("name", f"MigCat {_uid()}"),
        display_order=kw.get("display_order", 0),
    )
    db.add(cat)
    db.flush()
    return cat


def _make_subcategory(db, category_id: str, **kw) -> ServiceSubcategory:
    sub = ServiceSubcategory(
        category_id=category_id,
        name=kw.get("name", f"MigSub {_uid()}"),
        display_order=kw.get("display_order", 0),
    )
    db.add(sub)
    db.flush()
    return sub


def _make_service(db, subcategory_id: str, **kw) -> ServiceCatalog:
    svc = ServiceCatalog(
        subcategory_id=subcategory_id,
        name=kw.get("name", f"MigSvc {_uid()}"),
        slug=kw.get("slug", f"mig-svc-{_uid()}"),
        display_order=kw.get("display_order", 0),
    )
    db.add(svc)
    db.flush()
    return svc


def _make_filter_def(db, **kw) -> FilterDefinition:
    fd = FilterDefinition(
        key=kw.get("key", f"mig_fd_{_uid()}"),
        display_name=kw.get("display_name", "Grade Level"),
        filter_type=kw.get("filter_type", "multi_select"),
    )
    db.add(fd)
    db.flush()
    return fd


def _make_filter_option(db, fd_id: str, **kw) -> FilterOption:
    fo = FilterOption(
        filter_definition_id=fd_id,
        value=kw.get("value", f"opt_{_uid()}"),
        display_name=kw.get("display_name", "Elementary"),
        display_order=kw.get("display_order", 0),
    )
    db.add(fo)
    db.flush()
    return fo


# ── 1. Tables exist ───────────────────────────────────────────


class TestTablesExist:
    """Verify all 6 new tables + 3 modified tables exist."""

    @pytest.mark.parametrize(
        "table_name",
        [
            "service_subcategories",
            "service_catalog",
            "filter_definitions",
            "filter_options",
            "subcategory_filters",
            "subcategory_filter_options",
        ],
    )
    def test_new_table_exists(self, db, table_name):
        inspector = inspect(db.bind)
        assert table_name in inspector.get_table_names()


# ── 2. Column types on new tables ─────────────────────────────


class TestSubcategoryColumns:
    """Verify service_subcategories has all expected columns."""

    def test_has_slug_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_subcategories")}
        assert "slug" in cols

    def test_has_description_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_subcategories")}
        assert "description" in cols

    def test_has_is_active_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_subcategories")}
        assert "is_active" in cols

    def test_has_meta_title_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_subcategories")}
        assert "meta_title" in cols

    def test_has_meta_description_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_subcategories")}
        assert "meta_description" in cols

    def test_is_active_defaults_true(self, db):
        cat = _make_category(db)
        sub = ServiceSubcategory(
            category_id=cat.id, name=f"ActiveDefault {_uid()}"
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        assert sub.is_active is True


class TestCatalogColumns:
    """Verify service_catalog has all expected columns."""

    def test_has_default_duration_minutes(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_catalog")}
        assert "default_duration_minutes" in cols

    def test_has_price_floor_in_person_cents(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_catalog")}
        assert "price_floor_in_person_cents" in cols

    def test_has_price_floor_online_cents(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_catalog")}
        assert "price_floor_online_cents" in cols

    def test_default_duration_defaults_to_60(self, db):
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = _make_service(db, sub.id)
        db.commit()
        db.refresh(svc)
        assert svc.default_duration_minutes == 60

    def test_slug_is_nullable(self, db):
        """service_catalog.slug can be NULL."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"NoSlug {_uid()}",
            slug=None,
            display_order=0,
        )
        db.add(svc)
        db.commit()
        db.refresh(svc)
        assert svc.slug is None


class TestFilterDefinitionColumns:
    """Verify filter_definitions has all expected columns."""

    def test_has_description_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("filter_definitions")}
        assert "description" in cols

    def test_has_display_order_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("filter_definitions")}
        assert "display_order" in cols

    def test_has_is_active_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("filter_definitions")}
        assert "is_active" in cols

    def test_has_updated_at_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("filter_definitions")}
        assert "updated_at" in cols


class TestFilterOptionColumns:
    def test_has_is_active_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("filter_options")}
        assert "is_active" in cols


class TestSubcategoryFilterColumns:
    def test_has_is_required_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("subcategory_filters")}
        assert "is_required" in cols

    def test_has_created_at_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("subcategory_filters")}
        assert "created_at" in cols


class TestSubcategoryFilterOptionColumns:
    def test_has_created_at_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("subcategory_filter_options")}
        assert "created_at" in cols


# ── 3. FK relationships work ──────────────────────────────────


class TestForeignKeyRelationships:
    def test_subcategory_to_category(self, db):
        """Insert parent → insert child succeeds."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        db.commit()
        assert sub.category_id == cat.id

    def test_catalog_to_subcategory(self, db):
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = _make_service(db, sub.id)
        db.commit()
        assert svc.subcategory_id == sub.id

    def test_filter_option_to_definition(self, db):
        fd = _make_filter_def(db)
        fo = _make_filter_option(db, fd.id)
        db.commit()
        assert fo.filter_definition_id == fd.id

    def test_subcategory_filter_links(self, db):
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd = _make_filter_def(db)
        sf = SubcategoryFilter(
            subcategory_id=sub.id,
            filter_definition_id=fd.id,
            display_order=0,
        )
        db.add(sf)
        db.commit()
        assert sf.subcategory_id == sub.id
        assert sf.filter_definition_id == fd.id

    def test_subcategory_filter_option_links(self, db):
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd = _make_filter_def(db)
        fo = _make_filter_option(db, fd.id)
        sf = SubcategoryFilter(
            subcategory_id=sub.id,
            filter_definition_id=fd.id,
            display_order=0,
        )
        db.add(sf)
        db.flush()
        sfo = SubcategoryFilterOption(
            subcategory_filter_id=sf.id,
            filter_option_id=fo.id,
            display_order=0,
        )
        db.add(sfo)
        db.commit()
        assert sfo.subcategory_filter_id == sf.id
        assert sfo.filter_option_id == fo.id


# ── 4. FK CASCADE ─────────────────────────────────────────────


class TestFKCascade:
    def test_delete_subcategory_cascades_to_catalog(self, db):
        """Deleting a subcategory cascades to service_catalog via DB FK."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = _make_service(db, sub.id)
        svc_id = svc.id
        sub_id = sub.id
        db.commit()

        # Use raw SQL to trigger DB-level cascade (ORM tries to null FK)
        db.execute(text("DELETE FROM service_subcategories WHERE id = :id"), {"id": sub_id})
        db.commit()
        db.expire_all()

        assert db.get(ServiceCatalog, svc_id) is None

    def test_delete_subcategory_cascades_to_filters(self, db):
        """Deleting a subcategory cascades to subcategory_filters via DB FK."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd = _make_filter_def(db)
        sf = SubcategoryFilter(
            subcategory_id=sub.id,
            filter_definition_id=fd.id,
            display_order=0,
        )
        db.add(sf)
        db.flush()
        sf_id = sf.id
        sub_id = sub.id
        db.commit()

        db.execute(text("DELETE FROM service_subcategories WHERE id = :id"), {"id": sub_id})
        db.commit()
        db.expire_all()

        result = db.execute(
            text("SELECT id FROM subcategory_filters WHERE id = :id"), {"id": sf_id}
        )
        assert result.fetchone() is None

    def test_delete_filter_definition_cascades_to_options(self, db):
        """Deleting a filter_definition cascades to filter_options."""
        fd = _make_filter_def(db)
        fo = _make_filter_option(db, fd.id)
        fo_id = fo.id
        db.commit()

        db.delete(fd)
        db.commit()

        assert db.get(FilterOption, fo_id) is None


# ── 5. UNIQUE constraints ─────────────────────────────────────


class TestUniqueConstraints:
    def test_duplicate_slug_on_subcategory_rejected(self, db):
        """Non-NULL duplicate slugs on service_subcategories are rejected."""
        cat = _make_category(db)
        slug = f"unique-sub-{_uid()}"
        sub1 = ServiceSubcategory(
            category_id=cat.id,
            name=f"Sub1 {_uid()}",
            slug=slug,
        )
        db.add(sub1)
        db.commit()

        sub2 = ServiceSubcategory(
            category_id=cat.id,
            name=f"Sub2 {_uid()}",
            slug=slug,
        )
        db.add(sub2)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_duplicate_slug_on_catalog_rejected(self, db):
        """Non-NULL duplicate slugs on service_catalog are rejected."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        slug = f"unique-svc-{_uid()}"
        _make_service(db, sub.id, slug=slug)
        db.commit()

        svc2 = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"Dup {_uid()}",
            slug=slug,
            display_order=0,
        )
        db.add(svc2)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_duplicate_filter_mapping_rejected(self, db):
        """Duplicate (subcategory_id, filter_definition_id) is rejected."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd = _make_filter_def(db)

        sf1 = SubcategoryFilter(
            subcategory_id=sub.id,
            filter_definition_id=fd.id,
            display_order=0,
        )
        db.add(sf1)
        db.commit()

        sf2 = SubcategoryFilter(
            subcategory_id=sub.id,
            filter_definition_id=fd.id,
            display_order=1,
        )
        db.add(sf2)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


# ── 6. GIN index on filter_selections ─────────────────────────


class TestGINIndex:
    def test_filter_selections_gin_containment_query(self, db):
        """GIN index on instructor_services.filter_selections supports @> queries."""
        result = db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'instructor_services' "
                "AND indexdef LIKE '%gin%' "
                "AND indexname LIKE '%filter_selections%'"
            )
        )
        rows = result.fetchall()
        assert len(rows) >= 1, "GIN index on filter_selections not found"


# ── 7. eligible_age_groups TEXT[] ──────────────────────────────


class TestEligibleAgeGroups:
    def test_accepts_valid_values(self, db):
        """eligible_age_groups accepts toddler, kids, teens, adults."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"AllAges {_uid()}",
            slug=f"all-ages-{_uid()}",
            display_order=0,
            eligible_age_groups=["toddler", "kids", "teens", "adults"],
        )
        db.add(svc)
        db.commit()
        db.refresh(svc)
        assert set(svc.eligible_age_groups) == {"toddler", "kids", "teens", "adults"}

    def test_default_includes_adults(self, db):
        """Default eligible_age_groups includes 'adults'."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"DefAge {_uid()}",
            slug=f"def-age-{_uid()}",
            display_order=0,
        )
        db.add(svc)
        db.commit()
        db.refresh(svc)
        assert "adults" in svc.eligible_age_groups


# ── 8. CHECK constraint on duration ───────────────────────────


class TestCheckConstraints:
    def test_duration_below_min_rejected(self, db):
        """default_duration_minutes < 15 is rejected by CHECK."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO service_catalog "
                    "(id, subcategory_id, name, display_order, default_duration_minutes, is_active) "
                    "VALUES (:id, :sub_id, :name, 0, 10, true)"
                ),
                {
                    "id": str(_ulid.ULID()),
                    "sub_id": sub.id,
                    "name": f"BadDuration {_uid()}",
                },
            )
        db.rollback()

    def test_duration_above_max_rejected(self, db):
        """default_duration_minutes > 480 is rejected by CHECK."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO service_catalog "
                    "(id, subcategory_id, name, display_order, default_duration_minutes, is_active) "
                    "VALUES (:id, :sub_id, :name, 0, 500, true)"
                ),
                {
                    "id": str(_ulid.ULID()),
                    "sub_id": sub.id,
                    "name": f"BadDuration {_uid()}",
                },
            )
        db.rollback()

    def test_valid_duration_accepted(self, db):
        """default_duration_minutes = 60 is accepted."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"GoodDuration {_uid()}",
            slug=f"good-dur-{_uid()}",
            display_order=0,
            default_duration_minutes=60,
        )
        db.add(svc)
        db.commit()
        db.refresh(svc)
        assert svc.default_duration_minutes == 60


# ── 9. filter_type CHECK constraint ───────────────────────────


class TestFilterTypeCheck:
    def test_invalid_filter_type_rejected(self, db):
        """filter_type not in ('single_select', 'multi_select') is rejected."""
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO filter_definitions (id, key, display_name, filter_type) "
                    "VALUES (:id, :key, 'Bad Type', 'invalid')"
                ),
                {"id": str(_ulid.ULID()), "key": f"bad_type_{_uid()}"},
            )
        db.rollback()

    def test_single_select_accepted(self, db):
        fd = FilterDefinition(
            key=f"ss_{_uid()}",
            display_name="Single Select",
            filter_type="single_select",
        )
        db.add(fd)
        db.commit()
        assert fd.filter_type == "single_select"


# ── 10. Partial unique indexes (NULL slugs don't conflict) ────


class TestPartialUniqueIndexes:
    def test_null_slugs_dont_conflict_on_subcategory(self, db):
        """Multiple NULL slugs are allowed on service_subcategories."""
        cat = _make_category(db)
        sub1 = ServiceSubcategory(
            category_id=cat.id,
            name=f"NullSlug1 {_uid()}",
            slug=None,
        )
        sub2 = ServiceSubcategory(
            category_id=cat.id,
            name=f"NullSlug2 {_uid()}",
            slug=None,
        )
        db.add_all([sub1, sub2])
        db.commit()
        assert sub1.slug is None
        assert sub2.slug is None

    def test_null_slugs_dont_conflict_on_catalog(self, db):
        """Multiple NULL slugs are allowed on service_catalog."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc1 = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"NullSlug1 {_uid()}",
            slug=None,
            display_order=0,
        )
        svc2 = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"NullSlug2 {_uid()}",
            slug=None,
            display_order=1,
        )
        db.add_all([svc1, svc2])
        db.commit()
        assert svc1.slug is None
        assert svc2.slug is None


# ── 11. New columns on service_categories ─────────────────────


class TestServiceCategoriesNewColumns:
    def test_has_slug_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_categories")}
        assert "slug" in cols

    def test_has_meta_title_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_categories")}
        assert "meta_title" in cols

    def test_has_meta_description_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("service_categories")}
        assert "meta_description" in cols

    def test_slug_roundtrip(self, db):
        cat = ServiceCategory(
            name=f"Slugged {_uid()}",
            slug=f"slugged-{_uid()}",
            display_order=0,
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)
        assert cat.slug is not None
        assert cat.slug.startswith("slugged-")


# ── 12. New columns on instructor_services ────────────────────


class TestInstructorServicesNewColumns:
    def test_has_filter_selections(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("instructor_services")}
        assert "filter_selections" in cols

    def test_has_service_catalog_id(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("instructor_services")}
        assert "service_catalog_id" in cols


# ── 13. New column on instructor_profiles ─────────────────────


class TestInstructorProfilesNewColumn:
    def test_has_slug_column(self, db):
        inspector = inspect(db.bind)
        cols = {c["name"] for c in inspector.get_columns("instructor_profiles")}
        assert "slug" in cols
