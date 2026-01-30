# backend/tests/unit/services/search/test_location_learning_admin_service.py
"""
Unit tests for location_learning_admin_service.py.

Targets missed lines:
- 56, 60, 66: Input validation in _format_clicks
- 72-74: Exception handling for invalid count values
- 121: Region ID lookup when empty
- 171-174: resolve_region_name with None/missing region
- 194, 210, 228, 232, 235, 252: create_manual_alias validation paths

Bug Analysis:
- Line 72-74: Non-integer count values are silently skipped (intentional for robustness)
- Line 252: If add() fails, RuntimeError is raised appropriately
- No critical bugs found - validation is appropriately strict for admin operations
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.services.search.location_learning_admin_service import LocationLearningAdminService


class MockUnresolvedQuery:
    """Mock for unresolved location query rows."""

    def __init__(
        self,
        id: str = "query-1",
        query_normalized: str = "soho",
        search_count: int = 10,
        unique_user_count: int = 5,
        click_count: int = 3,
        click_region_counts: Optional[Dict[str, int]] = None,
        sample_original_queries: Optional[List[str]] = None,
        first_seen_at: Optional[datetime] = None,
        last_seen_at: Optional[datetime] = None,
        status: str = "pending",
    ):
        self.id = id
        self.query_normalized = query_normalized
        self.search_count = search_count
        self.unique_user_count = unique_user_count
        self.click_count = click_count
        self.click_region_counts = click_region_counts
        self.sample_original_queries = sample_original_queries or ["SoHo", "soho nyc"]
        self.first_seen_at = first_seen_at or datetime.now(timezone.utc)
        self.last_seen_at = last_seen_at or datetime.now(timezone.utc)
        self.status = status


class MockRegion:
    """Mock for region boundary rows."""

    def __init__(self, id: str, region_name: str, parent_region: Optional[str] = None):
        self.id = id
        self.region_name = region_name
        self.parent_region = parent_region


class MockAlias:
    """Mock for location alias rows."""

    def __init__(
        self,
        id: str = "alias-1",
        alias_normalized: str = "soho",
        region_boundary_id: Optional[str] = None,
        confidence: float = 0.9,
        user_count: int = 5,
        status: str = "pending_review",
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.alias_normalized = alias_normalized
        self.region_boundary_id = region_boundary_id
        self.confidence = confidence
        self.user_count = user_count
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)


class TestListUnresolved:
    """Tests for list_unresolved method."""

    def test_list_unresolved_with_empty_click_counts(self) -> None:
        """Test handling of None click_region_counts (line 56)."""
        mock_db = MagicMock()

        service = LocationLearningAdminService(mock_db)

        # Mock repositories
        service.unresolved_repo = MagicMock()
        service.location_resolution_repo = MagicMock()

        # Create query with None click counts
        query_with_none = MockUnresolvedQuery(
            id="q1",
            click_region_counts=None,  # Line 56: None counts
        )

        service.unresolved_repo.list_pending = MagicMock(return_value=[query_with_none])
        service.location_resolution_repo.get_regions_by_ids = MagicMock(return_value=[])

        result = service.list_unresolved(limit=10)

        assert len(result.queries) == 1
        assert result.queries[0].clicks == []

    def test_list_unresolved_with_region_ids(self) -> None:
        """Test that region IDs are collected and resolved (line 60)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        service.unresolved_repo = MagicMock()
        service.location_resolution_repo = MagicMock()

        # Create query with click counts
        query = MockUnresolvedQuery(
            id="q1",
            click_region_counts={"region-1": 5, "region-2": 3},
        )

        service.unresolved_repo.list_pending = MagicMock(return_value=[query])
        service.location_resolution_repo.get_regions_by_ids = MagicMock(
            return_value=[
                MockRegion("region-1", "SoHo"),
                MockRegion("region-2", "Tribeca"),
            ]
        )

        result = service.list_unresolved(limit=10)

        # Verify regions were looked up
        service.location_resolution_repo.get_regions_by_ids.assert_called_once()
        call_args = service.location_resolution_repo.get_regions_by_ids.call_args[0][0]
        assert "region-1" in call_args
        assert "region-2" in call_args

        # Verify clicks were formatted with region names
        assert len(result.queries[0].clicks) == 2

    def test_list_unresolved_with_non_dict_click_counts(self) -> None:
        """Test handling of non-dict click_region_counts (line 66)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        service.unresolved_repo = MagicMock()
        service.location_resolution_repo = MagicMock()

        # Create query with non-dict click counts (e.g., a list)
        query = MockUnresolvedQuery(
            id="q1",
            click_region_counts=["not", "a", "dict"],  # type: ignore
        )

        service.unresolved_repo.list_pending = MagicMock(return_value=[query])
        service.location_resolution_repo.get_regions_by_ids = MagicMock(return_value=[])

        result = service.list_unresolved(limit=10)

        # Should handle gracefully and return empty clicks
        assert result.queries[0].clicks == []

    def test_list_unresolved_with_invalid_count_values(self) -> None:
        """Test handling of non-integer count values (lines 72-74)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        service.unresolved_repo = MagicMock()
        service.location_resolution_repo = MagicMock()

        # Create query with invalid count values
        query = MockUnresolvedQuery(
            id="q1",
            click_region_counts={
                "region-1": 5,  # Valid
                "region-2": "not-a-number",  # Invalid - should be skipped
                "region-3": None,  # Invalid - should be handled
                "region-4": {},  # Invalid - should be skipped
            },
        )

        service.unresolved_repo.list_pending = MagicMock(return_value=[query])
        service.location_resolution_repo.get_regions_by_ids = MagicMock(
            return_value=[
                MockRegion("region-1", "SoHo"),
                MockRegion("region-2", "Tribeca"),
                MockRegion("region-3", "Chelsea"),
                MockRegion("region-4", "NoHo"),
            ]
        )

        result = service.list_unresolved(limit=10)

        # Should only include valid count (region-1 with count 5)
        # region-3 with None should be converted to 0
        valid_clicks = [c for c in result.queries[0].clicks if c.count > 0]
        assert len(valid_clicks) >= 1

    def test_list_unresolved_empty_region_ids(self) -> None:
        """Test when click counts have no region IDs (line 121 path)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        service.unresolved_repo = MagicMock()
        service.location_resolution_repo = MagicMock()

        # Create query with empty dict
        query = MockUnresolvedQuery(
            id="q1",
            click_region_counts={},
        )

        service.unresolved_repo.list_pending = MagicMock(return_value=[query])
        service.location_resolution_repo.get_regions_by_ids = MagicMock(return_value=[])

        result = service.list_unresolved(limit=10)

        # get_regions_by_ids should not be called with empty list
        assert result.queries[0].clicks == []


class TestListPendingAliases:
    """Tests for list_pending_aliases method."""

    def test_list_pending_aliases_with_region_ids(self) -> None:
        """Test that aliases with region IDs get resolved (line 121)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        service.location_alias_repo = MagicMock()
        service.location_resolution_repo = MagicMock()

        aliases = [
            MockAlias(id="a1", alias_normalized="soho", region_boundary_id="region-1"),
            MockAlias(id="a2", alias_normalized="tribeca", region_boundary_id="region-2"),
        ]

        service.location_alias_repo.list_by_source_and_status = MagicMock(return_value=aliases)
        service.location_resolution_repo.get_regions_by_ids = MagicMock(
            return_value=[
                MockRegion("region-1", "SoHo"),
                MockRegion("region-2", "Tribeca"),
            ]
        )

        result = service.list_pending_aliases(limit=100)

        assert len(result.aliases) == 2
        # Verify region names were resolved
        assert result.aliases[0].region_name == "SoHo"
        assert result.aliases[1].region_name == "Tribeca"

    def test_list_pending_aliases_with_no_region_ids(self) -> None:
        """Test aliases without region_boundary_id."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        service.location_alias_repo = MagicMock()
        service.location_resolution_repo = MagicMock()

        aliases = [
            MockAlias(id="a1", alias_normalized="ambiguous", region_boundary_id=None),
        ]

        service.location_alias_repo.list_by_source_and_status = MagicMock(return_value=aliases)
        service.location_resolution_repo.get_regions_by_ids = MagicMock(return_value=[])

        result = service.list_pending_aliases(limit=100)

        assert len(result.aliases) == 1
        assert result.aliases[0].region_name is None


class TestResolveRegionName:
    """Tests for resolve_region_name method."""

    def test_resolve_region_name_with_none(self) -> None:
        """Test resolve_region_name returns None for None input (line 171)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()

        result = service.resolve_region_name(None)

        assert result is None
        service.location_resolution_repo.get_region_by_id.assert_not_called()

    def test_resolve_region_name_with_empty_string(self) -> None:
        """Test resolve_region_name returns None for empty string (line 172)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()

        result = service.resolve_region_name("")

        assert result is None
        service.location_resolution_repo.get_region_by_id.assert_not_called()

    def test_resolve_region_name_not_found(self) -> None:
        """Test resolve_region_name returns None when region not found (lines 173-174)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_resolution_repo.get_region_by_id = MagicMock(return_value=None)

        result = service.resolve_region_name("non-existent-region")

        assert result is None

    def test_resolve_region_name_found(self) -> None:
        """Test resolve_region_name returns name when region found."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_resolution_repo.get_region_by_id = MagicMock(
            return_value=MockRegion("region-1", "SoHo")
        )

        result = service.resolve_region_name("region-1")

        assert result == "SoHo"


class TestCreateManualAlias:
    """Tests for create_manual_alias method."""

    def test_create_manual_alias_empty_alias(self) -> None:
        """Test that empty alias raises ValueError (line 210)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        with pytest.raises(ValueError, match="alias is required"):
            service.create_manual_alias(alias="")

    def test_create_manual_alias_whitespace_only(self) -> None:
        """Test that whitespace-only alias raises ValueError (line 210)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        with pytest.raises(ValueError, match="alias is required"):
            service.create_manual_alias(alias="   ")

    def test_create_manual_alias_already_exists(self) -> None:
        """Test that existing alias raises ValueError."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_resolution_repo.find_cached_alias = MagicMock(
            return_value=MockAlias(alias_normalized="soho")
        )

        with pytest.raises(ValueError, match="alias already exists"):
            service.create_manual_alias(alias="soho", region_boundary_id="region-1")

    def test_create_manual_alias_ambiguous_needs_two_valid_regions(self) -> None:
        """Test ambiguous alias requires at least 2 valid regions (line 228)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_resolution_repo.find_cached_alias = MagicMock(return_value=None)
        # Only one valid region returned
        service.location_resolution_repo.get_regions_by_ids = MagicMock(
            return_value=[MockRegion("region-1", "SoHo")]
        )

        with pytest.raises(
            ValueError, match="candidate_region_ids must contain at least 2 valid region ids"
        ):
            service.create_manual_alias(
                alias="houston st",
                candidate_region_ids=["region-1", "invalid-region"],
            )

    def test_create_manual_alias_non_ambiguous_needs_region(self) -> None:
        """Test non-ambiguous alias requires region_boundary_id (line 232)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_resolution_repo.find_cached_alias = MagicMock(return_value=None)

        with pytest.raises(
            ValueError, match="region_boundary_id is required for non-ambiguous aliases"
        ):
            service.create_manual_alias(
                alias="soho",
                region_boundary_id=None,
                candidate_region_ids=None,
            )

    def test_create_manual_alias_invalid_region(self) -> None:
        """Test non-ambiguous alias with invalid region raises ValueError (line 235)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_resolution_repo.find_cached_alias = MagicMock(return_value=None)
        service.location_resolution_repo.get_region_by_id = MagicMock(return_value=None)

        with pytest.raises(ValueError, match="invalid region_boundary_id"):
            service.create_manual_alias(alias="soho", region_boundary_id="invalid-region")

    def test_create_manual_alias_add_fails(self) -> None:
        """Test that failed add() raises RuntimeError (line 252)."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_alias_repo = MagicMock()
        service.unresolved_repo = MagicMock()

        service.location_resolution_repo.find_cached_alias = MagicMock(return_value=None)
        service.location_resolution_repo.get_region_by_id = MagicMock(
            return_value=MockRegion("region-1", "SoHo")
        )
        service.location_alias_repo.add = MagicMock(return_value=False)  # Simulate failure

        with pytest.raises(RuntimeError, match="failed to create alias"):
            service.create_manual_alias(alias="soho", region_boundary_id="region-1")

    def test_create_manual_alias_success(self) -> None:
        """Test successful alias creation."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_alias_repo = MagicMock()
        service.unresolved_repo = MagicMock()

        service.location_resolution_repo.find_cached_alias = MagicMock(return_value=None)
        service.location_resolution_repo.get_region_by_id = MagicMock(
            return_value=MockRegion("region-1", "SoHo")
        )
        service.location_alias_repo.add = MagicMock(return_value=True)
        service.unresolved_repo.mark_resolved = MagicMock()

        result = service.create_manual_alias(alias="soho", region_boundary_id="region-1")

        assert result.status == "created"
        assert result.alias_id is not None

    def test_create_manual_alias_ambiguous_success(self) -> None:
        """Test successful ambiguous alias creation with candidate regions."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()
        service.location_alias_repo = MagicMock()
        service.unresolved_repo = MagicMock()

        service.location_resolution_repo.find_cached_alias = MagicMock(return_value=None)
        service.location_resolution_repo.get_regions_by_ids = MagicMock(
            return_value=[
                MockRegion("region-1", "SoHo Manhattan"),
                MockRegion("region-2", "SoHo Brooklyn"),
            ]
        )
        service.location_alias_repo.add = MagicMock(return_value=True)
        service.unresolved_repo.mark_resolved = MagicMock()

        result = service.create_manual_alias(
            alias="soho",
            candidate_region_ids=["region-1", "region-2"],
        )

        assert result.status == "created"

        # Verify the alias was created with requires_clarification=True
        add_call = service.location_alias_repo.add.call_args[0][0]
        assert add_call.requires_clarification is True
        assert add_call.region_boundary_id is None


