from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.services.geocoding import factory


def test_create_geocoding_provider_selects_mapbox_and_mock(monkeypatch) -> None:
    monkeypatch.setattr(
        factory,
        "settings",
        SimpleNamespace(geocoding_provider="google"),
    )

    with patch.object(factory, "MapboxProvider", return_value="mapbox-provider"):
        with patch.object(factory, "MockGeocodingProvider", return_value="mock-provider"):
            assert factory.create_geocoding_provider("mapbox") == "mapbox-provider"
            assert factory.create_geocoding_provider("mock") == "mock-provider"


def test_create_geocoding_provider_falls_back_to_google_for_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        factory,
        "settings",
        SimpleNamespace(geocoding_provider="unsupported"),
    )

    with patch.object(factory, "GoogleMapsProvider", return_value="google-provider"):
        assert factory.create_geocoding_provider() == "google-provider"
