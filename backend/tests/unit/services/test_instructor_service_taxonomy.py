# backend/tests/unit/services/test_instructor_service_taxonomy.py
"""
Unit tests for InstructorService taxonomy methods (Phase 4).

Pure unit tests — all repositories are mocked via the _build_service() pattern.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.services.instructor_service import InstructorService

# ── Helpers ────────────────────────────────────────────────────


def _build_service() -> InstructorService:
    """Build InstructorService with all repos mocked."""
    db = MagicMock()
    svc = InstructorService(db)
    svc.profile_repository = MagicMock()
    svc.service_repository = MagicMock()
    svc.user_repository = MagicMock()
    svc.booking_repository = MagicMock()
    svc.catalog_repository = MagicMock()
    svc.category_repository = MagicMock()
    svc.analytics_repository = MagicMock()
    svc.preferred_place_repository = MagicMock()
    svc.service_area_repository = MagicMock()
    svc.taxonomy_filter_repository = MagicMock()
    return svc


def _make_category(id: str, name: str, display_order: int = 0, subcategories=None):
    return SimpleNamespace(
        id=id,
        name=name,
        description=f"{name} description",
        subtitle=None,
        display_order=display_order,
        icon_name=None,
        subcategories=subcategories or [],
    )


def _make_subcategory(id: str, name: str, category_id: str, display_order: int = 0, services=None):
    return SimpleNamespace(
        id=id,
        name=name,
        category_id=category_id,
        display_order=display_order,
        services=services or [],
    )


def _make_catalog_service(
    id: str = "svc-1",
    subcategory_id: str = "sub-1",
    name: str = "Piano",
    slug: str = "piano",
    eligible_age_groups=None,
):
    return SimpleNamespace(
        id=id,
        subcategory_id=subcategory_id,
        category_name="Music",
        name=name,
        slug=slug,
        description="Lessons",
        search_terms=["piano", "keyboard"],
        eligible_age_groups=eligible_age_groups or ["kids", "teens", "adults"],
        display_order=0,
        online_capable=True,
        requires_certification=False,
    )


# ── Group 4A: _catalog_service_to_dict ─────────────────────────


class TestCatalogServiceToDict:
    def test_subcategory_id_not_category_id(self):
        """Ensure output has subcategory_id, not category_id."""
        svc = _build_service()
        catalog = _make_catalog_service()
        result = svc._catalog_service_to_dict(catalog)

        assert "subcategory_id" in result
        assert "category_id" not in result
        assert result["subcategory_id"] == "sub-1"

    def test_eligible_age_groups_included(self):
        svc = _build_service()
        catalog = _make_catalog_service(eligible_age_groups=["kids", "teens"])
        result = svc._catalog_service_to_dict(catalog)

        assert result["eligible_age_groups"] == ["kids", "teens"]

    def test_category_name_included(self):
        svc = _build_service()
        catalog = _make_catalog_service()
        result = svc._catalog_service_to_dict(catalog)

        assert result["category_name"] == "Music"

    def test_empty_search_terms_defaults_to_list(self):
        svc = _build_service()
        catalog = _make_catalog_service()
        catalog.search_terms = None
        result = svc._catalog_service_to_dict(catalog)

        assert result["search_terms"] == []

    def test_empty_age_groups_defaults_to_list(self):
        svc = _build_service()
        catalog = _make_catalog_service()
        catalog.eligible_age_groups = None
        result = svc._catalog_service_to_dict(catalog)

        assert result["eligible_age_groups"] == []


# ── Group 4B: Filter validation in create_instructor_service_from_catalog ──


class TestCreateInstructorServiceFilterValidation:
    def test_valid_filter_selections_accepted(self):
        svc = _build_service()
        profile = SimpleNamespace(id="prof-1")
        svc.profile_repository.find_one_by.return_value = profile

        catalog = _make_catalog_service()
        svc.catalog_repository.get_by_id.return_value = catalog

        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (True, [])
        svc.service_repository.find_one_by.return_value = None

        created = SimpleNamespace(id="isvc-1", service_catalog_id="svc-1")
        svc.service_repository.create.return_value = created
        svc.cache_service = MagicMock()
        svc._invalidate_instructor_caches = MagicMock()

        with patch("app.services.instructor_service.invalidate_on_service_change"):
            with patch.object(svc, "_instructor_service_to_dict", return_value={"id": "isvc-1"}):
                result = svc.create_instructor_service_from_catalog(
                    "user-1",
                    "svc-1",
                    60.0,
                    filter_selections={"grade_level": ["elementary"]},
                )

        assert result == {"id": "isvc-1"}
        svc.taxonomy_filter_repository.validate_filter_selections.assert_called_once()

    def test_invalid_filter_selections_raises(self):
        svc = _build_service()
        profile = SimpleNamespace(id="prof-1")
        svc.profile_repository.find_one_by.return_value = profile

        catalog = _make_catalog_service()
        svc.catalog_repository.get_by_id.return_value = catalog

        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (
            False,
            ["Unknown filter key: bogus"],
        )

        with pytest.raises(BusinessRuleException, match="Invalid filter selections"):
            svc.create_instructor_service_from_catalog(
                "user-1",
                "svc-1",
                60.0,
                filter_selections={"bogus": ["value"]},
            )

    def test_invalid_age_groups_raises(self):
        svc = _build_service()
        profile = SimpleNamespace(id="prof-1")
        svc.profile_repository.find_one_by.return_value = profile

        catalog = _make_catalog_service(eligible_age_groups=["kids", "teens"])
        svc.catalog_repository.get_by_id.return_value = catalog

        with pytest.raises(BusinessRuleException, match="not eligible"):
            svc.create_instructor_service_from_catalog(
                "user-1",
                "svc-1",
                60.0,
                age_groups=["adults"],
            )

    def test_no_filter_selections_skips_validation(self):
        """When filter_selections is None, validation is skipped."""
        svc = _build_service()
        profile = SimpleNamespace(id="prof-1")
        svc.profile_repository.find_one_by.return_value = profile

        catalog = _make_catalog_service()
        svc.catalog_repository.get_by_id.return_value = catalog
        svc.service_repository.find_one_by.return_value = None

        created = SimpleNamespace(id="isvc-1", service_catalog_id="svc-1")
        svc.service_repository.create.return_value = created
        svc.cache_service = MagicMock()
        svc._invalidate_instructor_caches = MagicMock()

        with patch("app.services.instructor_service.invalidate_on_service_change"):
            with patch.object(svc, "_instructor_service_to_dict", return_value={"id": "isvc-1"}):
                svc.create_instructor_service_from_catalog("user-1", "svc-1", 60.0)

        svc.taxonomy_filter_repository.validate_filter_selections.assert_not_called()


# ── Group 4C: Filter validation in _update_services ────────────


class TestUpdateServicesFilterValidation:
    def test_filter_selections_validated(self):
        svc = _build_service()

        service_data = SimpleNamespace(
            service_catalog_id="cat-1",
            filter_selections={"grade": ["elem"]},
            model_dump=lambda: {
                "service_catalog_id": "cat-1",
                "filter_selections": {"grade": ["elem"]},
                "offers_travel": False,
                "offers_at_location": False,
                "offers_online": True,
                "hourly_rate": 50.0,
                "duration_options": [60],
            },
        )

        svc.service_repository.find_by.return_value = []
        svc.catalog_repository.exists.return_value = True
        catalog_svc = SimpleNamespace(subcategory_id="sub-1")
        svc.catalog_repository.get_by_id.return_value = catalog_svc
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (True, [])

        svc._validate_catalog_ids = MagicMock()
        svc._apply_location_type_capabilities = MagicMock()
        svc.validate_service_capabilities = MagicMock()
        svc.service_repository.create.return_value = SimpleNamespace(id="new-svc")

        svc._update_services("prof-1", "user-1", [service_data])

        svc.taxonomy_filter_repository.validate_filter_selections.assert_called_once_with(
            subcategory_id="sub-1",
            selections={"grade": ["elem"]},
        )

    def test_invalid_filter_selections_raises(self):
        svc = _build_service()

        service_data = SimpleNamespace(
            service_catalog_id="cat-1",
            filter_selections={"bogus": ["val"]},
            model_dump=lambda: {
                "service_catalog_id": "cat-1",
                "filter_selections": {"bogus": ["val"]},
                "offers_travel": False,
                "offers_at_location": False,
                "offers_online": True,
                "hourly_rate": 50.0,
                "duration_options": [60],
            },
        )

        svc.service_repository.find_by.return_value = []
        svc.catalog_repository.exists.return_value = True
        catalog_svc = SimpleNamespace(subcategory_id="sub-1")
        svc.catalog_repository.get_by_id.return_value = catalog_svc
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (
            False,
            ["Unknown filter key: bogus"],
        )

        svc._validate_catalog_ids = MagicMock()

        with pytest.raises(BusinessRuleException, match="Invalid filter selections"):
            svc._update_services("prof-1", "user-1", [service_data])


# ── Group 4D: New taxonomy methods ─────────────────────────────


class TestGetCategoriesWithSubcategories:
    def test_returns_sorted_categories_with_subcategories(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        sub1 = _make_subcategory("sub-1", "Guitar", "cat-1", display_order=1, services=[])
        sub0 = _make_subcategory("sub-0", "Piano", "cat-1", display_order=0, services=[])
        cat = _make_category("cat-1", "Music", display_order=0, subcategories=[sub1, sub0])

        svc.catalog_repository.get_categories_with_subcategories.return_value = [cat]

        result = svc.get_categories_with_subcategories()

        assert len(result) == 1
        assert result[0]["name"] == "Music"
        # Subcategories sorted by display_order
        assert result[0]["subcategories"][0]["name"] == "Piano"
        assert result[0]["subcategories"][1]["name"] == "Guitar"

    def test_cache_hit(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "cached"}]

        result = svc.get_categories_with_subcategories()
        assert result == [{"id": "cached"}]
        svc.catalog_repository.get_categories_with_subcategories.assert_not_called()

    def test_cache_set_on_miss(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        svc.catalog_repository.get_categories_with_subcategories.return_value = []

        svc.get_categories_with_subcategories()
        svc.cache_service.set.assert_called_once()


class TestGetCategoryTree:
    def test_returns_full_tree(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        catalog_svc = _make_catalog_service()
        sub = _make_subcategory("sub-1", "Keyboard", "cat-1", services=[catalog_svc])
        cat = _make_category("cat-1", "Music", subcategories=[sub])

        svc.catalog_repository.get_category_tree.return_value = cat

        result = svc.get_category_tree("cat-1")

        assert result["id"] == "cat-1"
        assert len(result["subcategories"]) == 1
        assert len(result["subcategories"][0]["services"]) == 1
        assert result["subcategories"][0]["services"][0]["subcategory_id"] == "sub-1"

    def test_not_found_raises(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_category_tree.return_value = None

        with pytest.raises(NotFoundException, match="Category not found"):
            svc.get_category_tree("missing")

    def test_cache_hit(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = {"id": "cached-tree"}

        result = svc.get_category_tree("cat-1")
        assert result == {"id": "cached-tree"}


class TestGetSubcategoryWithServices:
    def test_returns_subcategory_with_services(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        catalog_svc = _make_catalog_service()
        sub = _make_subcategory("sub-1", "Keyboard", "cat-1", services=[catalog_svc])

        svc.catalog_repository.get_subcategory_with_services.return_value = sub

        result = svc.get_subcategory_with_services("sub-1")

        assert result["id"] == "sub-1"
        assert result["category_id"] == "cat-1"
        assert len(result["services"]) == 1

    def test_not_found_raises(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None
        svc.catalog_repository.get_subcategory_with_services.return_value = None

        with pytest.raises(NotFoundException, match="Subcategory not found"):
            svc.get_subcategory_with_services("missing")


class TestGetSubcategoryFilters:
    def test_delegates_to_taxonomy_filter_repo(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        expected = [{"filter_key": "grade", "options": []}]
        svc.taxonomy_filter_repository.get_filters_for_subcategory.return_value = expected

        result = svc.get_subcategory_filters("sub-1")

        assert result == expected
        svc.taxonomy_filter_repository.get_filters_for_subcategory.assert_called_once_with("sub-1")

    def test_cache_hit(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"filter_key": "cached"}]

        result = svc.get_subcategory_filters("sub-1")
        assert result == [{"filter_key": "cached"}]
        svc.taxonomy_filter_repository.get_filters_for_subcategory.assert_not_called()


class TestGetServiceFilterContext:
    def test_returns_filter_context(self):
        svc = _build_service()
        catalog_svc = _make_catalog_service()
        svc.catalog_repository.get_service_with_subcategory.return_value = catalog_svc

        filters = [{"filter_key": "grade", "options": [{"value": "elem"}]}]
        svc.taxonomy_filter_repository.get_filters_for_subcategory.return_value = filters

        result = svc.get_service_filter_context("svc-1")

        assert result["available_filters"] == filters
        assert result["current_selections"] == {}

    def test_not_found_raises(self):
        svc = _build_service()
        svc.catalog_repository.get_service_with_subcategory.return_value = None

        with pytest.raises(NotFoundException, match="Service not found"):
            svc.get_service_filter_context("missing")


class TestGetServicesByAgeGroup:
    def test_returns_converted_services(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        catalog_svc = _make_catalog_service()
        svc.catalog_repository.get_services_by_eligible_age_group.return_value = [catalog_svc]

        result = svc.get_services_by_age_group("kids")

        assert len(result) == 1
        assert result[0]["name"] == "Piano"
        svc.catalog_repository.get_services_by_eligible_age_group.assert_called_once_with("kids")

    def test_cache_hit(self):
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = [{"id": "cached"}]

        result = svc.get_services_by_age_group("kids")
        assert result == [{"id": "cached"}]


# ── Group 4E: Updated existing methods ─────────────────────────


class TestGetAvailableCatalogServicesUpdated:
    def test_category_id_param_used(self):
        """Verify category_id (not slug) is passed to repo."""
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        catalog = _make_catalog_service()
        svc.catalog_repository.get_active_services_with_categories.return_value = [catalog]

        svc.get_available_catalog_services(category_id="cat-1")

        svc.catalog_repository.get_active_services_with_categories.assert_called_once_with(
            category_id="cat-1"
        )


class TestGetServiceCategoriesUpdated:
    def test_no_slug_in_output(self):
        """Verify output dicts do NOT contain a slug key."""
        svc = _build_service()
        svc.cache_service = MagicMock()
        svc.cache_service.get.return_value = None

        cat = SimpleNamespace(
            id="cat-1",
            name="Music",
            description="desc",
            display_order=1,
            subtitle=None,
            icon_name=None,
        )
        svc.category_repository.get_all_active.return_value = [cat]

        result = svc.get_service_categories()

        assert len(result) == 1
        assert "slug" not in result[0]
        assert result[0]["id"] == "cat-1"