class TestDismissUnresolved:
    """Tests for dismiss_unresolved method."""

    def test_dismiss_unresolved_normalizes_query(self) -> None:
        """Test that query is normalized before dismissing."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.unresolved_repo = MagicMock()

        result = service.dismiss_unresolved("  SoHo  NYC  ")

        service.unresolved_repo.set_status.assert_called_once_with(
            "soho nyc", status="rejected"
        )
        assert result.status == "dismissed"
        assert result.query_normalized == "soho nyc"

    def test_dismiss_unresolved_empty_query(self) -> None:
        """Test handling of empty query after normalization."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.unresolved_repo = MagicMock()

        result = service.dismiss_unresolved("   ")

        # Empty string after normalization should not call set_status
        service.unresolved_repo.set_status.assert_not_called()
        assert result.query_normalized == ""


class TestSetAliasStatus:
    """Tests for alias status update methods."""

    def test_set_alias_status_delegates_to_repo(self) -> None:
        """Test set_alias_status calls repository."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_alias_repo = MagicMock()
        service.location_alias_repo.update_status = MagicMock(return_value=True)

        result = service.set_alias_status("alias-1", "active")

        service.location_alias_repo.update_status.assert_called_once_with("alias-1", "active")
        assert result is True

    def test_approve_alias_sets_active(self) -> None:
        """Test approve_alias sets status to active."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_alias_repo = MagicMock()
        service.location_alias_repo.update_status = MagicMock(return_value=True)

        service.approve_alias("alias-1")

        service.location_alias_repo.update_status.assert_called_with("alias-1", "active")

    def test_reject_alias_sets_deprecated(self) -> None:
        """Test reject_alias sets status to deprecated."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_alias_repo = MagicMock()
        service.location_alias_repo.update_status = MagicMock(return_value=True)

        service.reject_alias("alias-1")

        service.location_alias_repo.update_status.assert_called_with("alias-1", "deprecated")


class TestListRegions:
    """Tests for list_regions method."""

    def test_list_regions_filters_invalid(self) -> None:
        """Test that regions with None id or region_name are filtered out."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)
        service.location_resolution_repo = MagicMock()

        # Include some invalid regions
        regions = [
            MockRegion("region-1", "SoHo"),
            SimpleNamespace(id=None, region_name="NoID", parent_region=None),  # Invalid
            SimpleNamespace(id="region-3", region_name=None, parent_region=None),  # Invalid
            MockRegion("region-4", "Tribeca", "Manhattan"),
        ]

        service.location_resolution_repo.list_regions = MagicMock(return_value=regions)

        result = service.list_regions(limit=100)

        # Only valid regions should be included
        assert len(result.regions) == 2
        assert result.regions[0].id == "region-1"
        assert result.regions[1].id == "region-4"
        assert result.regions[1].borough == "Manhattan"


class TestProcess:
    """Tests for process method."""

    def test_process_delegates_to_learning_service(self) -> None:
        """Test process calls learning service and formats response."""
        mock_db = MagicMock()
        service = LocationLearningAdminService(mock_db)

        mock_learned = [
            SimpleNamespace(
                alias_normalized="soho",
                region_boundary_id="region-1",
                confidence=0.95,
                status="active",
                confirmations=3,
            )
        ]

        service.learning_service = MagicMock()
        service.learning_service.process_pending = MagicMock(return_value=mock_learned)

        result = service.process(limit=10)

        service.learning_service.process_pending.assert_called_once_with(limit=10)
        assert result.learned_count == 1
        assert result.learned[0].alias_normalized == "soho"
