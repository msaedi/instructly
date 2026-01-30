from __future__ import annotations

import pytest

from app.services.geocoding import mapbox_provider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, *_args, **_kwargs):
        return self._response


def _feature(address: str | None = "320") -> dict:
    return {
        "id": "place.123",
        "center": [-73.99, 40.73],
        "place_name": "320 East 46th Street, New York, NY 10017, United States",
        "text": "East 46th Street",
        "properties": {"address": address} if address else {},
        "context": [
            {"id": "place.1", "text": "New York"},
            {"id": "region.1", "text": "New York", "short_code": "US-NY"},
            {"id": "postcode.1", "text": "10017"},
            {"id": "country.1", "text": "United States", "short_code": "US"},
        ],
        "relevance": 0.8,
    }


@pytest.mark.asyncio
async def test_geocode_success(monkeypatch) -> None:
    resp = _FakeResponse(200, {"features": [_feature()]})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    result = await provider.geocode("320 East 46th Street")

    assert result is not None
    assert result.provider_id == "mapbox:place.123"
    assert result.city == "New York"
    assert result.state == "NY"
    assert result.postal_code == "10017"
    assert result.country == "US"


@pytest.mark.asyncio
async def test_geocode_handles_empty_results(monkeypatch) -> None:
    resp = _FakeResponse(200, {"features": []})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    assert await provider.geocode("missing") is None


@pytest.mark.asyncio
async def test_reverse_geocode_http_error(monkeypatch) -> None:
    resp = _FakeResponse(503, {})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    assert await provider.reverse_geocode(1.0, 2.0) is None


@pytest.mark.asyncio
async def test_autocomplete_builds_results(monkeypatch) -> None:
    resp = _FakeResponse(
        200,
        {
            "features": [
                {"text": "Main", "id": "place.1", "place_name": "Main St", "place_type": ["place"]}
            ]
        },
    )
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    results = await provider.autocomplete("main", country="US", location_bias={"lat": 1, "lng": 2})

    assert results
    assert results[0].place_id == "place.1"


@pytest.mark.asyncio
async def test_get_place_details_parses_leading_segment(monkeypatch) -> None:
    feature = _feature(address=None)
    feature["place_name"] = "12 Broadway, New York, NY 10017, United States"
    feature["text"] = ""
    resp = _FakeResponse(200, {"features": [feature]})

    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    result = await provider.get_place_details("mapbox:place.123")

    assert result is not None
    assert result.street_number == "12"
    assert result.street_name == "Broadway"


def test_format_and_strip_provider_id() -> None:
    assert mapbox_provider.MapboxProvider._format_provider_id("") == ""
    assert mapbox_provider.MapboxProvider._format_provider_id("place.123") == "mapbox:place.123"
    assert mapbox_provider.MapboxProvider._strip_prefix("mapbox:place.123") == "place.123"


# ============================================================================
# Additional coverage tests for missed lines
# ============================================================================


@pytest.mark.asyncio
async def test_geocode_non_200_status(monkeypatch) -> None:
    """Line 26: geocode returns None on non-200 HTTP status."""
    resp = _FakeResponse(500, {})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    result = await provider.geocode("test address")
    assert result is None


@pytest.mark.asyncio
async def test_reverse_geocode_empty_features(monkeypatch) -> None:
    """Lines 43-47: reverse_geocode returns None with empty features list."""
    resp = _FakeResponse(200, {"features": []})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    result = await provider.reverse_geocode(40.73, -73.99)
    assert result is None


@pytest.mark.asyncio
async def test_reverse_geocode_success(monkeypatch) -> None:
    """Lines 43-47: reverse_geocode returns parsed result with features."""
    resp = _FakeResponse(200, {"features": [_feature()]})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    result = await provider.reverse_geocode(40.73, -73.99)
    assert result is not None
    assert result.city == "New York"


@pytest.mark.asyncio
async def test_autocomplete_without_country_param(monkeypatch) -> None:
    """Lines 64->66: autocomplete without country parameter."""
    resp = _FakeResponse(200, {"features": [{"text": "A", "id": "p1", "place_name": "A", "place_type": []}]})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    results = await provider.autocomplete("test", country=None)
    assert results


