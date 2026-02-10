from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.routes.v1 import prometheus as routes


def _make_request(query: str = "") -> Request:
    scope = {
        "type": "http",
        "query_string": query.encode(),
        "headers": [],
        "path": "/api/v1/metrics/prometheus",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_cache_enabled_respects_env(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_DISABLE_CACHE", "1")

    assert routes._cache_enabled() is False


def test_cache_enabled_in_tests_can_disable(monkeypatch):
    monkeypatch.delenv("PROMETHEUS_DISABLE_CACHE", raising=False)
    monkeypatch.setattr(routes.settings, "environment", "test", raising=False)
    monkeypatch.setenv("PROMETHEUS_CACHE_IN_TESTS", "0")

    assert routes._cache_enabled() is False


def test_get_cached_metrics_payload_uses_cache(monkeypatch):
    calls = {"count": 0}

    def _get_metrics():
        calls["count"] += 1
        return b"fresh"

    monkeypatch.setattr(routes, "prometheus_metrics", SimpleNamespace(get_metrics=_get_metrics))
    monkeypatch.setattr(routes, "_cache_enabled", lambda: True)
    monkeypatch.setattr(routes, "monotonic", lambda: 10.0)

    routes._metrics_cache = (10.0, b"cached")

    assert routes._get_cached_metrics_payload() == b"cached"
    assert calls["count"] == 0


def test_get_cached_metrics_payload_refreshes(monkeypatch):
    calls = {"count": 0}

    def _get_metrics():
        calls["count"] += 1
        return b"fresh"

    monkeypatch.setattr(routes, "prometheus_metrics", SimpleNamespace(get_metrics=_get_metrics))
    monkeypatch.setattr(routes, "_cache_enabled", lambda: True)
    monkeypatch.setattr(routes, "monotonic", lambda: 10.0)

    routes._metrics_cache = (0.0, b"old")

    assert routes._get_cached_metrics_payload() == b"fresh"
    assert calls["count"] == 1


def test_refresh_scrape_counter_line_handles_bad_payload():
    assert routes._refresh_scrape_counter_line(b"\xff") == b"\xff"
    assert routes._refresh_scrape_counter_line(b"no metrics") == b"no metrics"


def test_refresh_scrape_counter_line_updates():
    routes.SCRAPE_COUNT = 7
    payload = b"instainstru_prometheus_scrapes_total 1\nother 2\n"

    updated = routes._refresh_scrape_counter_line(payload)

    assert b"instainstru_prometheus_scrapes_total 7" in updated


def test_warm_cache_no_cache(monkeypatch):
    monkeypatch.setattr(routes, "_cache_enabled", lambda: False)

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "prometheus_metrics", SimpleNamespace(get_metrics=_boom))

    routes.warm_prometheus_metrics_response_cache()


def test_get_cached_metrics_payload_without_cache(monkeypatch):
    monkeypatch.setattr(routes, "_cache_enabled", lambda: False)
    monkeypatch.setattr(routes, "prometheus_metrics", SimpleNamespace(get_metrics=lambda: b"fresh-no-cache"))

    routes._metrics_cache = None
    payload = routes._get_cached_metrics_payload()
    assert payload == b"fresh-no-cache"


def test_warm_cache_when_disabled_and_metrics_succeeds(monkeypatch):
    monkeypatch.setattr(routes, "_cache_enabled", lambda: False)
    monkeypatch.setattr(routes, "prometheus_metrics", SimpleNamespace(get_metrics=lambda: b"ok"))

    routes.warm_prometheus_metrics_response_cache()
    assert routes._metrics_cache is None


def test_warm_cache_enabled_handles_metrics_generation_error(monkeypatch):
    monkeypatch.setattr(routes, "_cache_enabled", lambda: True)

    def _boom():
        raise RuntimeError("metrics-boom")

    monkeypatch.setattr(routes, "prometheus_metrics", SimpleNamespace(get_metrics=_boom))
    routes._metrics_cache = None

    routes.warm_prometheus_metrics_response_cache()
    assert routes._metrics_cache is None


@pytest.mark.asyncio
async def test_get_prometheus_metrics_refresh(monkeypatch):
    monkeypatch.setattr(routes, "_get_cached_metrics_payload", lambda force_refresh=False: b"instainstru_prometheus_scrapes_total 0\n")
    monkeypatch.setattr(routes, "prometheus_metrics", SimpleNamespace(get_content_type=lambda: "text/plain"))
    routes.SCRAPE_COUNT = 0

    request = _make_request("refresh=true")
    response = await routes.get_prometheus_metrics(request)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert b"instainstru_prometheus_scrapes_total 1" in response.body
