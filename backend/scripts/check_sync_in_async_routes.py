#!/usr/bin/env python3
"""
Pre-commit guard: prevent sync service calls in async route handlers.

Why:
- Sync service calls in async routes block the event loop.
- Many sync services use CacheServiceSyncAdapter, which no-ops on a running event loop,
  causing cache invalidations/sets/deletes to be silently skipped.

Fix:
- Wrap sync service calls with: await asyncio.to_thread(service.method, *args, **kwargs)
- Or make the route handler `def` (FastAPI runs sync handlers in a threadpool).
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from typing import Iterable, List, Tuple

from hook_config import is_excluded_legacy_route

ROUTE_DECORATORS = {
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "options",
    "head",
    "api_route",
    "websocket",
}

SAFE_WRAPPERS = {
    "asyncio.to_thread",
    "run_in_threadpool",
    "anyio.to_thread.run_sync",
}

EXTRA_SYNC_NAMES = {
    # Used widely as a sync dependency but doesn't follow *_service naming.
    "conflict_checker",
}

ASYNC_SERVICE_NAMES = {
    # Async cache service methods must be awaited; do not force thread offload.
    "cache_service",
}


def _is_route_handler(node: ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if isinstance(func, ast.Attribute) and func.attr in ROUTE_DECORATORS:
            return True
    return False


def _call_name(node: ast.Call) -> str:
    try:
        if isinstance(node.func, ast.Attribute):
            parts: list[str] = []
            current: ast.AST = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        if isinstance(node.func, ast.Name):
            return node.func.id
    except Exception:
        return ""
    return ""


def _is_sync_service_name(name: str) -> bool:
    if name in EXTRA_SYNC_NAMES:
        return True
    if name in ASYNC_SERVICE_NAMES:
        return False
    return name.endswith("_service")


class SyncInAsyncRouteVisitor(ast.NodeVisitor):
    def __init__(self, filename: str, source_lines: List[str]):
        self.filename = filename
        self.source_lines = source_lines
        self.violations: List[Tuple[int, str]] = []
        self._stack: list[ast.AST] = []
        self._in_route_handler = False
        self._route_handler_name = ""
        self._safe_wrapper_depth = 0

    def visit(self, node: ast.AST):  # type: ignore[override]
        self._stack.append(node)
        try:
            return super().visit(node)
        finally:
            self._stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        is_route = _is_route_handler(node)
        old_in_route = self._in_route_handler
        old_name = self._route_handler_name
        if is_route:
            self._in_route_handler = True
            self._route_handler_name = node.name
        self.generic_visit(node)
        self._in_route_handler = old_in_route
        self._route_handler_name = old_name

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Nested sync defs inside async routes are commonly used as helpers for to_thread.
        old_in_route = self._in_route_handler
        old_name = self._route_handler_name
        self._in_route_handler = False
        self._route_handler_name = ""
        self.generic_visit(node)
        self._in_route_handler = old_in_route
        self._route_handler_name = old_name

    def visit_Call(self, node: ast.Call):
        if not self._in_route_handler:
            self.generic_visit(node)
            return

        call_name = _call_name(node)

        # Treat calls inside thread offload wrappers as safe (covers lambda/partial patterns).
        if call_name in SAFE_WRAPPERS:
            self._safe_wrapper_depth += 1
            self.generic_visit(node)
            self._safe_wrapper_depth -= 1
            return

        if self._safe_wrapper_depth > 0:
            self.generic_visit(node)
            return

        # Skip calls that are explicitly awaited (assumed to be async methods).
        parent = self._stack[-2] if len(self._stack) >= 2 else None
        if isinstance(parent, ast.Await):
            self.generic_visit(node)
            return

        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            base_name = node.func.value.id
            if _is_sync_service_name(base_name):
                source = ""
                if 0 < node.lineno <= len(self.source_lines):
                    source = self.source_lines[node.lineno - 1].strip()
                if "async-blocking-ignore" in source.lower():
                    self.generic_visit(node)
                    return
                self.violations.append(
                    (
                        node.lineno,
                        f"Sync call `{base_name}.{node.func.attr}()` in async route "
                        f"`{self._route_handler_name}()`: wrap in `await asyncio.to_thread(...)`",
                    )
                )

        self.generic_visit(node)


def _check_file(path: Path) -> List[Tuple[str, int, str]]:
    try:
        content = path.read_text()
        source_lines = content.splitlines()
        tree = ast.parse(content)
    except SyntaxError:
        return []
    except Exception as e:
        return [(str(path), 1, f"Error reading/parsing file: {e}")]

    visitor = SyncInAsyncRouteVisitor(str(path), source_lines)
    visitor.visit(tree)
    return [(str(path), line, msg) for line, msg in visitor.violations]


def main(argv: List[str]) -> int:
    routes_dir = Path("backend/app/routes")
    if not routes_dir.exists():
        print("No routes directory found at backend/app/routes", file=sys.stderr)
        return 0

    paths: Iterable[Path] = routes_dir.rglob("*.py")
    violations: List[Tuple[str, int, str]] = []
    files_checked = 0
    files_excluded = 0

    for path in paths:
        if is_excluded_legacy_route(str(path)):
            files_excluded += 1
            continue
        files_checked += 1
        violations.extend(_check_file(path))

    print("\n" + "=" * 60)
    print("Sync-in-Async Route Check")
    print("=" * 60)
    print(f"Files checked:  {files_checked}")
    print(f"Files excluded: {files_excluded} (legacy routes with v1 counterparts)")

    if violations:
        print(f"Violations:     {len(violations)}")
        print("=" * 60)
        print(
            "\nSync service calls in async route handlers must be offloaded with asyncio.to_thread()\n"
        )
        for filepath, line, msg in violations:
            print(f"  {filepath}:{line}")
            print(f"    {msg}")
        print("\nFix example:")
        print("  result = await asyncio.to_thread(service.method, arg1, kw=value)")
        return 1

    print("Violations:     0")
    print("=" * 60)
    print("\nNo sync-in-async route violations found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
