from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.geocoding import google_provider
from app.services.geocoding.base import GeocodingProviderError


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, params: dict | None = None):
        self.calls.append((url, params or {}))
        return self._response


def _patch_settings(monkeypatch, *, google_key: str = "key", mapbox_token: str = "") -> None:
    monkeypatch.setattr(
        google_provider,
        "settings",
        SimpleNamespace(google_maps_api_key=google_key, mapbox_access_token=mapbox_token),
    )


def _sample_google_result() -> dict:
    return {
        "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
        "place_id": "abcd",
        "geometry": {"location": {"lat": 37.422, "lng": -122.084}},
        "address_components": [
            {"long_name": "1600", "short_name": "1600", "types": ["street_number"]},
            {
                "long_name": "Amphitheatre Parkway",
                "short_name": "Amphitheatre Pkwy",
                "types": ["route"],
            },
            {"long_name": "Mountain View", "short_name": "Mountain View", "types": ["locality"]},
            {"long_name": "California", "short_name": "CA", "types": ["administrative_area_level_1"]},
            {"long_name": "94043", "short_name": "94043", "types": ["postal_code"]},
            {"long_name": "United States", "short_name": "US", "types": ["country"]},
        ],
    }


@pytest.mark.asyncio
async def test_geocode_success(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "OK", "results": [_sample_google_result()]})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    result = await provider.geocode("1600 Amphitheatre Pkwy")

    assert result is not None
    assert result.provider_id == "google:abcd"
    assert result.country == "US"
    assert result.state == "CA"
    assert result.city == "Mountain View"


@pytest.mark.asyncio
async def test_geocode_zero_results(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "ZERO_RESULTS", "results": []})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    assert await provider.geocode("nope") is None


@pytest.mark.asyncio
async def test_geocode_http_error(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(429, {})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    with pytest.raises(GeocodingProviderError) as exc:
        await provider.geocode("addr")

    assert exc.value.status == "HTTP_429"


@pytest.mark.asyncio
async def test_reverse_geocode_error_status(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "REQUEST_DENIED", "error_message": "bad key"})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    with pytest.raises(GeocodingProviderError) as exc:
        await provider.reverse_geocode(1.0, 2.0)

    assert exc.value.status == "REQUEST_DENIED"


@pytest.mark.asyncio
async def test_autocomplete_fallback_to_mapbox(monkeypatch) -> None:
    _patch_settings(monkeypatch, mapbox_token="token")
    resp = _FakeResponse(200, {"status": "REQUEST_DENIED", "predictions": []})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    class _Fallback:
        async def autocomplete(self, *_args, **_kwargs):
            return [SimpleNamespace(text="Main", place_id="mbx", description="desc", types=[])]

    monkeypatch.setattr(google_provider, "MapboxProvider", _Fallback)

    provider = google_provider.GoogleMapsProvider()
    results = await provider.autocomplete("main st")

    assert results
    assert results[0].place_id == "mbx"


@pytest.mark.asyncio
async def test_autocomplete_no_fallback(monkeypatch) -> None:
    _patch_settings(monkeypatch, mapbox_token="")
    resp = _FakeResponse(200, {"status": "REQUEST_DENIED", "predictions": []})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    results = await provider.autocomplete("main st")

    assert results == []


@pytest.mark.asyncio
async def test_get_place_details_filters_zero_coords(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(
        200,
        {
            "result": {
                "formatted_address": "Somewhere",
                "place_id": "pid",
                "geometry": {"location": {"lat": 0.0, "lng": 0.0}},
                "address_components": [],
            }
        },
    )
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    assert await provider.get_place_details("google:pid") is None


@pytest.mark.asyncio
async def test_geocode_ok_empty_results(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "OK", "results": []})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    assert await provider.geocode("empty") is None


@pytest.mark.asyncio
async def test_reverse_geocode_ok_empty_results(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "OK", "results": []})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    assert await provider.reverse_geocode(1.0, 2.0) is None


@pytest.mark.asyncio
async def test_autocomplete_builds_results_and_params(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(
        200,
        {
            "status": "OK",
            "predictions": [
                {
                    "place_id": "p1",
                    "description": "Main St",
                    "types": ["address"],
                    "structured_formatting": {"main_text": "Main"},
                }
            ],
        },
    )
    client = _FakeAsyncClient(resp)
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: client)

    provider = google_provider.GoogleMapsProvider()
    results = await provider.autocomplete(
        "main",
        session_token="sess",
        country="US",
        location_bias={"lat": 40.0, "lng": -73.0, "radius_m": "bad"},
    )

    assert results
    assert results[0].place_id == "p1"
    _, params = client.calls[0]
    assert params["sessiontoken"] == "sess"
    assert params["components"] == "country:us"
    assert params["locationbias"].startswith("circle:50000@40.0,-73.0")


