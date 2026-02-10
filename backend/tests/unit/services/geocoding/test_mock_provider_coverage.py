from __future__ import annotations

import pytest

from app.services.geocoding.mock_provider import MockGeocodingProvider


@pytest.mark.asyncio
async def test_reverse_geocode_returns_requested_coordinates():
    provider = MockGeocodingProvider()

    result = await provider.reverse_geocode(40.71, -74.01)

    assert result is not None
    assert result.latitude == 40.71
    assert result.longitude == -74.01
    assert result.provider_id == "mock:reverse"
