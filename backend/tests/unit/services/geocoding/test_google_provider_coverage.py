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
