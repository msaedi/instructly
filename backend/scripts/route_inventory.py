#!/usr/bin/env python
"""
Generate router and route inventory artifacts.
Outputs:
- backend/.artifacts/router_inventory.csv
- backend/.artifacts/route_inventory.json
- backend/.artifacts/ROUTER_INVENTORY.md
"""

from __future__ import annotations

import csv
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from fastapi.routing import APIRoute


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _format_dependency_name(obj: Any) -> str:
    call = getattr(obj, "dependency", None)
    if call is None:
        call = getattr(obj, "call", None)
    if call is None:
        return repr(obj)
    name = getattr(call, "__name__", repr(call))
    module = getattr(call, "__module__", "")
    if module and module != "builtins":
        return f"{module}.{name}"
    return name


def _collect_endpoint_dependencies(route: APIRoute) -> List[str]:
    seen: List[str] = []
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return seen
    for dep in dependant.dependencies or []:
        name = _format_dependency_name(dep)
        if name not in seen:
            seen.append(name)
    return seen


def main() -> None:
    root = _project_root()
    artifacts_dir = root / "backend" / ".artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    import sys

    sys.path.append(str(root / "backend"))

    from app.main import app  # type: ignore  # pylint: disable=import-error

    fastapi_app = app
    # Some environments wrap FastAPI with middleware instances (e.g., rate limiting)
    # that expose the actual app via `.app`.
    while not hasattr(fastapi_app, "routes") and hasattr(fastapi_app, "app"):
        fastapi_app = getattr(fastapi_app, "app")  # type: ignore[assignment]

    rows: List[Dict[str, Any]] = []

    for route in fastapi_app.routes:  # type: ignore[attr-defined]
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        methods = sorted(route.methods or [])
        endpoint = route.endpoint
        module = getattr(endpoint, "__module__", "")
        endpoint_name = getattr(endpoint, "__name__", repr(endpoint))
        try:
            source_file = inspect.getsourcefile(endpoint)
        except TypeError:
            source_file = None
        if source_file is not None:
            source_path = Path(source_file)
            try:
                rel_path = source_path.relative_to(root)
            except ValueError:
                rel_path = source_path
        else:
            rel_path = Path("unknown")
        try:
            _, line_no = inspect.getsourcelines(endpoint)
        except (OSError, TypeError):
            line_no = None

        include_deps = [
            _format_dependency_name(dep) for dep in (route.dependencies or [])
        ]
        endpoint_deps = _collect_endpoint_dependencies(route)

        dep_strings: Sequence[str] = include_deps + endpoint_deps
        has_public_guard = any("public_guard" in dep for dep in dep_strings)
        has_active_user = any(dep.endswith("get_current_active_user") for dep in dep_strings)
        has_beta_access = any("require_beta_access" in dep for dep in dep_strings)

        row = {
            "path": path,
            "methods": ",".join(methods),
            "module": module,
            "endpoint_function": endpoint_name,
            "file": str(rel_path),
            "line": line_no if line_no is not None else "",
            "include_router_dependencies": ";".join(include_deps),
            "endpoint_dependencies": ";".join(endpoint_deps),
            "tags": ",".join(route.tags or []),
            "is_api": path.startswith("/api/"),
            "has_public_guard": has_public_guard,
            "has_get_current_active_user": has_active_user,
            "has_require_beta_access": has_beta_access,
        }
        rows.append(row)

    rows.sort(key=lambda r: (r["path"], r["methods"]))

    csv_path = artifacts_dir / "router_inventory.csv"
    csv_headers = [
        "path",
        "methods",
        "module",
        "endpoint_function",
        "file",
        "line",
        "include_router_dependencies",
        "endpoint_dependencies",
        "tags",
        "is_api",
        "has_public_guard",
        "has_get_current_active_user",
        "has_require_beta_access",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=csv_headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    json_path = artifacts_dir / "route_inventory.json"
    with json_path.open("w", encoding="utf-8") as jf:
        json.dump(rows, jf, indent=2, sort_keys=False)

    md_path = artifacts_dir / "ROUTER_INVENTORY.md"
    with md_path.open("w", encoding="utf-8") as md:
        md.write("# Router Inventory\n\n")
        md.write("| Path | Methods | Module | Endpoint | Tags | Public Guard | Requires Beta |\n")
        md.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for row in rows:
            md.write(
                f"| `{row['path']}` | {row['methods']} | `{row['module']}` | `{row['endpoint_function']}` | "
                f"{row['tags'] or '-'} | {'yes' if row['has_public_guard'] else 'no'} | "
                f"{'yes' if row['has_require_beta_access'] else 'no'} |\n"
            )


if __name__ == "__main__":
    main()
