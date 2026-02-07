# backend/tests/unit/schemas/test_taxonomy_schemas.py
"""
Unit tests for taxonomy Pydantic schemas (Phase 3).

Tests validation, serialization, required/optional fields for subcategory
and taxonomy filter schemas.
"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.schemas.service_catalog import CategoryResponse
from app.schemas.service_catalog_responses import (
    CategoryServiceDetail,
    CategoryWithServices,
    TopCategoryItem,
)
from app.schemas.subcategory import (
    CategoryTreeResponse,
    CategoryWithSubcategories,
    SubcategoryBase,
    SubcategoryBrief,
    SubcategoryCreate,
    SubcategoryResponse,
    SubcategoryWithServices,
)
from app.schemas.taxonomy_filter import (
    FilterDefinitionResponse,
    FilterDefinitionWithOptions,
    FilterOptionResponse,
    InstructorFilterContext,
    SubcategoryFilterResponse,
)

_ULID = "01JAAAAAAAAAAAAAAAAAAAAAAА"  # 26-char test ID
_ULID2 = "01JBBBBBBBBBBBBBBBBBBBBBBB"


# ── 2A. Subcategory schemas ───────────────────────────────────


class TestSubcategorySchemas:
    def test_subcategory_base_valid(self):
        """SubcategoryBase accepts name + display_order."""
        s = SubcategoryBase(name="Piano", display_order=1)
        assert s.name == "Piano"
        assert s.display_order == 1

    def test_subcategory_base_default_display_order(self):
        """SubcategoryBase defaults display_order to 0."""
        s = SubcategoryBase(name="Guitar")
        assert s.display_order == 0

    def test_subcategory_create_requires_category_id(self):
        """SubcategoryCreate requires category_id string."""
        s = SubcategoryCreate(name="Piano", display_order=1, category_id=_ULID)
        assert s.category_id == _ULID

    def test_subcategory_create_rejects_missing_category_id(self):
        """SubcategoryCreate without category_id raises ValidationError."""
        with pytest.raises(ValidationError):
            SubcategoryCreate(name="Piano")

    def test_subcategory_response_serialization(self):
        """SubcategoryResponse includes id, category_id, name, display_order."""
        s = SubcategoryResponse(id=_ULID, category_id=_ULID2, name="Voice", display_order=3)
        assert s.id == _ULID
        assert s.category_id == _ULID2
        assert s.name == "Voice"

    def test_subcategory_brief_has_service_count(self):
        """SubcategoryBrief includes service_count field."""
        s = SubcategoryBrief(id=_ULID, name="Piano", service_count=5)
        assert s.service_count == 5

    def test_subcategory_brief_default_service_count(self):
        """SubcategoryBrief defaults service_count to 0."""
        s = SubcategoryBrief(id=_ULID, name="Piano")
        assert s.service_count == 0

    def test_subcategory_with_services_nested(self):
        """SubcategoryWithServices nests CatalogServiceResponse list."""
        s = SubcategoryWithServices(
            id=_ULID,
            category_id=_ULID2,
            name="Piano",
            display_order=1,
            services=[],
        )
        assert s.services == []

    def test_category_with_subcategories(self):
        """CategoryWithSubcategories nests SubcategoryBrief list."""
        c = CategoryWithSubcategories(
            id=_ULID,
            name="Music",
            display_order=1,
            subcategories=[
                SubcategoryBrief(id=_ULID2, name="Piano", service_count=3),
            ],
        )
        assert len(c.subcategories) == 1
        assert c.subcategories[0].name == "Piano"

    def test_category_tree_response(self):
        """CategoryTreeResponse nests SubcategoryWithServices."""
        t = CategoryTreeResponse(
            id=_ULID,
            name="Music",
            display_order=1,
            subcategories=[
                SubcategoryWithServices(
                    id=_ULID2, category_id=_ULID, name="Piano", display_order=1, services=[]
                ),
            ],
        )
        assert len(t.subcategories) == 1

    def test_subcategory_create_rejects_extra_fields(self):
        """SubcategoryCreate forbids extra fields."""
        with pytest.raises(ValidationError):
            SubcategoryCreate(name="Piano", category_id=_ULID, bogus="extra")

    def test_subcategory_name_max_length(self):
        """SubcategoryBase enforces max_length=255 on name."""
        with pytest.raises(ValidationError):
            SubcategoryCreate(name="x" * 256, category_id=_ULID)


# ── 2B. Filter schemas ────────────────────────────────────────


class TestTaxonomyFilterSchemas:
    def test_filter_option_response(self):
        """FilterOptionResponse has id, value, display_name, display_order."""
        o = FilterOptionResponse(
            id=_ULID, value="elementary", display_name="Elementary (K-5)", display_order=0
        )
        assert o.value == "elementary"
        assert o.display_name == "Elementary (K-5)"

    def test_filter_definition_response(self):
        """FilterDefinitionResponse has id, key, display_name, filter_type."""
        d = FilterDefinitionResponse(
            id=_ULID, key="grade_level", display_name="Grade Level", filter_type="multi_select"
        )
        assert d.key == "grade_level"
        assert d.filter_type == "multi_select"

    def test_filter_definition_with_options(self):
        """FilterDefinitionWithOptions nests FilterOptionResponse list."""
        d = FilterDefinitionWithOptions(
            id=_ULID,
            key="grade_level",
            display_name="Grade Level",
            filter_type="multi_select",
            options=[
                FilterOptionResponse(
                    id=_ULID2, value="elementary", display_name="Elementary", display_order=0
                ),
            ],
        )
        assert len(d.options) == 1

    def test_subcategory_filter_response(self):
        """SubcategoryFilterResponse has filter_key, filter_display_name, filter_type, options."""
        s = SubcategoryFilterResponse(
            filter_key="grade_level",
            filter_display_name="Grade Level",
            filter_type="multi_select",
            options=[
                FilterOptionResponse(
                    id=_ULID, value="elementary", display_name="Elementary", display_order=0
                ),
            ],
        )
        assert s.filter_key == "grade_level"
        assert len(s.options) == 1

    def test_instructor_filter_context(self):
        """InstructorFilterContext has available_filters and current_selections."""
        ctx = InstructorFilterContext(
            available_filters=[
                SubcategoryFilterResponse(
                    filter_key="grade_level",
                    filter_display_name="Grade Level",
                    filter_type="multi_select",
                    options=[],
                ),
            ],
            current_selections={"grade_level": ["elementary"]},
        )
        assert len(ctx.available_filters) == 1
        assert ctx.current_selections["grade_level"] == ["elementary"]

    def test_instructor_filter_context_empty_filters(self):
        """InstructorFilterContext works with empty filter list."""
        ctx = InstructorFilterContext(available_filters=[], current_selections={})
        assert ctx.available_filters == []

    def test_instructor_filter_context_empty_selections(self):
        """InstructorFilterContext works with empty current_selections."""
        ctx = InstructorFilterContext(available_filters=[], current_selections={})
        assert ctx.current_selections == {}

    def test_subcategory_filter_response_rejects_extra(self):
        """SubcategoryFilterResponse forbids extra fields."""
        with pytest.raises(ValidationError):
            SubcategoryFilterResponse(
                filter_key="k", filter_display_name="K", filter_type="single_select",
                bogus="extra",
            )


# ── 2C. Updated service_catalog schemas ───────────────────────


class TestServiceCatalogSchemaUpdates:
    def test_top_category_item_no_slug(self):
        """TopCategoryItem no longer has slug field."""
        item = TopCategoryItem(id=_ULID, name="Music")
        assert not hasattr(item, "slug") or "slug" not in item.model_fields

    def test_category_with_services_no_slug(self):
        """CategoryWithServices no longer has slug field."""
        CategoryWithServices(id=_ULID, name="Music")
        assert "slug" not in CategoryWithServices.model_fields

    def test_category_service_detail_has_subcategory_id(self):
        """CategoryServiceDetail uses subcategory_id, not category_id."""
        d = CategoryServiceDetail(
            id=_ULID, subcategory_id=_ULID2, name="Piano", slug="piano",
        )
        assert d.subcategory_id == _ULID2
        assert "category_id" not in CategoryServiceDetail.model_fields

    def test_category_service_detail_eligible_age_groups(self):
        """CategoryServiceDetail has eligible_age_groups field."""
        d = CategoryServiceDetail(
            id=_ULID, subcategory_id=_ULID2, name="Piano", slug="piano",
            eligible_age_groups=["kids", "teens"],
        )
        assert d.eligible_age_groups == ["kids", "teens"]

    def test_category_response_no_slug(self):
        """CategoryResponse does not have slug field."""
        CategoryResponse(id=_ULID, name="Music", display_order=1)
        assert "slug" not in CategoryResponse.model_fields


# ── 2D. Updated instructor schemas ────────────────────────────


class TestInstructorSchemaUpdates:
    def test_service_create_accepts_filter_selections(self):
        """ServiceCreate accepts filter_selections dict."""
        from app.schemas.instructor import ServiceCreate

        s = ServiceCreate(
            service_catalog_id=_ULID,
            hourly_rate=50.0,
            offers_travel=False,
            offers_at_location=False,
            offers_online=True,
            filter_selections={"grade_level": ["elementary"]},
        )
        assert s.filter_selections == {"grade_level": ["elementary"]}

    def test_service_create_filter_selections_none(self):
        """ServiceCreate accepts None for filter_selections."""
        from app.schemas.instructor import ServiceCreate

        s = ServiceCreate(
            service_catalog_id=_ULID,
            hourly_rate=50.0,
            offers_travel=False,
            offers_at_location=False,
            offers_online=True,
        )
        assert s.filter_selections is None or s.filter_selections == {}

    def test_service_create_filter_selections_empty(self):
        """ServiceCreate accepts empty dict for filter_selections."""
        from app.schemas.instructor import ServiceCreate

        s = ServiceCreate(
            service_catalog_id=_ULID,
            hourly_rate=50.0,
            offers_travel=False,
            offers_at_location=False,
            offers_online=True,
            filter_selections={},
        )
        assert s.filter_selections == {}
