"""Factory for geocoding providers."""

from ...core.config import settings
from .base import GeocodingProvider
from .google_provider import GoogleMapsProvider
from .mapbox_provider import MapboxProvider
from .mock_provider import MockGeocodingProvider


def create_geocoding_provider() -> GeocodingProvider:
    name = (settings.geocoding_provider or "google").lower()
    provider: GeocodingProvider
    if name == "google":
        provider = GoogleMapsProvider()
    elif name == "mapbox":
        provider = MapboxProvider()
    elif name == "mock":
        provider = MockGeocodingProvider()
    else:
        provider = GoogleMapsProvider()
    return provider
