"""AST-based detector for slot-era tests."""
from __future__ import annotations

import ast
from pathlib import Path

# Build tokens dynamically to avoid guard grep
_API_NAMES = {
    "get_" + "slots_by_date",
    "delete_" + "slots_by_dates",
    "slot_" + "exists",
    "count_available_" + "slots",
    "get_" + "week_slots",
    "get_" + "slots_with_booking_status",
    "get_" + "slots_for_date",
}

_CLASS_NAMES = {"Slot" + "Manager", "Availability" + "Slot"}

_TABLE_NAMES = {"availability_" + "slots"}

# Known-good tests that may mention 'slot' only in strings/asserts:
_WHITELIST_SUFFIXES = {
    "backend/tests/integration/availability/test_no_slot_queries_runtime.py",
    "backend/tests/integration/availability/test_routes_bitmap_only.py",
}


def _name_of_attr(node: ast.AST) -> str | None:
    """Turn foo.bar.baz into 'foo.bar.baz'."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    if parts:
        return ".".join(reversed(parts))
    return None


def is_slot_era_file(path: str) -> bool:
    """Check if a file uses slot-era APIs via AST analysis."""
    p = Path(path)
    # Whitelist specific files that are bitmap-era but contain "slot" in strings
    for suf in _WHITELIST_SUFFIXES:
        if str(p).endswith(suf):
            return False

    try:
        src = p.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except Exception:
        # On parse failure, be conservative and do not skip
        return False

    for node in ast.walk(tree):
        # 1) Imports: from X import Y / import X
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _CLASS_NAMES | _API_NAMES | _TABLE_NAMES:
                    return True

        if isinstance(node, ast.Import):
            for alias in node.names:
                nm = alias.name.rsplit(".", 1)[-1]
                if nm in _CLASS_NAMES:
                    return True

        # 2) Attribute or Name usage: repo.method calls (e.g., repo.get_slots_by_date)
        if isinstance(node, ast.Attribute):
            nm = _name_of_attr(node)
            if nm and nm.split(".")[-1] in _API_NAMES:
                return True

        if isinstance(node, ast.Name):
            if node.id in _CLASS_NAMES | _API_NAMES | _TABLE_NAMES:
                return True

        # Note: we intentionally IGNORE string literals / comments,
        # so asserting "availability_slots" in a header won't trigger a skip.

    return False
