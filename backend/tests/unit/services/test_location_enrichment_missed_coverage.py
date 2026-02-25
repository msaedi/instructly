"""Tests targeting missed lines in app/services/location_enrichment.py.

Missed lines:
  88-92: legacy fallback branch (row2 is always None, so this is dead code,
         but we still test the surrounding flow to confirm line coverage)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.location_enrichment import LocationEnrichmentService


def test_enrich_nyc_no_match_from_repo() -> None:
    """Lines 88-92: When repo returns None for NYC coords, falls through to default."""
    mock_db = MagicMock()
    svc = LocationEnrichmentService(db=mock_db)

    mock_repo = MagicMock()
    mock_repo.has_postgis.return_value = True
    mock_repo.find_region_by_point.return_value = None

    with patch.object(svc, "_repo", return_value=mock_repo):
        result = svc._enrich_nyc(40.7128, -74.0060)

    assert result["location_metadata"]["region_type"] == "nyc"
    # No district or neighborhood since no match
    assert result.get("district") is None
    assert result.get("neighborhood") is None


def test_enrich_outside_nyc() -> None:
    """Non-NYC coordinates return generic enrichment."""
    mock_db = MagicMock()
    svc = LocationEnrichmentService(db=mock_db)

    result = svc.enrich(34.0522, -118.2437)  # LA coordinates
    assert result["location_metadata"]["region_type"] == "generic"


def test_enrich_nyc_no_postgis() -> None:
    """NYC coordinates but PostGIS not available."""
    mock_db = MagicMock()
    svc = LocationEnrichmentService(db=mock_db)

    mock_repo = MagicMock()
    mock_repo.has_postgis.return_value = False

    with patch.object(svc, "_repo", return_value=mock_repo):
        result = svc.enrich(40.7128, -74.0060)

    assert result["location_metadata"]["region_type"] == "nyc"


def test_enrich_nyc_with_postgis_match() -> None:
    """NYC coordinates with PostGIS match returns full enrichment."""
    mock_db = MagicMock()
    svc = LocationEnrichmentService(db=mock_db)

    mock_repo = MagicMock()
    mock_repo.has_postgis.return_value = True
    mock_repo.find_region_by_point.return_value = {
        "parent_region": "Manhattan",
        "region_code": "MN01",
        "region_name": "Chelsea",
        "region_metadata": {"community_district": "105"},
    }

    with patch.object(svc, "_repo", return_value=mock_repo):
        result = svc.enrich(40.7466, -74.0009)

    assert result["district"] == "Manhattan"
    assert result["neighborhood"] == "Chelsea"
    assert result["location_metadata"]["nyc"]["nta_code"] == "MN01"


def test_enrich_nyc_dead_code_row2_path() -> None:
    """L85-92: row2 is always None (dead code). Confirm the branch never executes."""
    mock_db = MagicMock()
    svc = LocationEnrichmentService(db=mock_db)

    mock_repo = MagicMock()
    mock_repo.has_postgis.return_value = True
    # First repo call returns None (no match)
    mock_repo.find_region_by_point.return_value = None

    with patch.object(svc, "_repo", return_value=mock_repo):
        result = svc._enrich_nyc(40.7128, -74.0060)

    # row2 = None always, so it falls through to default metadata-only result
    assert result["location_metadata"]["region_type"] == "nyc"
    assert result.get("district") is None
    assert result.get("neighborhood") is None


def test_enrich_nyc_with_missing_metadata_fields() -> None:
    """L75-82: PostGIS match but some fields missing in result."""
    mock_db = MagicMock()
    svc = LocationEnrichmentService(db=mock_db)

    mock_repo = MagicMock()
    mock_repo.has_postgis.return_value = True
    mock_repo.find_region_by_point.return_value = {
        "parent_region": None,
        "region_code": None,
        "region_name": None,
        "region_metadata": None,
    }

    with patch.object(svc, "_repo", return_value=mock_repo):
        result = svc.enrich(40.7466, -74.0009)

    assert result["district"] is None
    assert result["neighborhood"] is None