@pytest.mark.asyncio
async def test_autocomplete_http_error(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    resp = _FakeResponse(500, {})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    assert await provider.autocomplete("main") == []


@pytest.mark.asyncio
async def test_get_place_details_success(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    payload = _sample_google_result()
    resp = _FakeResponse(200, {"result": payload})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    result = await provider.get_place_details("google:abcd")

    assert result is not None
    assert result.provider_id == "google:abcd"


def test_format_and_strip_provider_id() -> None:
    assert google_provider.GoogleMapsProvider._format_provider_id("") == ""
    assert google_provider.GoogleMapsProvider._format_provider_id("pid") == "google:pid"
    assert google_provider.GoogleMapsProvider._strip_prefix("google:pid") == "pid"


# ============================================================================
# Additional coverage tests for missed lines
# ============================================================================


@pytest.mark.asyncio
async def test_geocode_error_status_raises(monkeypatch) -> None:
    """Line 47: geocode raises GeocodingProviderError on error status."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "INVALID_REQUEST", "error_message": "bad request"})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    with pytest.raises(GeocodingProviderError) as exc:
        await provider.geocode("invalid")

    assert exc.value.status == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_reverse_geocode_http_error(monkeypatch) -> None:
    """Line 61: reverse_geocode raises on non-200 HTTP status."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(500, {})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    with pytest.raises(GeocodingProviderError) as exc:
        await provider.reverse_geocode(40.7, -74.0)

    assert exc.value.status == "HTTP_500"


@pytest.mark.asyncio
async def test_reverse_geocode_ok_with_results(monkeypatch) -> None:
    """Lines 73, 75: reverse_geocode returns parsed result when OK with results."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "OK", "results": [_sample_google_result()]})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    result = await provider.reverse_geocode(37.422, -122.084)

    assert result is not None
    assert result.city == "Mountain View"
    assert result.state == "CA"


@pytest.mark.asyncio
async def test_reverse_geocode_zero_results(monkeypatch) -> None:
    """Line 75: reverse_geocode returns None on ZERO_RESULTS status."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "ZERO_RESULTS", "results": []})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    result = await provider.reverse_geocode(0.0, 0.0)
    assert result is None


@pytest.mark.asyncio
async def test_autocomplete_location_bias_valid_radius(monkeypatch) -> None:
    """Lines 101->107: autocomplete with valid numeric radius in location_bias."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "OK", "predictions": []})
    client = _FakeAsyncClient(resp)
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: client)

    provider = google_provider.GoogleMapsProvider()
    await provider.autocomplete(
        "main",
        location_bias={"lat": 40.0, "lng": -73.0, "radius_m": 10000},
    )

    _, params = client.calls[0]
    assert params["locationbias"] == "circle:10000@40.0,-73.0"


@pytest.mark.asyncio
async def test_autocomplete_location_bias_small_radius_enforces_minimum(monkeypatch) -> None:
    """Lines 101->107: autocomplete enforces minimum radius of 1000."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"status": "OK", "predictions": []})
    client = _FakeAsyncClient(resp)
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: client)

    provider = google_provider.GoogleMapsProvider()
    await provider.autocomplete(
        "main",
        location_bias={"lat": 40.0, "lng": -73.0, "radius_m": 100},  # Less than 1000
    )

    _, params = client.calls[0]
    assert params["locationbias"] == "circle:1000@40.0,-73.0"


@pytest.mark.asyncio
async def test_get_place_details_http_error(monkeypatch) -> None:
    """Line 154: get_place_details returns None on non-200 HTTP status."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(500, {})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    result = await provider.get_place_details("google:pid")
    assert result is None


@pytest.mark.asyncio
async def test_get_place_details_no_result_in_response(monkeypatch) -> None:
    """Line 158: get_place_details returns None when no result in response."""
    _patch_settings(monkeypatch)
    resp = _FakeResponse(200, {"result": None})
    monkeypatch.setattr(google_provider.httpx, "AsyncClient", lambda **_kw: _FakeAsyncClient(resp))

    provider = google_provider.GoogleMapsProvider()
    result = await provider.get_place_details("google:pid")
    assert result is None


def test_parse_result_address_component_with_short_name() -> None:
    """Lines 174->176, 176->173: _parse_result extracts short_name from components."""
    result_data = {
        "formatted_address": "123 Main St",
        "place_id": "test",
        "geometry": {"location": {"lat": 40.7, "lng": -74.0}},
        "address_components": [
            {"long_name": "123", "short_name": "123", "types": ["street_number"]},
            {"long_name": "Main Street", "short_name": "Main St", "types": ["route"]},
            {"long_name": "New York", "short_name": "NY", "types": ["administrative_area_level_1"]},
            {"long_name": "United States", "short_name": "US", "types": ["country"]},
        ],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)

    assert result.state == "NY"  # Uses short_name
    assert result.country == "US"  # Uses short_name (2 chars)


def test_parse_result_country_normalization_long_name() -> None:
    """Lines 187-190: _parse_result normalizes long country names to ISO codes."""
    for country_name in ["United States", "United States of America", "USA"]:
        result_data = {
            "formatted_address": "123 Main St",
            "place_id": "test",
            "geometry": {"location": {"lat": 40.7, "lng": -74.0}},
            "address_components": [
                {"long_name": country_name, "short_name": country_name, "types": ["country"]},
            ],
        }
        provider = google_provider.GoogleMapsProvider()
        result = provider._parse_result(result_data)
        assert result.country == "US", f"Failed for country name: {country_name}"


def test_parse_result_country_truncation() -> None:
    """Lines 187-190: _parse_result truncates unknown long country names."""
    result_data = {
        "formatted_address": "123 Main St",
        "place_id": "test",
        "geometry": {"location": {"lat": 51.5, "lng": -0.1}},
        "address_components": [
            {
                "long_name": "United Kingdom",
                "short_name": "United Kingdom",  # Long short_name (unusual)
                "types": ["country"],
            },
        ],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)
    assert result.country == "UN"  # First 2 chars uppercased


def test_parse_result_city_fallback_to_postal_town() -> None:
    """Line 203: _parse_result uses postal_town as city fallback."""
    result_data = {
        "formatted_address": "123 Main St, London",
        "place_id": "test",
        "geometry": {"location": {"lat": 51.5, "lng": -0.1}},
        "address_components": [
            {"long_name": "London", "short_name": "London", "types": ["postal_town"]},
            {"long_name": "GB", "short_name": "GB", "types": ["country"]},
        ],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)
    assert result.city == "London"


def test_parse_result_city_fallback_to_sublocality() -> None:
    """Line 203: _parse_result uses sublocality as city fallback."""
    result_data = {
        "formatted_address": "123 Main St, Brooklyn",
        "place_id": "test",
        "geometry": {"location": {"lat": 40.6, "lng": -73.9}},
        "address_components": [
            {"long_name": "Brooklyn", "short_name": "Brooklyn", "types": ["sublocality"]},
            {"long_name": "US", "short_name": "US", "types": ["country"]},
        ],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)
    assert result.city == "Brooklyn"


def test_strip_prefix_without_google_prefix() -> None:
    """Line 224: _strip_prefix returns original id when no google: prefix."""
    assert google_provider.GoogleMapsProvider._strip_prefix("pid") == "pid"
    assert google_provider.GoogleMapsProvider._strip_prefix("") == ""
    assert google_provider.GoogleMapsProvider._strip_prefix("other:pid") == "other:pid"


def test_parse_result_with_empty_address_components() -> None:
    """Test _parse_result handles empty address_components gracefully."""
    result_data = {
        "formatted_address": "Somewhere",
        "place_id": "test",
        "geometry": {"location": {"lat": 0.0, "lng": 0.0}},
        "address_components": [],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)

    assert result.street_number is None
    assert result.street_name is None
    assert result.city is None


def test_parse_result_uses_address_component_key() -> None:
    """Line 169: _parse_result supports alternate address_component key."""
    result_data = {
        "formatted_address": "123 Main St",
        "place_id": "test",
        "geometry": {"location": {"lat": 40.7, "lng": -74.0}},
        "address_component": [  # Note: singular form
            {"long_name": "123", "short_name": "123", "types": ["street_number"]},
        ],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)
    assert result.street_number == "123"


def test_parse_result_missing_geometry() -> None:
    """Lines 178-179: _parse_result handles missing geometry."""
    result_data = {
        "formatted_address": "123 Main St",
        "place_id": "test",
        "address_components": [],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)

    assert result.latitude == 0.0
    assert result.longitude == 0.0


def test_parse_result_country_two_char_long_name() -> None:
    """Lines 187-188: _parse_result handles 2-char long_name without short_name."""
    result_data = {
        "formatted_address": "123 Main St",
        "place_id": "test",
        "geometry": {"location": {"lat": 40.7, "lng": -74.0}},
        "address_components": [
            {
                "long_name": "us",  # 2-char long_name
                "short_name": "",  # Empty short_name (will be filtered)
                "types": ["country"],
            },
        ],
    }
    provider = google_provider.GoogleMapsProvider()
    result = provider._parse_result(result_data)
    assert result.country == "US"  # Should be uppercased