@pytest.mark.asyncio
async def test_autocomplete_empty_country_string(monkeypatch) -> None:
    """Lines 64->66: autocomplete with empty country string."""
    resp = _FakeResponse(200, {"features": [{"text": "A", "id": "p1", "place_name": "A", "place_type": []}]})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    results = await provider.autocomplete("test", country="")
    assert results


@pytest.mark.asyncio
async def test_autocomplete_without_location_bias(monkeypatch) -> None:
    """Lines 66->71: autocomplete without location_bias."""
    resp = _FakeResponse(200, {"features": [{"text": "A", "id": "p1", "place_name": "A", "place_type": []}]})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    results = await provider.autocomplete("test", location_bias=None)
    assert results


@pytest.mark.asyncio
async def test_autocomplete_invalid_location_bias_types(monkeypatch) -> None:
    """Lines 69->71: autocomplete with invalid lat/lng types in location_bias."""
    resp = _FakeResponse(200, {"features": [{"text": "A", "id": "p1", "place_name": "A", "place_type": []}]})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    # Test with string values instead of numbers
    results = await provider.autocomplete("test", location_bias={"lat": "invalid", "lng": "invalid"})
    assert results


@pytest.mark.asyncio
async def test_autocomplete_non_200_status(monkeypatch) -> None:
    """Line 76: autocomplete returns empty list on non-200 HTTP status."""
    resp = _FakeResponse(429, {})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    results = await provider.autocomplete("test")
    assert results == []


@pytest.mark.asyncio
async def test_get_place_details_non_200_status(monkeypatch) -> None:
    """Line 100: get_place_details returns None on non-200 HTTP status."""
    resp = _FakeResponse(404, {})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    result = await provider.get_place_details("place.123")
    assert result is None


@pytest.mark.asyncio
async def test_get_place_details_empty_features(monkeypatch) -> None:
    """Line 104: get_place_details returns None with empty features."""
    resp = _FakeResponse(200, {"features": []})
    monkeypatch.setattr(mapbox_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))
    monkeypatch.setattr(mapbox_provider, "settings", type("S", (), {"mapbox_access_token": "t"})())

    provider = mapbox_provider.MapboxProvider()
    result = await provider.get_place_details("place.123")
    assert result is None


def test_parse_feature_no_regex_match_sets_street_name() -> None:
    """Lines 162-163: _parse_feature sets street_name from leading segment when no regex match."""
    feature = {
        "id": "place.123",
        "center": [-73.99, 40.73],
        "place_name": "Broadway, New York, NY 10017",  # No number prefix
        "text": "",  # Empty text forces leading segment fallback
        "properties": {},  # No address property
        "context": [
            {"id": "place.1", "text": "New York"},
            {"id": "region.1", "text": "New York", "short_code": "US-NY"},
            {"id": "country.1", "short_code": "US"},
        ],
        "relevance": 1.0,
    }
    provider = mapbox_provider.MapboxProvider()
    result = provider._parse_feature(feature)
    # When regex doesn't match (no number prefix), street_name = leading_segment
    assert result.street_name == "Broadway"
    assert result.street_number is None


def test_parse_feature_state_with_dash_prefix() -> None:
    """Lines 174-177: _parse_feature extracts state code after dash."""
    feature = {
        "id": "place.123",
        "center": [-73.99, 40.73],
        "place_name": "123 Main St, New York, NY",
        "text": "Main St",
        "properties": {"address": "123"},
        "context": [
            {"id": "place.1", "text": "New York"},
            {"id": "region.1", "text": "New York", "short_code": "US-NY"},  # Has dash
            {"id": "country.1", "short_code": "US"},
        ],
        "relevance": 1.0,
    }
    provider = mapbox_provider.MapboxProvider()
    result = provider._parse_feature(feature)
    assert result.state == "NY"


