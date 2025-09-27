#!/usr/bin/env python3
"""
Pre-commit guard to enforce @BaseService.measure_operation usage on service methods.

Rules:
- Inspect classes that inherit from BaseService
- For each public method (non-dunder, not starting with underscore), ensure it is decorated
  with @BaseService.measure_operation("<operation_name>")
- Allow explicit opt-out by placing "# no-metrics" on the function definition line
- Skip trivial/property-like methods (decorated with @property or @cached_property)

Usage:
- Pre-commit passes changed files as argv. If none are passed, script scans default services dir.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable, List

SERVICES_DIR = Path("backend/app/services")


def _is_baseservice_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        # Handle both BaseService and app.services.base.BaseService forms
        if isinstance(base, ast.Name) and base.id == "BaseService":
            return True
        if isinstance(base, ast.Attribute):
            # Walk attribute chain to see if it ends with BaseService
            attr = base
            while isinstance(attr, ast.Attribute):
                if attr.attr == "BaseService":
                    return True
                attr = attr.value  # type: ignore[assignment]
            if isinstance(attr, ast.Name) and attr.id == "BaseService":
                return True
    return False


def _has_measure_decorator(func: ast.AST) -> bool:
    decorator_list = getattr(func, "decorator_list", [])
    for dec in decorator_list:
        # Match @BaseService.measure_operation("...")
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            if dec.func.attr == "measure_operation":
                # Ensure qualifier is BaseService
                value = dec.func.value
                if isinstance(value, ast.Name) and value.id == "BaseService":
                    return True
                if isinstance(value, ast.Attribute):
                    # Allow something like app.services.base.BaseService.measure_operation
                    attr = value
                    while isinstance(attr, ast.Attribute):
                        if attr.attr == "BaseService":
                            return True
                        attr = attr.value  # type: ignore[assignment]
                    if isinstance(attr, ast.Name) and attr.id == "BaseService":
                        return True
        # Do NOT accept bare @measure_operation — we want the canonical decorator
    return False


def _has_property_like_decorator(func: ast.AST) -> bool:
    decorator_list = getattr(func, "decorator_list", [])
    for dec in decorator_list:
        if isinstance(dec, ast.Name) and dec.id in {"property", "cached_property"}:
            return True
        if isinstance(dec, ast.Attribute) and dec.attr in {"setter", "deleter"}:
            return True
    return False


def _has_no_metrics_opt_out(source_lines: List[str], func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    try:
        # Look at function def line only for opt-out marker
        line = source_lines[func.lineno - 1]
        return "# no-metrics" in line
    except Exception:
        return False


def _iter_service_methods(tree: ast.AST) -> Iterable[tuple[ast.ClassDef, ast.AST]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_baseservice_class(node):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield node, item


def check_file(path: Path) -> List[str]:
    errors: List[str] = []
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [f"{path}:0: unable to read file: {exc}"]

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno or 0}: syntax error: {exc.msg}"]

    lines = source.splitlines()

    for cls, func in _iter_service_methods(tree):
        func_name = getattr(func, "name", "<unknown>")
        # Skip dunder and private methods
        if func_name.startswith("__") and func_name.endswith("__"):
            continue
        if func_name.startswith("_"):
            continue
        # Skip property-like methods
        if _has_property_like_decorator(func):
            continue
        # Allow explicit opt-out
        if _has_no_metrics_opt_out(lines, func):
            continue
        # Enforce decorator
        if not _has_measure_decorator(func):
            lineno = getattr(func, "lineno", 0)
            class_name = getattr(cls, "name", "<Service>")
            errors.append(
                f"{path}:{lineno}: public service method '{class_name}.{func_name}' missing @BaseService.measure_operation(\"...\")"
            )

    return errors


def collect_files_from_argv(argv: List[str]) -> List[Path]:
    if argv:
        return [Path(a) for a in argv if a.endswith(".py")]
    # Fallback: scan services dir
    if SERVICES_DIR.exists():
        return [p for p in SERVICES_DIR.rglob("*.py")]
    return []


def main(argv: List[str]) -> int:
    files = collect_files_from_argv(argv)
    all_errors: List[str] = []
    for f in files:
        # Only check files within services directory
        try:
            _rel = f.relative_to(SERVICES_DIR)
        except Exception:
            # Skip files outside services dir
            continue
        all_errors.extend(check_file(f))

    if all_errors:
        print("\n".join(all_errors))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
