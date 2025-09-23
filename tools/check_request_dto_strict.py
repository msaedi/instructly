#!/usr/bin/env python3
"""Failing guardrail: ensure request DTOs stay strict-friendly."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List

REQUEST_SUFFIXES = (
    "Request",
    "Create",
    "Update",
    "Confirm",
    "Reset",
    "Verify",
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "backend" / "app" / "schemas"


def get_base_names(node: ast.ClassDef) -> List[str]:
    names: List[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            parts: List[str] = []
            current = base
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value  # type: ignore[assignment]
            if isinstance(current, ast.Name):
                parts.append(current.id)
            names.append(".".join(reversed(parts)))
    return names


def has_dual_mode_config(node: ast.ClassDef) -> bool:
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "model_config":
                    value = stmt.value
                    if isinstance(value, ast.Attribute):
                        parts: List[str] = []
                        current = value
                        while isinstance(current, ast.Attribute):
                            parts.append(current.attr)
                            current = current.value  # type: ignore[assignment]
                        if isinstance(current, ast.Name):
                            parts.append(current.id)
                        dotted = ".".join(reversed(parts))
                        if "StrictRequestModel" in dotted:
                            return True
                    elif isinstance(value, ast.Name):
                        if "StrictRequestModel" in value.id:
                            return True
                    elif isinstance(value, ast.Call):
                        call = value
                        func = call.func
                        if (
                            isinstance(func, ast.Attribute)
                            and isinstance(func.value, ast.Name)
                            and func.value.id == "StrictRequestModel"
                        ):
                            return True
                        if isinstance(func, ast.Name) and func.id == "ConfigDict":
                            for keyword in call.keywords:
                                if keyword.arg == "extra":
                                    expr = keyword.value
                                    if isinstance(expr, ast.IfExp) and hasattr(ast, "unparse"):
                                        text = ast.unparse(expr)
                                        if (
                                            "STRICT" in text
                                            and "forbid" in text
                                            and "ignore" in text
                                        ):
                                            return True
    return False


def main() -> int:
    offenders: list[tuple[str, str, List[str]]] = []
    total = 0

    for path in SCHEMAS_DIR.rglob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            print(f"error: failed to parse {path.relative_to(ROOT)}: {exc}")
            return 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith(REQUEST_SUFFIXES):
                total += 1
                bases = get_base_names(node)
                inherits_strict = any("StrictRequestModel" in base for base in bases)
                if inherits_strict or has_dual_mode_config(node):
                    continue
                offenders.append(
                    (
                        str(path.relative_to(ROOT)),
                        node.name,
                        bases,
                    )
                )

    if offenders:
        print("request DTO strict check failed:")
        for file, cls, bases in offenders:
            print(f"  - {file}: class {cls} bases={bases}")
        print(f"TOTAL offenders: {len(offenders)} out of {total} request-like classes")
        return 1

    print(f"request DTO strict check passed for {total} request-like classes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