def test_parse_feature_country_with_dash_prefix() -> None:
    """Lines 182-184: _parse_feature extracts country code after dash."""
    feature = {
        "id": "place.123",
        "center": [-73.99, 40.73],
        "place_name": "123 Main St, Country",
        "text": "Main St",
        "properties": {"address": "123"},
        "context": [
            {"id": "place.1", "text": "City"},
            {"id": "region.1", "text": "State"},
            {"id": "country.1", "short_code": "XY-US"},  # Has dash
        ],
        "relevance": 1.0,
    }
    provider = mapbox_provider.MapboxProvider()
    result = provider._parse_feature(feature)
    assert result.country == "US"


def test_parse_feature_country_full_name_normalized() -> None:
    """Lines 187-192: _parse_feature normalizes full country names to ISO codes."""
    for country_name in ["United States", "United States of America", "USA"]:
        feature = {
            "id": "place.123",
            "center": [-73.99, 40.73],
            "place_name": "123 Main St",
            "text": "Main St",
            "properties": {"address": "123"},
            "context": [
                {"id": "place.1", "text": "City"},
                {"id": "country.1", "text": country_name},  # No short_code, long name
            ],
            "relevance": 1.0,
        }
        provider = mapbox_provider.MapboxProvider()
        result = provider._parse_feature(feature)
        assert result.country == "US", f"Failed for country name: {country_name}"


def test_parse_feature_country_truncation() -> None:
    """Line 192: _parse_feature truncates unknown long country names to 2 chars."""
    feature = {
        "id": "place.123",
        "center": [-73.99, 40.73],
        "place_name": "123 Main St",
        "text": "Main St",
        "properties": {"address": "123"},
        "context": [
            {"id": "place.1", "text": "City"},
            {"id": "country.1", "text": "Germany"},  # Not in US normalization list
        ],
        "relevance": 1.0,
    }
    provider = mapbox_provider.MapboxProvider()
    result = provider._parse_feature(feature)
    assert result.country == "GE"  # First 2 chars uppercased


def test_strip_prefix_without_mapbox_prefix() -> None:
    """Line 225: _strip_prefix returns original id when no mapbox: prefix."""
    assert mapbox_provider.MapboxProvider._strip_prefix("place.123") == "place.123"
    assert mapbox_provider.MapboxProvider._strip_prefix("") == ""
    assert mapbox_provider.MapboxProvider._strip_prefix("other:place.123") == "other:place.123"


def test_parse_feature_missing_center_coordinates() -> None:
    """Lines 108-109: _parse_feature handles missing center coordinates."""
    feature = {
        "id": "place.123",
        "center": [],  # Empty center
        "place_name": "Some Place",
        "text": "Place",
        "properties": {},
        "context": [],
        "relevance": 1.0,
    }
    provider = mapbox_provider.MapboxProvider()
    result = provider._parse_feature(feature)
    assert result.latitude == 0.0
    assert result.longitude == 0.0


def test_parse_feature_non_dict_context_entries() -> None:
    """Lines 112-114: _parse_feature filters out non-dict context entries."""
    feature = {
        "id": "place.123",
        "center": [-73.99, 40.73],
        "place_name": "123 Main St, New York",
        "text": "Main St",
        "properties": {"address": "123"},
        "context": [
            {"id": "place.1", "text": "New York"},
            None,  # Non-dict entry should be filtered
            "invalid",  # Non-dict entry should be filtered
            {"id": "region.1", "text": "NY"},
        ],
        "relevance": 1.0,
    }
    provider = mapbox_provider.MapboxProvider()
    result = provider._parse_feature(feature)
    assert result.city == "New York"


def test_parse_feature_numeric_house_number_and_street() -> None:
    """Lines 138-145: _parse_feature handles numeric house_number and street_name."""
    feature = {
        "id": "place.123",
        "center": [-73.99, 40.73],
        "place_name": "123 Main St",
        "text": 456,  # Numeric text
        "properties": {"address": 123},  # Numeric address
        "context": [],
        "relevance": 1.0,
    }
    provider = mapbox_provider.MapboxProvider()
    result = provider._parse_feature(feature)
    assert result.street_number == "123"
    assert result.street_name == "456"
