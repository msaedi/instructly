# backend/tests/unit/test_catalog_browse_service.py
"""
Unit tests for CatalogBrowseService.

Mock all repositories; verify dict shapes match Pydantic schemas.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import NotFoundException
from app.services.catalog_browse_service import CatalogBrowseService

# ── Helpers ────────────────────────────────────────────────────


def _cat(**kw: Any) -> SimpleNamespace:
    defaults = {
        "id": "CAT01",
        "slug": "music",
        "name": "Music",
        "description": "All things music",
        "meta_title": None,
        "meta_description": None,
        "display_order": 1,
        "subtitle": None,
        "icon_name": "music",
        "subcategories": [],
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _sub(**kw: Any) -> SimpleNamespace:
    defaults = {
        "id": "SUB01",
        "slug": "piano",
        "name": "Piano",
        "description": "Piano lessons",
        "meta_title": None,
        "meta_description": None,
        "display_order": 1,
        "is_active": True,
        "category": _cat(),
        "services": [],
        "subcategory_filters": [],
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _svc(**kw: Any) -> SimpleNamespace:
    defaults = {
        "id": "SVC01",
        "slug": "classical-piano",
        "name": "Classical Piano",
        "description": "Classical piano instruction",
        "subcategory_id": "SUB01",
        "display_order": 1,
        "is_active": True,
        "eligible_age_groups": ["kids", "teens", "adults"],
        "default_duration_minutes": 60,
        "online_capable": True,
        "requires_certification": False,
        "search_terms": ["piano", "classical"],
        "price_floor_in_person_cents": None,
        "price_floor_online_cents": None,
        "subcategory": _sub(),
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _build_service() -> CatalogBrowseService:
    """Build CatalogBrowseService with mocked repos."""
    with patch.object(CatalogBrowseService, "__init__", lambda self, db: None):
        svc = CatalogBrowseService.__new__(CatalogBrowseService)
        svc.db = MagicMock()
        svc.category_repo = MagicMock()
        svc.subcategory_repo = MagicMock()
        svc.catalog_repo = MagicMock()
        svc.filter_repo = MagicMock()
        return svc


# ── Tests ──────────────────────────────────────────────────────


class TestListCategories:
    def test_returns_ordered_list_with_subcategory_count(self) -> None:
        svc = _build_service()
        svc.category_repo.get_all_active.return_value = [
            _cat(
                id="C1",
                slug="music",
                name="Music",
                subcategories=[
                    _sub(id="S1", is_active=True),
                    _sub(id="S2", is_active=True),
                    _sub(id="S3", is_active=False),
                ],
            ),
            _cat(id="C2", slug="arts", name="Arts", subcategories=[]),
        ]

        result = svc.list_categories()

        assert len(result) == 2
        assert result[0]["name"] == "Music"
        assert result[0]["subcategory_count"] == 2  # only active ones
        assert result[1]["subcategory_count"] == 0

    def test_returns_empty_list_when_no_categories(self) -> None:
        svc = _build_service()
        svc.category_repo.get_all_active.return_value = []

        result = svc.list_categories()

        assert result == []


class TestGetCategory:
    def test_returns_detail_with_subcategories(self) -> None:
        svc = _build_service()
        sub1 = _sub(id="S1", slug="piano", name="Piano", display_order=1, is_active=True)
        sub1.services = [_svc(is_active=True), _svc(id="SVC02", is_active=True)]
        sub2 = _sub(id="S2", slug="guitar", name="Guitar", display_order=2, is_active=True)
        sub2.services = [_svc(id="SVC03", is_active=False)]

        cat = _cat(slug="music", subcategories=[sub2, sub1])
        svc.category_repo.get_by_slug.return_value = cat

        result = svc.get_category("music")

        assert result["slug"] == "music"
        assert len(result["subcategories"]) == 2
        # Sorted by display_order
        assert result["subcategories"][0]["name"] == "Piano"
        assert result["subcategories"][0]["service_count"] == 2
        assert result["subcategories"][1]["name"] == "Guitar"
        assert result["subcategories"][1]["service_count"] == 0  # only inactive service

    def test_raises_not_found_for_missing_slug(self) -> None:
        svc = _build_service()
        svc.category_repo.get_by_slug.return_value = None

        with pytest.raises(NotFoundException, match="not found"):
            svc.get_category("nonexistent")


class TestGetSubcategory:
    def test_returns_detail_with_services_and_filters(self) -> None:
        svc = _build_service()
        service = _svc(id="SVC01", is_active=True)
        sub = _sub(
            id="SUB01",
            slug="piano",
            services=[service],
        )
        svc.subcategory_repo.get_by_category_slug.return_value = sub
        svc.filter_repo.get_filters_for_subcategory.return_value = [
            {"filter_key": "grade_level", "filter_display_name": "Grade Level"}
        ]

        result = svc.get_subcategory("music", "piano")

        assert result["slug"] == "piano"
        assert len(result["services"]) == 1
        assert result["services"][0]["name"] == "Classical Piano"
        assert len(result["filters"]) == 1
        assert result["category"]["name"] == "Music"

    def test_raises_not_found_when_slug_mismatch(self) -> None:
        svc = _build_service()
        svc.subcategory_repo.get_by_category_slug.return_value = None

        with pytest.raises(NotFoundException, match="not found"):
            svc.get_subcategory("music", "algebra")

    def test_raises_not_found_for_nonexistent_slug(self) -> None:
        svc = _build_service()
        svc.subcategory_repo.get_by_category_slug.return_value = None

        with pytest.raises(NotFoundException, match="not found"):
            svc.get_subcategory("nonexistent", "nonexistent")

    def test_handles_null_category_gracefully(self) -> None:
        svc = _build_service()
        service = _svc(id="SVC01", is_active=True)
        sub = _sub(
            id="SUB01",
            slug="orphan",
            category=None,
            services=[service],
        )
        svc.subcategory_repo.get_by_category_slug.return_value = sub
        svc.filter_repo.get_filters_for_subcategory.return_value = []

        result = svc.get_subcategory("any", "orphan")

        assert result["slug"] == "orphan"
        assert len(result["services"]) == 1
        assert result["services"][0]["category_name"] is None
        assert result["category"] == {}

    def test_excludes_inactive_services(self) -> None:
        svc = _build_service()
        active = _svc(id="SVC01", is_active=True)
        inactive = _svc(id="SVC02", is_active=False)
        sub = _sub(services=[active, inactive])
        svc.subcategory_repo.get_by_category_slug.return_value = sub
        svc.filter_repo.get_filters_for_subcategory.return_value = []

        result = svc.get_subcategory("music", "piano")

        assert len(result["services"]) == 1
        assert result["services"][0]["id"] == "SVC01"


class TestGetService:
    def test_returns_detail(self) -> None:
        svc = _build_service()
        service_obj = _svc()
        svc.catalog_repo.get_service_with_subcategory.return_value = service_obj

        result = svc.get_service("SVC01")

        assert result["id"] == "SVC01"
        assert result["name"] == "Classical Piano"
        assert result["subcategory_name"] == "Piano"
        assert result["subcategory_id"] == "SUB01"

    def test_raises_not_found_for_missing_id(self) -> None:
        svc = _build_service()
        svc.catalog_repo.get_service_with_subcategory.return_value = None

        with pytest.raises(NotFoundException, match="not found"):
            svc.get_service("INVALID")


class TestListServicesForSubcategory:
    def test_returns_active_services(self) -> None:
        svc = _build_service()
        svc.catalog_repo.get_by_subcategory.return_value = [
            _svc(id="SVC01", slug="piano-1"),
            _svc(id="SVC02", slug="piano-2"),
        ]

        result = svc.list_services_for_subcategory("SUB01")

        assert len(result) == 2
        assert result[0]["id"] == "SVC01"


class TestGetFiltersForSubcategory:
    def test_returns_filter_tree(self) -> None:
        svc = _build_service()
        svc.filter_repo.get_filters_for_subcategory.return_value = [
            {
                "id": "F1",
                "key": "grade_level",
                "display_name": "Grade Level",
                "filter_type": "multi_select",
                "is_required": False,
                "options": [{"id": "O1", "value": "elementary", "display_name": "Elementary", "display_order": 1}],
            }
        ]

        result = svc.get_filters_for_subcategory("SUB01")

        assert len(result) == 1
        assert result[0]["key"] == "grade_level"
        assert len(result[0]["options"]) == 1
