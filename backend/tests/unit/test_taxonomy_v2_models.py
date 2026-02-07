# backend/tests/unit/test_taxonomy_v2_models.py
"""
Unit tests for taxonomy v2 SQLAlchemy models.

Tests model instantiation, relationships, repr, and column configuration.

Note: Column `default=` values are only applied on DB INSERT (flush), not on
Python instantiation. Default tests check column metadata instead.
"""

from __future__ import annotations

from app.models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from app.models.service_catalog import (
    InstructorService,
    ServiceCatalog,
    ServiceCategory,
)
from app.models.subcategory import ServiceSubcategory


class TestServiceCategoryModel:
    """Tests for ServiceCategory model."""

    def test_instantiation_with_required_fields(self) -> None:
        cat = ServiceCategory(name="Music", display_order=1)
        assert cat.name == "Music"
        assert cat.display_order == 1

    def test_nullable_fields_accept_none(self) -> None:
        cat = ServiceCategory(name="Dance")
        assert cat.subtitle is None
        assert cat.description is None
        assert cat.icon_name is None
        assert cat.slug is None
        assert cat.meta_title is None
        assert cat.meta_description is None

    def test_column_default_display_order(self) -> None:
        """Verify display_order has default=0 in column definition."""
        col = ServiceCategory.__table__.c.display_order
        assert col.default is not None
        assert col.default.arg == 0

    def test_repr(self) -> None:
        cat = ServiceCategory(name="Music", id="01TEST")
        result = repr(cat)
        assert "ServiceCategory" in result
        assert "Music" in result

    def test_has_subcategories_relationship(self) -> None:
        assert hasattr(ServiceCategory, "subcategories")

    def test_tablename(self) -> None:
        assert ServiceCategory.__tablename__ == "service_categories"


class TestServiceSubcategoryModel:
    """Tests for ServiceSubcategory model."""

    def test_instantiation_with_required_fields(self) -> None:
        sub = ServiceSubcategory(category_id="01CATID", name="Piano")
        assert sub.name == "Piano"
        assert sub.category_id == "01CATID"

    def test_nullable_fields(self) -> None:
        sub = ServiceSubcategory(category_id="01CATID", name="Guitar")
        assert sub.slug is None
        assert sub.description is None
        assert sub.meta_title is None
        assert sub.meta_description is None

    def test_column_defaults(self) -> None:
        """Verify column defaults in metadata."""
        table = ServiceSubcategory.__table__
        assert table.c.display_order.default.arg == 0
        assert table.c.is_active.default.arg is True

    def test_repr(self) -> None:
        sub = ServiceSubcategory(category_id="01CATID", name="Piano")
        result = repr(sub)
        assert "ServiceSubcategory" in result
        assert "Piano" in result

    def test_has_relationships(self) -> None:
        assert hasattr(ServiceSubcategory, "category")
        assert hasattr(ServiceSubcategory, "services")
        assert hasattr(ServiceSubcategory, "subcategory_filters")

    def test_tablename(self) -> None:
        assert ServiceSubcategory.__tablename__ == "service_subcategories"

    def test_service_count_property_no_services(self) -> None:
        sub = ServiceSubcategory(category_id="01CATID", name="Drums")
        assert sub.service_count == 0


class TestServiceCatalogModel:
    """Tests for ServiceCatalog model."""

    def test_instantiation_with_required_fields(self) -> None:
        svc = ServiceCatalog(
            subcategory_id="01SUBID", name="Piano Lessons"
        )
        assert svc.name == "Piano Lessons"
        assert svc.subcategory_id == "01SUBID"

    def test_column_defaults(self) -> None:
        """Verify column defaults in metadata."""
        table = ServiceCatalog.__table__
        assert table.c.default_duration_minutes.default.arg == 60
        assert table.c.display_order.default.arg == 999
        assert table.c.online_capable.default.arg is True
        assert table.c.requires_certification.default.arg is False
        assert table.c.is_active.default.arg is True

    def test_nullable_fields(self) -> None:
        svc = ServiceCatalog(
            subcategory_id="01SUBID", name="Guitar Lessons"
        )
        assert svc.slug is None
        assert svc.description is None

    def test_explicit_age_groups(self) -> None:
        svc = ServiceCatalog(
            subcategory_id="01SUBID",
            name="Voice",
            eligible_age_groups=["toddler", "kids", "teens", "adults"],
        )
        assert "kids" in svc.eligible_age_groups

    def test_repr(self) -> None:
        svc = ServiceCatalog(
            subcategory_id="01SUBID", name="Piano Lessons", is_active=True
        )
        result = repr(svc)
        assert "ServiceCatalog" in result
        assert "Piano Lessons" in result

    def test_repr_inactive(self) -> None:
        svc = ServiceCatalog(
            subcategory_id="01SUBID", name="Archived", is_active=False
        )
        result = repr(svc)
        assert "(inactive)" in result

    def test_category_property_no_subcategory(self) -> None:
        svc = ServiceCatalog(subcategory_id="01SUBID", name="Orphan")
        assert svc.category is None

    def test_has_relationships(self) -> None:
        assert hasattr(ServiceCatalog, "subcategory")
        assert hasattr(ServiceCatalog, "instructor_services")

    def test_tablename(self) -> None:
        assert ServiceCatalog.__tablename__ == "service_catalog"


