from __future__ import annotations

from fastapi.routing import APIRoute

from app.main import app


def _fastapi_app():
    current = app
    visited = set()
    while hasattr(current, "app") and getattr(current, "routes", None) is None:
        visited.add(id(current))
        current = getattr(current, "app")
        if id(current) in visited:
            break
    return current

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ALLOW_NON_API_PREFIXES = (
    "/auth",
    "/api/public",
    "/services/",
    "/health",
    "/internal",
    "/ops/",
    "/webhooks/",
    "/api/v1/bookings",
    "/beta",
    "/stripe",
    "/instructors",
    "/metrics",
)


def test_mutating_routes_use_api_prefix() -> None:
    violations: list[tuple[str, tuple[str, ...]]] = []
    fastapi_app = _fastapi_app()
    for route in fastapi_app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        methods = route.methods or set()
        if not path or not methods:
            continue
        if MUTATING_METHODS.isdisjoint(methods):
            continue
        if path.startswith("/api/"):
            continue
        if any(path.startswith(prefix) for prefix in ALLOW_NON_API_PREFIXES):
            continue
        violations.append((path, tuple(sorted(methods))))
    assert not violations, f"Mutating routes must live under /api/: {violations}"
