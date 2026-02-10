# backend/tests/models/test_taxonomy_models.py
"""
Tests for the 3-level taxonomy models (Phase 1).

Validates ServiceSubcategory, FilterDefinition, FilterOption,
SubcategoryFilter, SubcategoryFilterOption models and the updated
ServiceCatalog/InstructorService fields.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
import ulid as _ulid

from app.models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from app.models.service_catalog import (
    InstructorService as Service,
    ServiceCatalog,
    ServiceCategory,
)
from app.models.subcategory import ServiceSubcategory

# ── Helpers ────────────────────────────────────────────────────


_uid_counter = 0


def _uid() -> str:
    """Short unique suffix for test data (counter ensures uniqueness within same ms)."""
    global _uid_counter
    _uid_counter += 1
    return f"{str(_ulid.ULID()).lower()[:8]}{_uid_counter:02d}"


def _make_category(db, *, name: str | None = None, **kw) -> ServiceCategory:
    name = name or f"TM Cat {_uid()}"
    cat = ServiceCategory(name=name, display_order=kw.get("display_order", 0))
    db.add(cat)
    db.flush()
    return cat


def _make_subcategory(db, category_id: str, *, name: str | None = None, **kw) -> ServiceSubcategory:
    name = name or f"TM Sub {_uid()}"
    sub = ServiceSubcategory(
        category_id=category_id,
        name=name,
        display_order=kw.get("display_order", 0),
    )
    db.add(sub)
    db.flush()
    return sub


def _make_service(db, subcategory_id: str, *, name: str | None = None, slug: str | None = None):
    name = name or f"TM Svc {_uid()}"
    slug = slug or f"tm-svc-{_uid()}"
    svc = ServiceCatalog(
        subcategory_id=subcategory_id,
        name=name,
        slug=slug,
        display_order=0,
        is_active=True,
    )
    db.add(svc)
    db.flush()
    return svc


def _make_filter_def(db, *, key: str | None = None, display_name: str = "Grade Level"):
    key = key or f"tm_fd_{_uid()}"
    fd = FilterDefinition(key=key, display_name=display_name, filter_type="multi_select")
    db.add(fd)
    db.flush()
    return fd


def _make_filter_option(db, fd_id: str, *, value: str | None = None, display_name: str = "Elementary"):
    value = value or f"opt_{_uid()}"
    fo = FilterOption(
        filter_definition_id=fd_id,
        value=value,
        display_name=display_name,
        display_order=0,
    )
    db.add(fo)
    db.flush()
    return fo


# ── 1A. ServiceSubcategory model ──────────────────────────────


class TestServiceSubcategoryModel:
    def test_create_subcategory(self, db):
        """Create a subcategory linked to a category."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id, name=f"Piano {_uid()}")
        db.commit()

        assert sub.id is not None
        assert len(sub.id) == 26  # ULID
        assert sub.category_id == cat.id

    def test_subcategory_category_relationship(self, db):
        """subcategory.category navigates to parent category."""
        cat = _make_category(db, name=f"Music {_uid()}")
        sub = _make_subcategory(db, cat.id)
        db.commit()
        db.refresh(sub)

        assert sub.category is not None
        assert sub.category.name == cat.name

    def test_subcategory_services_relationship(self, db):
        """subcategory.services returns child service_catalog entries."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        _make_service(db, sub.id)
        _make_service(db, sub.id)
        db.commit()
        db.refresh(sub)

        assert len(sub.services) == 2

    def test_subcategory_display_order_default(self, db):
        """display_order defaults to 0."""
        cat = _make_category(db)
        sub = ServiceSubcategory(category_id=cat.id, name=f"Default Order {_uid()}")
        db.add(sub)
        db.commit()
        db.refresh(sub)

        assert sub.display_order == 0

    def test_subcategory_requires_category_id(self, db):
        """Creating without category_id raises IntegrityError."""
        sub = ServiceSubcategory(name=f"Orphan {_uid()}")
        db.add(sub)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_subcategory_unique_name_per_category(self, db):
        """Duplicate name within same category raises IntegrityError."""
        cat = _make_category(db)
        unique_name = f"Piano {_uid()}"
        _make_subcategory(db, cat.id, name=unique_name)
        db.commit()

        dup = ServiceSubcategory(category_id=cat.id, name=unique_name)
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_subcategory_repr(self, db):
        """__repr__ includes name and category_id."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id, name=f"Guitar {_uid()}")
        assert "Guitar" in repr(sub)

    def test_subcategory_service_count_property(self, db):
        """service_count returns count of related services."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        _make_service(db, sub.id)
        _make_service(db, sub.id)
        db.commit()
        db.refresh(sub)

        assert sub.service_count == 2

    def test_subcategory_to_dict(self, db):
        """to_dict returns expected keys."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id, name=f"Voice {_uid()}")
        db.commit()
        db.refresh(sub)

        d = sub.to_dict()
        assert "Voice" in d["name"]
        assert d["category_id"] == cat.id
        assert "service_count" in d