class TestFilterDefinitionModel:
    """Tests for FilterDefinition model."""

    def test_instantiation(self) -> None:
        fd = FilterDefinition(
            key="grade_level",
            display_name="Grade Level",
            filter_type="multi_select",
        )
        assert fd.key == "grade_level"
        assert fd.display_name == "Grade Level"
        assert fd.filter_type == "multi_select"

    def test_column_defaults(self) -> None:
        table = FilterDefinition.__table__
        assert table.c.filter_type.default.arg == "multi_select"
        assert table.c.display_order.default.arg == 0
        assert table.c.is_active.default.arg is True

    def test_nullable_fields(self) -> None:
        fd = FilterDefinition(key="style", display_name="Style")
        assert fd.description is None

    def test_repr(self) -> None:
        fd = FilterDefinition(
            key="grade_level",
            display_name="Grade Level",
            filter_type="multi_select",
        )
        result = repr(fd)
        assert "FilterDefinition" in result
        assert "grade_level" in result

    def test_has_options_relationship(self) -> None:
        assert hasattr(FilterDefinition, "options")

    def test_tablename(self) -> None:
        assert FilterDefinition.__tablename__ == "filter_definitions"


class TestFilterOptionModel:
    """Tests for FilterOption model."""

    def test_instantiation(self) -> None:
        fo = FilterOption(
            filter_definition_id="01FDID",
            value="elementary",
            display_name="Elementary (K-5)",
        )
        assert fo.value == "elementary"
        assert fo.display_name == "Elementary (K-5)"

    def test_column_defaults(self) -> None:
        table = FilterOption.__table__
        assert table.c.display_order.default.arg == 0
        assert table.c.is_active.default.arg is True

    def test_repr(self) -> None:
        fo = FilterOption(
            filter_definition_id="01FDID",
            value="elementary",
            display_name="Elementary (K-5)",
        )
        result = repr(fo)
        assert "FilterOption" in result
        assert "elementary" in result

    def test_has_filter_definition_relationship(self) -> None:
        assert hasattr(FilterOption, "filter_definition")

    def test_tablename(self) -> None:
        assert FilterOption.__tablename__ == "filter_options"


class TestSubcategoryFilterModel:
    """Tests for SubcategoryFilter model."""

    def test_instantiation(self) -> None:
        sf = SubcategoryFilter(
            subcategory_id="01SUBID",
            filter_definition_id="01FDID",
            display_order=0,
        )
        assert sf.subcategory_id == "01SUBID"
        assert sf.filter_definition_id == "01FDID"

    def test_column_defaults(self) -> None:
        table = SubcategoryFilter.__table__
        assert table.c.display_order.default.arg == 0
        assert table.c.is_required.default.arg is False

    def test_repr(self) -> None:
        sf = SubcategoryFilter(
            subcategory_id="01SUBID",
            filter_definition_id="01FDID",
        )
        result = repr(sf)
        assert "SubcategoryFilter" in result

    def test_has_relationships(self) -> None:
        assert hasattr(SubcategoryFilter, "subcategory")
        assert hasattr(SubcategoryFilter, "filter_definition")
        assert hasattr(SubcategoryFilter, "filter_options")

    def test_tablename(self) -> None:
        assert SubcategoryFilter.__tablename__ == "subcategory_filters"


class TestSubcategoryFilterOptionModel:
    """Tests for SubcategoryFilterOption model."""

    def test_instantiation(self) -> None:
        sfo = SubcategoryFilterOption(
            subcategory_filter_id="01SFID",
            filter_option_id="01FOID",
            display_order=0,
        )
        assert sfo.subcategory_filter_id == "01SFID"
        assert sfo.filter_option_id == "01FOID"

    def test_column_default(self) -> None:
        table = SubcategoryFilterOption.__table__
        assert table.c.display_order.default.arg == 0

    def test_repr(self) -> None:
        sfo = SubcategoryFilterOption(
            subcategory_filter_id="01SFID",
            filter_option_id="01FOID",
        )
        result = repr(sfo)
        assert "SubcategoryFilterOption" in result

    def test_has_relationships(self) -> None:
        assert hasattr(SubcategoryFilterOption, "subcategory_filter")
        assert hasattr(SubcategoryFilterOption, "filter_option")

    def test_tablename(self) -> None:
        assert SubcategoryFilterOption.__tablename__ == "subcategory_filter_options"


class TestInstructorServiceModel:
    """Tests for InstructorService taxonomy-related fields."""

    def test_filter_selections_column_exists(self) -> None:
        """filter_selections JSONB column has server_default '{}'."""
        table = InstructorService.__table__
        col = table.c.filter_selections
        assert col is not None
        assert col.server_default is not None

    def test_explicit_filter_selections(self) -> None:
        svc = InstructorService(
            instructor_profile_id="01IPID",
            service_catalog_id="01SCID",
            hourly_rate=75.00,
            filter_selections={"grade_level": ["elementary"]},
        )
        assert svc.filter_selections == {"grade_level": ["elementary"]}

    def test_has_catalog_entry_relationship(self) -> None:
        assert hasattr(InstructorService, "catalog_entry")

    def test_tablename(self) -> None:
        assert InstructorService.__tablename__ == "instructor_services"
