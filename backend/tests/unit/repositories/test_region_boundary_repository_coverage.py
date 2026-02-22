"""Unit tests for RegionBoundaryRepository — targets missed lines and branch partials.

Missed lines:
  162-163 find_region_by_point: exception → db.rollback() also raises → caught
  196-197 list_regions: exception → db.rollback() also raises → caught
  240-241 get_simplified_geojson_by_ids: exception → db.rollback() also raises → caught
  265->251 find_region_ids_by_partial_names: loop iteration with exception inside
  270-271 find_region_ids_by_partial_names: exception → db.rollback() also raises → caught
  298-299 delete_by_region_name: exception → db.rollback() also raises → caught
  325-326 delete_by_region_code: exception → db.rollback() also raises → caught
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.region_boundary_repository import RegionBoundaryRepository


def _make_repo() -> tuple[RegionBoundaryRepository, MagicMock]:
    mock_db = MagicMock()
    repo = RegionBoundaryRepository(mock_db)
    return repo, mock_db


# ------------------------------------------------------------------
# find_region_by_point — lines 162-163
# ------------------------------------------------------------------


class TestFindRegionByPoint:
    """Cover the double-exception path (db.rollback also fails)."""

    def test_exception_with_rollback_failure(self) -> None:
        """Lines 162-163: execute raises → rollback also raises → returns None."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback also failed")

        result = repo.find_region_by_point(40.7128, -74.0060, "nyc")

        assert result is None
        mock_db.rollback.assert_called_once()

    def test_exception_with_rollback_success(self) -> None:
        """Primary exception path: execute raises → rollback succeeds → returns None."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("connection lost")

        result = repo.find_region_by_point(40.7128, -74.0060, "borough")

        assert result is None
        mock_db.rollback.assert_called_once()


# ------------------------------------------------------------------
# list_regions — lines 196-197
# ------------------------------------------------------------------


class TestListRegions:
    """Cover the double-exception path in list_regions."""

    def test_exception_with_rollback_failure(self) -> None:
        """Lines 196-197: execute raises → rollback also raises → returns []."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback also failed")

        result = repo.list_regions("nyc")

        assert result == []
        mock_db.rollback.assert_called_once()

    def test_exception_with_rollback_success(self) -> None:
        """Primary exception path: returns empty list."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("timeout")

        result = repo.list_regions("borough", parent_region="Manhattan")

        assert result == []


# ------------------------------------------------------------------
# get_simplified_geojson_by_ids — lines 240-241
# ------------------------------------------------------------------


class TestGetSimplifiedGeojsonByIds:
    """Cover the double-exception path and empty ids."""

    def test_empty_ids_returns_empty_list(self) -> None:
        """Line 204: ids is empty → return [] immediately."""
        repo, _mock_db = _make_repo()

        result = repo.get_simplified_geojson_by_ids([])

        assert result == []

    def test_exception_with_rollback_failure(self) -> None:
        """Lines 240-241: execute raises → rollback also raises → returns []."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback also failed")

        result = repo.get_simplified_geojson_by_ids(["id_1", "id_2"])

        assert result == []
        mock_db.rollback.assert_called_once()

    def test_exception_with_rollback_success(self) -> None:
        """Primary exception path: returns empty list."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("timeout")

        result = repo.get_simplified_geojson_by_ids(["id_1"])

        assert result == []


# ------------------------------------------------------------------
# find_region_ids_by_partial_names — lines 265->251, 270-271
# ------------------------------------------------------------------


class TestFindRegionIdsByPartialNames:
    """Cover the iteration and double-exception path."""

    def test_empty_names_returns_empty_dict(self) -> None:
        """Line 248-249: names is empty → return {} immediately."""
        repo, _mock_db = _make_repo()

        result = repo.find_region_ids_by_partial_names([])

        assert result == {}

    def test_successful_lookup(self) -> None:
        """Normal path: finds regions by name."""
        repo, mock_db = _make_repo()

        row = MagicMock()
        row.__getitem__ = MagicMock(return_value="region_id_1")
        row.__bool__ = MagicMock(return_value=True)
        mock_db.execute.return_value.first.return_value = row

        result = repo.find_region_ids_by_partial_names(["Brooklyn"])

        assert "Brooklyn" in result

    def test_exception_per_name_with_rollback_failure(self) -> None:
        """Lines 270-271: per-name exception → rollback also raises → continues loop."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback also failed")

        result = repo.find_region_ids_by_partial_names(["Brooklyn", "Queens"])

        # Should return empty dict (all names failed) but not raise
        assert result == {}
        assert mock_db.rollback.call_count == 2

    def test_partial_failure_some_names_found(self) -> None:
        """Line 265->251: mixed results — some found, some fail."""
        repo, mock_db = _make_repo()

        good_row = MagicMock()
        good_row.__getitem__ = MagicMock(return_value="region_id_1")
        good_row.__bool__ = MagicMock(return_value=True)

        # First name succeeds, second name fails
        mock_db.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=good_row)),
            RuntimeError("query failed"),
        ]

        result = repo.find_region_ids_by_partial_names(["Brooklyn", "Queens"])

        assert "Brooklyn" in result
        assert "Queens" not in result


# ------------------------------------------------------------------
# delete_by_region_name — lines 298-299
# ------------------------------------------------------------------


class TestDeleteByRegionName:
    """Cover the double-exception path in delete_by_region_name."""

    def test_exception_with_rollback_failure(self) -> None:
        """Lines 298-299: execute raises → rollback also raises → returns 0."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback also failed")

        result = repo.delete_by_region_name("Brooklyn", region_type="nyc")

        assert result == 0
        mock_db.rollback.assert_called_once()

    def test_exception_with_rollback_success(self) -> None:
        """Primary exception path: returns 0."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("timeout")

        result = repo.delete_by_region_name("Brooklyn")

        assert result == 0

    def test_success_with_region_type(self) -> None:
        """Normal path with region_type provided."""
        repo, mock_db = _make_repo()

        res = MagicMock()
        res.rowcount = 2
        mock_db.execute.return_value = res

        result = repo.delete_by_region_name("Brooklyn", region_type="borough")

        assert result == 2

    def test_success_without_region_type(self) -> None:
        """Normal path without region_type."""
        repo, mock_db = _make_repo()

        res = MagicMock()
        res.rowcount = 1
        mock_db.execute.return_value = res

        result = repo.delete_by_region_name("Brooklyn")

        assert result == 1


# ------------------------------------------------------------------
# delete_by_region_code — lines 325-326
# ------------------------------------------------------------------


class TestDeleteByRegionCode:
    """Cover the double-exception path in delete_by_region_code."""

    def test_exception_with_rollback_failure(self) -> None:
        """Lines 325-326: execute raises → rollback also raises → returns 0."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback also failed")

        result = repo.delete_by_region_code("BK", region_type="nyc")

        assert result == 0
        mock_db.rollback.assert_called_once()

    def test_exception_with_rollback_success(self) -> None:
        """Primary exception path: returns 0."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("timeout")

        result = repo.delete_by_region_code("BK")

        assert result == 0

    def test_success_with_region_type(self) -> None:
        """Normal path with region_type provided."""
        repo, mock_db = _make_repo()

        res = MagicMock()
        res.rowcount = 3
        mock_db.execute.return_value = res

        result = repo.delete_by_region_code("BK", region_type="borough")

        assert result == 3

    def test_success_without_region_type(self) -> None:
        """Normal path without region_type."""
        repo, mock_db = _make_repo()

        res = MagicMock()
        res.rowcount = 1
        mock_db.execute.return_value = res

        result = repo.delete_by_region_code("BK")

        assert result == 1