# ── 1B. Filter models ─────────────────────────────────────────


class TestFilterDefinitionModel:
    def test_create_filter_definition(self, db):
        """Create a filter definition."""
        fd = _make_filter_def(db, display_name="Style")
        db.commit()

        assert fd.id is not None
        assert fd.key.startswith("tm_fd_")
        assert fd.display_name == "Style"
        assert fd.filter_type == "multi_select"

    def test_filter_definition_options_relationship(self, db):
        """filter_definition.options returns child FilterOption entries."""
        fd = _make_filter_def(db)
        _make_filter_option(db, fd.id, display_name="Elementary")
        _make_filter_option(db, fd.id, display_name="Middle School")
        db.commit()
        db.refresh(fd)

        assert len(fd.options) == 2

    def test_filter_definition_unique_key(self, db):
        """Duplicate key raises IntegrityError."""
        unique_key = f"uq_key_{_uid()}"
        _make_filter_def(db, key=unique_key)
        db.commit()

        dup = FilterDefinition(key=unique_key, display_name="Dup", filter_type="single_select")
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_filter_definition_to_dict(self, db):
        fd = _make_filter_def(db, display_name="Test")
        db.commit()
        d = fd.to_dict()
        assert d["key"].startswith("tm_fd_")
        assert d["filter_type"] == "multi_select"


class TestFilterOptionModel:
    def test_create_filter_option(self, db):
        """Create a filter option."""
        fd = _make_filter_def(db)
        fo = _make_filter_option(db, fd.id, value=f"honors_{_uid()}", display_name="Honors")
        db.commit()

        assert fo.id is not None
        assert fo.filter_definition_id == fd.id

    def test_filter_option_requires_definition_id(self, db):
        """Creating without filter_definition_id raises IntegrityError."""
        fo = FilterOption(value=f"orphan_{_uid()}", display_name="Orphan", display_order=0)
        db.add(fo)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_filter_option_unique_value_per_definition(self, db):
        """Duplicate value within same definition raises IntegrityError."""
        fd = _make_filter_def(db)
        dup_value = f"dup_{_uid()}"
        _make_filter_option(db, fd.id, value=dup_value, display_name="Dup1")
        db.commit()

        dup = FilterOption(filter_definition_id=fd.id, value=dup_value, display_name="Dup2", display_order=1)
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_filter_option_to_dict(self, db):
        fd = _make_filter_def(db)
        fo = _make_filter_option(db, fd.id, display_name="Elem")
        db.commit()
        d = fo.to_dict()
        assert "value" in d
        assert "display_order" in d


class TestSubcategoryFilterModel:
    def test_link_filter_to_subcategory(self, db):
        """SubcategoryFilter links a filter_definition to a subcategory."""
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

        assert sf.id is not None
        assert sf.subcategory_id == sub.id
        assert sf.filter_definition_id == fd.id

    def test_subcategory_filter_options(self, db):
        """SubcategoryFilterOption links specific options to a subcategory-filter pair."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd = _make_filter_def(db)
        fo1 = _make_filter_option(db, fd.id, display_name="Opt1")
        fo2 = _make_filter_option(db, fd.id, display_name="Opt2")

        sf = SubcategoryFilter(subcategory_id=sub.id, filter_definition_id=fd.id, display_order=0)
        db.add(sf)
        db.flush()

        sfo1 = SubcategoryFilterOption(subcategory_filter_id=sf.id, filter_option_id=fo1.id, display_order=0)
        sfo2 = SubcategoryFilterOption(subcategory_filter_id=sf.id, filter_option_id=fo2.id, display_order=1)
        db.add_all([sfo1, sfo2])
        db.commit()
        db.refresh(sf)

        assert len(sf.filter_options) == 2

    def test_subcategory_filter_unique_constraint(self, db):
        """Duplicate (subcategory_id, filter_definition_id) raises IntegrityError."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        fd = _make_filter_def(db)

        sf = SubcategoryFilter(subcategory_id=sub.id, filter_definition_id=fd.id, display_order=0)
        db.add(sf)
        db.commit()

        dup = SubcategoryFilter(subcategory_id=sub.id, filter_definition_id=fd.id, display_order=1)
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


