#!/usr/bin/env python3
"""Failing guardrail: ensure FastAPI routes declare response_model."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List

METHOD_NAMES = {"get", "post", "put", "delete", "patch"}
ROOT = Path(__file__).resolve().parents[1]
ROUTES_DIR = ROOT / "backend" / "app" / "routes"


def get_attribute_root_name(attr: ast.Attribute) -> str:
    parts = [attr.attr]
    value = attr.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value  # type: ignore[assignment]
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def main() -> int:
    missing: List[tuple[str, int, str, str]] = []

    for path in ROUTES_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            print(f"error: failed to parse {path.relative_to(ROOT)}: {exc}")
            return 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        method = decorator.func.attr
                        if method not in METHOD_NAMES:
                            continue
                        base_name = get_attribute_root_name(decorator.func)
                        if not base_name.endswith("router"):
                            continue
                        has_response_model = any(
                            kw.arg == "response_model" for kw in decorator.keywords if kw.arg
                        )
                        if not has_response_model:
                            missing.append(
                                (
                                    str(path.relative_to(ROOT)),
                                    decorator.lineno,
                                    base_name,
                                    node.name,
                                )
                            )

    if missing:
        print("route response_model check failed:")
        for file, line, router, endpoint in sorted(missing, key=lambda x: (x[0], x[1])):
            print(f"  - {file}:{line} → {router}.{endpoint} missing response_model")
        print(f"TOTAL missing decorators: {len(missing)}")
        return 1

    print("route response_model check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
