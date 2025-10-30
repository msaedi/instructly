# backend/scripts/dev/list_routes.py
"""
List FastAPI routes with authentication metadata.

Outputs a markdown-friendly table detailing method, path, handler, and any
attached dependencies that appear related to auth/roles/scopes.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import List, Tuple

from fastapi.applications import FastAPI
from fastapi.routing import APIRoute

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def format_dependency(dep: object) -> str:
    target = getattr(dep, "dependency", None) or dep
    if hasattr(target, "__module__") and hasattr(target, "__name__"):
        return f"{target.__module__}.{target.__name__}"
    if hasattr(target, "__class__"):
        cls = target.__class__
        return f"{cls.__module__}.{cls.__name__}"
    return repr(target)


def _unwrap_app(app: FastAPI) -> FastAPI:
    current = app
    max_depth = 10
    depth = 0
    while not hasattr(current, "routes") and hasattr(current, "app") and depth < max_depth:
        current = getattr(current, "app")
        depth += 1
    if not hasattr(current, "routes"):
        raise RuntimeError("Unable to unwrap FastAPI application from middleware stack")
    return current  # type: ignore[return-value]


def collect_route_info(app: FastAPI) -> List[Tuple[str, str, str, List[str]]]:
    fastapi_app = _unwrap_app(app)
    rows: List[Tuple[str, str, str, List[str]]] = []
    for route in fastapi_app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(route.methods or [])
        path = route.path
        endpoint = route.endpoint

        handler_name = f"{endpoint.__module__}.{endpoint.__name__}"

        deps: List[str] = []
        for dep in route.dependant.dependencies:
            deps.append(format_dependency(dep.call))
        rows.append((",".join(methods), path, handler_name, deps))
    return rows


def classify_path(path: str, handler: str) -> str:
    if path.startswith("/admin") or ".admin_" in handler or "/internal" in path:
        return "admin/internal"
    if path.startswith("/internal") or "internal" in handler:
        return "admin/internal"
    return "public"


def main() -> None:
    from app.main import app  # type: ignore

    rows = collect_route_info(app)
    print("| Method(s) | Path | Handler | Auth Dependencies | Section |")
    print("|-----------|------|---------|--------------------|---------|")
    for methods, path, handler, deps in sorted(rows, key=lambda r: (r[1], r[0])):
        deps_str = "<br/>".join(deps) if deps else "—"
        section = classify_path(path, handler)
        print(f"| {methods} | {path} | `{handler}` | {deps_str} | {section} |")


if __name__ == "__main__":
    main()
