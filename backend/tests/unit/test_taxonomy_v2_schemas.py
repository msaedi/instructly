# backend/tests/unit/test_taxonomy_v2_schemas.py
"""
Unit tests for taxonomy v2 Pydantic schemas.

Tests serialization from ORM-like data, validation, nesting, and edge cases.
"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.schemas.service_catalog import (
    CatalogServiceResponse,
    CategoryResponse,
    ServiceCatalogDetail,
    ServiceCatalogSummary,
)
from app.schemas.subcategory import (
    CategoryDetail,
    CategorySummary,
    CategoryTreeResponse,
    CategoryWithSubcategories,
    SubcategoryBrief,
    SubcategoryDetail,
    SubcategorySummary,
    SubcategoryWithServices,
)
from app.schemas.taxonomy_filter import (
    FilterDefinitionWithOptions,
    FilterOptionResponse,
    FilterWithOptions,
    InstructorFilterContext,
    SubcategoryFilterResponse,
)


class TestCategoryResponse:
    """Tests for CategoryResponse schema."""

    def test_serialization(self) -> None:
        data = {
            "id": "01ABC",
            "name": "Music",
            "subtitle": "Instruments & Voice",
            "description": "All music lessons",
            "display_order": 1,
            "icon_name": "music",
        }
        schema = CategoryResponse(**data)
        assert schema.id == "01ABC"
        assert schema.name == "Music"
        assert schema.display_order == 1

    def test_optional_fields_accept_none(self) -> None:
        schema = CategoryResponse(
            id="01ABC",
            name="Music",
            display_order=0,
        )
        assert schema.subtitle is None
        assert schema.description is None
        assert schema.icon_name is None

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            CategoryResponse(
                id="01ABC",
                name="Music",
                display_order=0,
                bogus="field",
            )


class TestCategorySummary:
    """Tests for CategorySummary schema (Phase 3)."""

    def test_serialization(self) -> None:
        schema = CategorySummary(
            id="01ABC",
            name="Music",
            slug="music",
            description="All music lessons",
            subcategory_count=5,
        )
        assert schema.slug == "music"
        assert schema.subcategory_count == 5

    def test_defaults(self) -> None:
        schema = CategorySummary(id="01ABC", name="Music")
        assert schema.slug is None
        assert schema.description is None
        assert schema.subcategory_count == 0


class TestCategoryDetail:
    """Tests for CategoryDetail schema (Phase 3)."""

    def test_with_subcategories(self) -> None:
        schema = CategoryDetail(
            id="01ABC",
            name="Music",
            slug="music",
            meta_title="Music Lessons NYC",
            meta_description="Best music lessons",
            subcategories=[
                SubcategorySummary(
                    id="01SUB",
                    slug="piano",
                    name="Piano",
                    service_count=3,
                ),
            ],
        )
        assert len(schema.subcategories) == 1
        assert schema.subcategories[0].name == "Piano"
        assert schema.meta_title == "Music Lessons NYC"

    def test_empty_subcategories(self) -> None:
        schema = CategoryDetail(id="01ABC", name="Empty")
        assert schema.subcategories == []


class TestSubcategorySummary:
    """Tests for SubcategorySummary schema (Phase 3)."""

    def test_serialization(self) -> None:
        schema = SubcategorySummary(
            id="01SUB",
            slug="piano",
            name="Piano",
            description="Piano lessons for all ages",
            service_count=5,
        )
        assert schema.slug == "piano"
        assert schema.service_count == 5

    def test_defaults(self) -> None:
        schema = SubcategorySummary(id="01SUB", name="Guitar")
        assert schema.slug is None
        assert schema.description is None
        assert schema.service_count == 0


class TestSubcategoryDetail:
    """Tests for SubcategoryDetail schema (Phase 3)."""

    def test_with_services_and_filters(self) -> None:
        schema = SubcategoryDetail(
            id="01SUB",
            slug="math",
            name="Math",
            description="Math tutoring",
            meta_title="Math Tutoring NYC",
            meta_description="Best math tutors",
            category=CategoryResponse(
                id="01CAT", name="Tutoring", display_order=2
            ),
            services=[
                CatalogServiceResponse(
                    id="01SVC",
                    subcategory_id="01SUB",
                    name="Algebra",
                    category_name="Tutoring",
                ),
            ],
            filters=[
                SubcategoryFilterResponse(
                    filter_key="grade_level",
                    filter_display_name="Grade Level",
                    filter_type="multi_select",
                    options=[
                        FilterOptionResponse(
                            id="01OPT",
                            value="elementary",
                            display_name="Elementary (K-5)",
                        ),
                    ],
                ),
            ],
        )
        assert len(schema.services) == 1
        assert len(schema.filters) == 1
        assert schema.filters[0].filter_key == "grade_level"

    def test_empty_services_and_filters(self) -> None:
        schema = SubcategoryDetail(
            id="01SUB",
            name="Piano",
            category=CategoryResponse(
                id="01CAT", name="Music", display_order=1
            ),
        )
        assert schema.services == []
        assert schema.filters == []


class TestSubcategoryBrief:
    """Tests for SubcategoryBrief schema."""

    def test_serialization(self) -> None:
        schema = SubcategoryBrief(
            id="01SUB", name="Piano", service_count=3
        )
        assert schema.id == "01SUB"
        assert schema.name == "Piano"
        assert schema.service_count == 3

    def test_default_service_count(self) -> None:
        schema = SubcategoryBrief(id="01SUB", name="Guitar")
        assert schema.service_count == 0


class TestSubcategoryWithServices:
    """Tests for SubcategoryWithServices schema."""

    def test_nested_services(self) -> None:
        schema = SubcategoryWithServices(
            id="01SUB",
            category_id="01CAT",
            name="Piano",
            display_order=1,
            services=[
                CatalogServiceResponse(
                    id="01SVC",
                    subcategory_id="01SUB",
                    name="Classical Piano",
                ),
            ],
        )
        assert len(schema.services) == 1
        assert schema.services[0].name == "Classical Piano"


class TestCategoryWithSubcategories:
    """Tests for CategoryWithSubcategories schema."""

    def test_nested_subcategories(self) -> None:
        schema = CategoryWithSubcategories(
            id="01CAT",
            name="Music",
            display_order=1,
            subcategories=[
                SubcategoryBrief(
                    id="01SUB", name="Piano", service_count=3
                ),
                SubcategoryBrief(
                    id="02SUB", name="Guitar", service_count=2
                ),
            ],
        )
        assert len(schema.subcategories) == 2


class TestCategoryTreeResponse:
    """Tests for CategoryTreeResponse — full 3-level tree."""

    def test_full_tree(self) -> None:
        schema = CategoryTreeResponse(
            id="01CAT",
            name="Music",
            display_order=1,
            subcategories=[
                SubcategoryWithServices(
                    id="01SUB",
                    category_id="01CAT",
                    name="Piano",
                    display_order=1,
                    services=[
                        CatalogServiceResponse(
                            id="01SVC",
                            subcategory_id="01SUB",
                            name="Classical Piano",
                        ),
                    ],
                ),
            ],
        )
        assert len(schema.subcategories) == 1
        assert len(schema.subcategories[0].services) == 1


class TestServiceCatalogSummary:
    """Tests for ServiceCatalogSummary schema (Phase 3)."""

    def test_serialization(self) -> None:
        schema = ServiceCatalogSummary(
            id="01SVC",
            slug="piano-lessons",
            name="Piano Lessons",
            eligible_age_groups=["kids", "teens", "adults"],
            default_duration_minutes=60,
        )
        assert schema.slug == "piano-lessons"
        assert "kids" in schema.eligible_age_groups

    def test_defaults(self) -> None:
        schema = ServiceCatalogSummary(id="01SVC", name="Guitar")
        assert schema.slug is None
        assert schema.eligible_age_groups == []
        assert schema.default_duration_minutes == 60


class TestServiceCatalogDetail:
    """Tests for ServiceCatalogDetail schema (Phase 3)."""

    def test_inherits_summary_fields(self) -> None:
        schema = ServiceCatalogDetail(
            id="01SVC",
            name="Piano Lessons",
            description="Learn piano",
            price_floor_in_person_cents=5000,
            price_floor_online_cents=4000,
            subcategory_id="01SUB",
            subcategory_name="Piano",
        )
        assert schema.description == "Learn piano"
        assert schema.price_floor_in_person_cents == 5000
        assert schema.subcategory_name == "Piano"

    def test_optional_price_floors(self) -> None:
        schema = ServiceCatalogDetail(
            id="01SVC", name="Voice", subcategory_id="01SUB"
        )
        assert schema.price_floor_in_person_cents is None
        assert schema.price_floor_online_cents is None


class TestFilterOptionResponse:
    """Tests for FilterOptionResponse schema."""

    def test_serialization(self) -> None:
        schema = FilterOptionResponse(
            id="01OPT",
            value="elementary",
            display_name="Elementary (K-5)",
            display_order=1,
        )
        assert schema.value == "elementary"
        assert schema.display_name == "Elementary (K-5)"

    def test_default_display_order(self) -> None:
        schema = FilterOptionResponse(
            id="01OPT", value="honors", display_name="Honors"
        )
        assert schema.display_order == 0


class TestSubcategoryFilterResponse:
    """Tests for SubcategoryFilterResponse schema."""

    def test_with_options(self) -> None:
        schema = SubcategoryFilterResponse(
            filter_key="grade_level",
            filter_display_name="Grade Level",
            filter_type="multi_select",
            options=[
                FilterOptionResponse(
                    id="01", value="elementary", display_name="Elementary"
                ),
                FilterOptionResponse(
                    id="02", value="middle", display_name="Middle School"
                ),
            ],
        )
        assert len(schema.options) == 2
        assert schema.filter_type == "multi_select"


class TestFilterWithOptions:
    """Tests for FilterWithOptions schema (Phase 3)."""

    def test_with_is_required(self) -> None:
        schema = FilterWithOptions(
            id="01FD",
            key="grade_level",
            display_name="Grade Level",
            filter_type="multi_select",
            is_required=True,
            options=[
                FilterOptionResponse(
                    id="01", value="elementary", display_name="Elementary"
                ),
            ],
        )
        assert schema.is_required is True
        assert schema.key == "grade_level"

    def test_is_required_defaults_false(self) -> None:
        schema = FilterWithOptions(
            id="01FD",
            key="style",
            display_name="Style",
            filter_type="single_select",
        )
        assert schema.is_required is False
        assert schema.options == []


class TestFilterDefinitionWithOptions:
    """Tests for FilterDefinitionWithOptions schema."""

    def test_nesting(self) -> None:
        schema = FilterDefinitionWithOptions(
            id="01FD",
            key="goal",
            display_name="Learning Goal",
            filter_type="multi_select",
            options=[
                FilterOptionResponse(
                    id="01", value="enrichment", display_name="Enrichment"
                ),
            ],
        )
        assert len(schema.options) == 1


class TestInstructorFilterContext:
    """Tests for InstructorFilterContext schema."""

    def test_with_selections(self) -> None:
        schema = InstructorFilterContext(
            available_filters=[
                SubcategoryFilterResponse(
                    filter_key="grade_level",
                    filter_display_name="Grade Level",
                    filter_type="multi_select",
                ),
            ],
            current_selections={
                "grade_level": ["elementary", "middle_school"],
            },
        )
        assert len(schema.available_filters) == 1
        assert "grade_level" in schema.current_selections

    def test_empty_defaults(self) -> None:
        schema = InstructorFilterContext()
        assert schema.available_filters == []
        assert schema.current_selections == {}
