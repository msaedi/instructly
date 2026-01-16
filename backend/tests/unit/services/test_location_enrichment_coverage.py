from __future__ import annotations

from types import SimpleNamespace

from app.services.location_enrichment import LocationEnrichmentService


def test_detect_region_nyc_bounds() -> None:
    service = LocationEnrichmentService(SimpleNamespace())

    assert service.detect_region(40.7, -74.0) == "nyc"
    assert service.detect_region(42.0, -75.0) is None


def test_enrich_nyc_without_postgis(monkeypatch) -> None:
    service = LocationEnrichmentService(SimpleNamespace())

    class DummyRepo:
        def has_postgis(self) -> bool:
            return False

    monkeypatch.setattr(service, "_repo", lambda: DummyRepo())

    result = service.enrich(40.7, -74.0)

    assert result["location_metadata"]["region_type"] == "nyc"


def test_enrich_nyc_with_match(monkeypatch) -> None:
    service = LocationEnrichmentService(SimpleNamespace())

    class DummyRepo:
        def has_postgis(self) -> bool:
            return True

        def find_region_by_point(self, _lat, _lng, region_type=None):
            return {
                "parent_region": "Manhattan",
                "region_code": "MN01",
                "region_name": "Chelsea",
                "region_metadata": {"community_district": "4"},
            }

    monkeypatch.setattr(service, "_repo", lambda: DummyRepo())

    result = service.enrich(40.7, -74.0)

    assert result["district"] == "Manhattan"
    assert result["neighborhood"] == "Chelsea"
    assert result["location_metadata"]["nyc"]["community_district"] == "4"


def test_enrich_generic_region(monkeypatch) -> None:
    service = LocationEnrichmentService(SimpleNamespace())

    result = service.enrich(10.0, 10.0)

    assert result["location_metadata"]["region_type"] == "generic"
