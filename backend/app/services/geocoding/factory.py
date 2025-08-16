"""Factory for geocoding providers."""

from ...core.config import settings
from .base import GeocodingProvider
from .google_provider import GoogleMapsProvider
from .mapbox_provider import MapboxProvider
from .mock_provider import MockGeocodingProvider


def create_geocoding_provider() -> GeocodingProvider:
    name = (settings.geocoding_provider or "google").lower()
    if name == "google":
        return GoogleMapsProvider()
    if name == "mapbox":
        return MapboxProvider()
    if name == "mock":
        return MockGeocodingProvider()
    # default fallback
    return GoogleMapsProvider()
