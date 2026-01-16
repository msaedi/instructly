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
