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
# find_region_ids_by_partial_names — batched lookup and rollback path
# ------------------------------------------------------------------


class TestFindRegionIdsByPartialNames:
    """Cover the batched lookup behavior and double-exception path."""

    def test_empty_names_returns_empty_dict(self) -> None:
        """Line 248-249: names is empty → return {} immediately."""
        repo, _mock_db = _make_repo()

        result = repo.find_region_ids_by_partial_names([])

        assert result == {}

    def test_successful_lookup_batches_names_in_one_query(self) -> None:
        """Normal path: finds multiple regions with a single execute call."""
        repo, mock_db = _make_repo()

        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = [
            {"partial_name": "Brooklyn", "id": "region_id_1"},
            {"partial_name": "Queens", "id": "region_id_2"},
        ]
        mock_db.execute.return_value = execute_result

        result = repo.find_region_ids_by_partial_names(["Brooklyn", "Queens"])

        assert result == {"Brooklyn": "region_id_1", "Queens": "region_id_2"}
        mock_db.execute.assert_called_once()

    def test_unmatched_names_are_omitted(self) -> None:
        """Only matched partial names are returned in the mapping."""
        repo, mock_db = _make_repo()

        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = [
            {"partial_name": "Brooklyn", "id": "region_id_1"},
        ]
        mock_db.execute.return_value = execute_result

        result = repo.find_region_ids_by_partial_names(["Brooklyn", "Queens"])

        assert result == {"Brooklyn": "region_id_1"}

    def test_exception_with_rollback_failure(self) -> None:
        """Execute raises → rollback also raises → returns empty dict."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback also failed")

        result = repo.find_region_ids_by_partial_names(["Brooklyn", "Queens"])

        assert result == {}
        mock_db.rollback.assert_called_once()


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


# ------------------------------------------------------------------
# get_all_active_polygons_geojson — lines 318-323
# ------------------------------------------------------------------


class TestGetAllActivePolygonsGeojson:
    """Cover exception path with double rollback failure."""

    def test_exception_with_rollback_failure(self) -> None:
        """Lines 318-323: execute raises → rollback also raises → returns []."""
        repo, mock_db = _make_repo()

        mock_db.execute.side_effect = RuntimeError("query failed")
        mock_db.rollback.side_effect = RuntimeError("rollback failed")

        result = repo.get_all_active_polygons_geojson(region_type="nyc")

        assert result == []
        mock_db.rollback.assert_called_once()


# ------------------------------------------------------------------
# find_region_ids_by_partial_names — rows with missing fields (line 346)
# ------------------------------------------------------------------


class TestFindRegionIdsByPartialNamesMissingFields:
    def test_rows_with_missing_partial_name_or_id_filtered(self) -> None:
        """Rows where partial_name or id is None/empty are excluded (line 366)."""
        repo, mock_db = _make_repo()

        execute_result = MagicMock()
        execute_result.mappings.return_value.all.return_value = [
            {"partial_name": "Brooklyn", "id": "region_id_1"},
            {"partial_name": None, "id": "region_id_2"},
            {"partial_name": "Queens", "id": None},
            {"partial_name": "", "id": "region_id_3"},
        ]
        mock_db.execute.return_value = execute_result

        result = repo.find_region_ids_by_partial_names(["Brooklyn", "Queens"])
        assert result == {"Brooklyn": "region_id_1"}


# ------------------------------------------------------------------
# resolve_display_keys_to_ids — non-PostgreSQL dialect (lines 395-406)
# ------------------------------------------------------------------


class TestResolveDisplayKeysNonPostgres:
    def test_non_postgresql_dialect_uses_expanding_bindparam(self) -> None:
        """Non-PostgreSQL dialect → IN :keys with expanding bindparam (lines 395-406)."""
        repo, mock_db = _make_repo()

        # Set dialect to sqlite (non-PostgreSQL)
        mock_db.bind.dialect.name = "sqlite"

        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([
            MagicMock(display_key="dk1", id="id1"),
            MagicMock(display_key="dk1", id="id2"),
        ]))
        mock_db.execute.return_value = execute_result

        result = repo.resolve_display_keys_to_ids(["dk1"])
        assert "dk1" in result
        assert len(result["dk1"]) == 2
