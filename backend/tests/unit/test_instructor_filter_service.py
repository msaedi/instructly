# backend/tests/unit/test_instructor_filter_service.py
"""
Unit tests for InstructorService filter selection methods.

Mock repositories to test update_filter_selections and
validate_filter_selections_for_service.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import BusinessRuleException, NotFoundException
from app.services.instructor_service import InstructorService

# ── Helpers ────────────────────────────────────────────────────


def _profile(**kw: Any) -> SimpleNamespace:
    defaults = {"id": "PROF01", "user_id": "USER01"}
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _instructor_service(**kw: Any) -> SimpleNamespace:
    defaults = {
        "id": "IS01",
        "instructor_profile_id": "PROF01",
        "service_catalog_id": "CAT_SVC01",
        "name": "Piano",
        "hourly_rate": 50.0,
        "custom_description": None,
        "duration_options": [60],
        "filter_selections": {},
        "is_active": True,
        "offers_travel": False,
        "offers_at_location": False,
        "offers_online": True,
        "created_at": None,
        "updated_at": None,
        "catalog_entry": None,
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _catalog_entry(**kw: Any) -> SimpleNamespace:
    defaults = {
        "id": "CAT_SVC01",
        "subcategory_id": "SUB01",
        "name": "Classical Piano",
        "slug": "classical-piano",
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _build_instructor_service() -> InstructorService:
    """Build InstructorService with mocked dependencies."""
    with patch.object(InstructorService, "__init__", lambda self, *a, **kw: None):
        svc = InstructorService.__new__(InstructorService)
        svc.db = MagicMock()
        svc.cache_service = MagicMock()
        svc.profile_repository = MagicMock()
        svc.service_repository = MagicMock()
        svc.catalog_repository = MagicMock()
        svc.taxonomy_filter_repository = MagicMock()

        # Mock transaction context manager
        svc.transaction = MagicMock()
        svc.transaction.return_value.__enter__ = MagicMock(return_value=None)
        svc.transaction.return_value.__exit__ = MagicMock(return_value=False)

        # Mock _invalidate_instructor_caches to avoid side effects
        svc._invalidate_instructor_caches = MagicMock()

        # Mock _instructor_service_to_dict to return a simple dict
        svc._instructor_service_to_dict = MagicMock(
            return_value={
                "id": "IS01",
                "catalog_service_id": "CAT_SVC01",
                "name": "Piano",
                "service_catalog_name": "Classical Piano",
                "category": "Music",
                "hourly_rate": 50.0,
                "description": None,
                "duration_options": [60],
                "offers_travel": False,
                "offers_at_location": False,
                "offers_online": True,
                "is_active": True,
                "created_at": None,
                "updated_at": None,
            }
        )

        return svc


# ── update_filter_selections ────────────────────────────────


class TestUpdateFilterSelections:
    @patch("app.services.instructor_service.invalidate_on_service_change")
    def test_happy_path(self, mock_invalidate: MagicMock) -> None:
        svc = _build_instructor_service()
        svc.profile_repository.find_one_by.return_value = _profile()
        svc.service_repository.find_one_by.return_value = _instructor_service()
        svc.catalog_repository.get_by_id.return_value = _catalog_entry()
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (True, [])

        result = svc.update_filter_selections(
            instructor_id="USER01",
            instructor_service_id="IS01",
            filter_selections={"grade_level": ["elementary"]},
        )

        assert result["id"] == "IS01"
        svc.service_repository.update.assert_called_once()
        mock_invalidate.assert_called_once_with("IS01", "update")

    def test_rejects_non_owner(self) -> None:
        svc = _build_instructor_service()
        svc.profile_repository.find_one_by.return_value = _profile(id="PROF_OTHER")
        svc.service_repository.find_one_by.return_value = _instructor_service(
            instructor_profile_id="PROF01"
        )

        with pytest.raises(BusinessRuleException, match="do not own"):
            svc.update_filter_selections(
                instructor_id="USER01",
                instructor_service_id="IS01",
                filter_selections={"grade_level": ["elementary"]},
            )

    def test_rejects_invalid_selections(self) -> None:
        svc = _build_instructor_service()
        svc.profile_repository.find_one_by.return_value = _profile()
        svc.service_repository.find_one_by.return_value = _instructor_service()
        svc.catalog_repository.get_by_id.return_value = _catalog_entry()
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (
            False,
            ["Unknown filter key 'bogus'"],
        )

        with pytest.raises(BusinessRuleException, match="Invalid filter"):
            svc.update_filter_selections(
                instructor_id="USER01",
                instructor_service_id="IS01",
                filter_selections={"bogus": ["x"]},
            )

    def test_not_found_missing_profile(self) -> None:
        svc = _build_instructor_service()
        svc.profile_repository.find_one_by.return_value = None

        with pytest.raises(NotFoundException, match="profile"):
            svc.update_filter_selections("USER01", "IS01", {})

    def test_not_found_missing_service(self) -> None:
        svc = _build_instructor_service()
        svc.profile_repository.find_one_by.return_value = _profile()
        svc.service_repository.find_one_by.return_value = None

        with pytest.raises(NotFoundException, match="service"):
            svc.update_filter_selections("USER01", "IS01", {})


# ── validate_filter_selections_for_service ───────────────────


class TestValidateFilterSelectionsForService:
    def test_valid_returns_true(self) -> None:
        svc = _build_instructor_service()
        svc.catalog_repository.get_by_id.return_value = _catalog_entry()
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (True, [])

        result = svc.validate_filter_selections_for_service(
            service_catalog_id="CAT_SVC01",
            selections={"grade_level": ["elementary"]},
        )

        assert result["valid"] is True
        assert result["errors"] == []

    def test_invalid_returns_per_field_errors(self) -> None:
        svc = _build_instructor_service()
        svc.catalog_repository.get_by_id.return_value = _catalog_entry()
        svc.taxonomy_filter_repository.validate_filter_selections.return_value = (
            False,
            ["Unknown option 'bogus' for filter 'grade_level'"],
        )

        result = svc.validate_filter_selections_for_service(
            service_catalog_id="CAT_SVC01",
            selections={"grade_level": ["bogus"]},
        )

        assert result["valid"] is False
        assert len(result["errors"]) == 1

    def test_not_found_for_missing_service(self) -> None:
        svc = _build_instructor_service()
        svc.catalog_repository.get_by_id.return_value = None

        with pytest.raises(NotFoundException, match="not found"):
            svc.validate_filter_selections_for_service("INVALID", {})