# ── 1C. Updated service_catalog model ─────────────────────────


class TestServiceCatalogModelUpdates:
    def test_subcategory_id_field(self, db):
        """service_catalog has subcategory_id FK."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = _make_service(db, sub.id)
        db.commit()

        assert svc.subcategory_id == sub.id

    def test_eligible_age_groups_array(self, db):
        """eligible_age_groups stores TEXT[] correctly."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"Age Group {_uid()}",
            slug=f"age-group-{_uid()}",
            display_order=0,
            eligible_age_groups=["kids", "teens", "adults"],
        )
        db.add(svc)
        db.commit()
        db.refresh(svc)

        assert svc.eligible_age_groups == ["kids", "teens", "adults"]

    def test_eligible_age_groups_default(self, db):
        """eligible_age_groups defaults to kids, teens, adults (matching seed)."""
        cat = _make_category(db)
        sub = _make_subcategory(db, cat.id)
        svc = ServiceCatalog(
            subcategory_id=sub.id,
            name=f"Default Ages {_uid()}",
            slug=f"default-ages-{_uid()}",
            display_order=0,
        )
        db.add(svc)
        db.commit()
        db.refresh(svc)

        assert svc.eligible_age_groups == ["kids", "teens", "adults"]

    def test_service_subcategory_relationship(self, db):
        """service.subcategory navigates to parent subcategory."""
        cat = _make_category(db)
        sub_name = f"Piano {_uid()}"
        sub = _make_subcategory(db, cat.id, name=sub_name)
        svc = _make_service(db, sub.id)
        db.commit()
        db.refresh(svc)

        assert svc.subcategory is not None
        assert svc.subcategory.name == sub_name

    def test_service_category_property(self, db):
        """service.category @property traverses through subcategory."""
        cat_name = f"Music {_uid()}"
        cat = _make_category(db, name=cat_name)
        sub = _make_subcategory(db, cat.id)
        svc = _make_service(db, sub.id)
        db.commit()
        db.refresh(svc)

        assert svc.category is not None
        assert svc.category.name == cat_name

    def test_service_category_name_property(self, db):
        """service.category_name returns category name string."""
        cat_name = f"Cat Name {_uid()}"
        cat = _make_category(db, name=cat_name)
        sub = _make_subcategory(db, cat.id)
        svc = _make_service(db, sub.id)
        db.commit()
        db.refresh(svc)

        assert svc.category_name == cat_name


# ── 1D. Updated instructor_services model ─────────────────────


class TestInstructorServiceModelUpdates:
    def test_filter_selections_jsonb(self, db, test_instructor):
        """filter_selections stores JSONB correctly."""
        from app.models.instructor import InstructorProfile

        profile = db.query(InstructorProfile).filter(
            InstructorProfile.user_id == test_instructor.id
        ).first()
        assert profile is not None

        svc = db.query(Service).filter(
            Service.instructor_profile_id == profile.id
        ).first()
        if svc:
            svc.filter_selections = {"grade_level": ["elementary", "middle"]}
            db.commit()
            db.refresh(svc)
            assert svc.filter_selections == {"grade_level": ["elementary", "middle"]}

    def test_filter_selections_empty_dict(self, db, test_instructor):
        """filter_selections can be empty dict {}."""
        from app.models.instructor import InstructorProfile

        profile = db.query(InstructorProfile).filter(
            InstructorProfile.user_id == test_instructor.id
        ).first()
        svc = db.query(Service).filter(
            Service.instructor_profile_id == profile.id
        ).first()
        if svc:
            svc.filter_selections = {}
            db.commit()
            db.refresh(svc)
            assert svc.filter_selections == {}
