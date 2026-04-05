#!/usr/bin/env python3
"""Ensure runtime and OpenAPI apps use the shared router registry."""

from __future__ import annotations

import ast
from pathlib import Path
import sys


def _load_tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _has_named_import(tree: ast.AST, module_suffix: str, symbol: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if not module.endswith(module_suffix):
            continue
        if any(alias.name == symbol for alias in node.names):
            return True
    return False


def _has_named_call(tree: ast.AST, symbol: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == symbol:
            return True
    return False


def _contains_inline_router_registration(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    return "api_v1.include_router(" in content


def _validate_usage(
    path: Path,
    *,
    module_suffix: str,
    import_name: str,
    call_name: str,
) -> list[str]:
    tree = _load_tree(path)
    errors: list[str] = []
    if not _has_named_import(tree, module_suffix, import_name):
        errors.append(f"{path.name} must import {import_name} from {module_suffix}")
    if not _has_named_call(tree, call_name):
        errors.append(f"{path.name} must call {call_name}(app)")
    if _contains_inline_router_registration(path):
        errors.append(f"{path.name} should not contain inline api_v1.include_router(...) calls")
    return errors


def main() -> int:
    backend_dir = Path(__file__).resolve().parent.parent
    main_py = backend_dir / "app" / "main.py"
    openapi_py = backend_dir / "app" / "openapi_app.py"

    errors: list[str] = []
    errors.extend(
        _validate_usage(
            main_py,
            module_suffix="core.router_registry",
            import_name="register_all_routers",
            call_name="register_all_routers",
        )
    )
    errors.extend(
        _validate_usage(
            openapi_py,
            module_suffix="core.router_registry",
            import_name="register_openapi_routers",
            call_name="register_openapi_routers",
        )
    )

    if errors:
        print("❌ Router registry wiring mismatch:\n")
        for error in errors:
            print(f"- {error}")
        return 1

    print("✅ Runtime and OpenAPI apps both use app.core.router_registry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
