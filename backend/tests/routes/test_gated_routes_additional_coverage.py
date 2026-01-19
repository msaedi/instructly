from __future__ import annotations

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from app.routes.v1 import gated as routes


def _make_request(query: str = "") -> Request:
    scope = {
        "type": "http",
        "query_string": query.encode(),
        "headers": [],
        "path": "/api/v1/gated/ping",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_enforce_no_query_params_allows_empty():
    request = _make_request()

    routes._enforce_no_query_params(request)


def test_enforce_no_query_params_rejects_query():
    request = _make_request("foo=bar")

    with pytest.raises(HTTPException) as exc:
        routes._enforce_no_query_params(request)

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_gated_ping_returns_ok():
    response = await routes.gated_ping(_strict=None)

    assert response.ok is True
