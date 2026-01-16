from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routes.v1.admin import search_config as routes
from app.schemas.nl_search import AdminSearchConfigUpdate


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(
        parsing_model="parse-1",
        parsing_timeout_ms=1500,
        embedding_model="embed-1",
        embedding_timeout_ms=2000,
        location_model="loc-1",
        location_timeout_ms=1800,
        search_budget_ms=3500,
        high_load_budget_ms=2500,
        high_load_threshold=12,
        uncached_concurrency=3,
        max_retries=2,
    )


def test_build_admin_search_config_response(monkeypatch):
    config = _make_config()
    monkeypatch.setattr(routes, "get_search_config", lambda: config)
    monkeypatch.setattr(
        routes,
        "AVAILABLE_PARSING_MODELS",
        [{"id": "p1", "name": "Parser", "description": "parser"}],
        raising=False,
    )
    monkeypatch.setattr(
        routes,
        "AVAILABLE_EMBEDDING_MODELS",
        [{"id": "e1", "name": "Embed", "description": "embed"}],
        raising=False,
    )

    response = routes._build_admin_search_config_response()

    assert response.parsing_model == "parse-1"
    assert response.embedding_model == "embed-1"
    assert response.available_parsing_models[0].id == "p1"
    assert response.available_embedding_models[0].id == "e1"


@pytest.mark.asyncio
async def test_get_search_config_admin_sets_inflight(monkeypatch):
    config = _make_config()
    monkeypatch.setattr(routes, "get_search_config", lambda: config)
    async def _inflight():
        return 7

    monkeypatch.setattr(routes, "get_search_inflight_count", _inflight)
    monkeypatch.setattr(routes, "AVAILABLE_PARSING_MODELS", [], raising=False)
    monkeypatch.setattr(routes, "AVAILABLE_EMBEDDING_MODELS", [], raising=False)

    response = await routes.get_search_config_admin(_=None)

    assert response.current_in_flight_requests == 7


@pytest.mark.asyncio
async def test_update_search_config_admin_updates_and_sets_limit(monkeypatch):
    updated = _make_config()
    updated.uncached_concurrency = 9

    monkeypatch.setattr(routes, "update_search_config", lambda **_kwargs: updated)
    async def _inflight():
        return 2

    monkeypatch.setattr(routes, "get_search_inflight_count", _inflight)
    monkeypatch.setattr(routes, "AVAILABLE_PARSING_MODELS", [], raising=False)
    monkeypatch.setattr(routes, "AVAILABLE_EMBEDDING_MODELS", [], raising=False)

    called = {}

    async def _set_limit(value):
        called["value"] = value

    monkeypatch.setattr(routes, "set_uncached_search_concurrency_limit", _set_limit)

    payload = AdminSearchConfigUpdate(uncached_concurrency=9)
    response = await routes.update_search_config_admin(payload, _=None)

    assert response.uncached_concurrency == 9
    assert called["value"] == 9


@pytest.mark.asyncio
async def test_reset_search_config_admin_always_sets_limit(monkeypatch):
    config = _make_config()
    config.uncached_concurrency = 4

    monkeypatch.setattr(routes, "reset_search_config", lambda: config)
    async def _inflight():
        return 1

    monkeypatch.setattr(routes, "get_search_inflight_count", _inflight)
    monkeypatch.setattr(routes, "AVAILABLE_PARSING_MODELS", [], raising=False)
    monkeypatch.setattr(routes, "AVAILABLE_EMBEDDING_MODELS", [], raising=False)

    called = {}

    async def _set_limit(value):
        called["value"] = value

    monkeypatch.setattr(routes, "set_uncached_search_concurrency_limit", _set_limit)

    response = await routes.reset_search_config_admin(_=None)

    assert response.uncached_concurrency == 4
    assert called["value"] == 4
