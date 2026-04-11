#!/usr/bin/env python3
"""Shared graphify rebuild helper for git hooks."""

from __future__ import annotations

import os
from pathlib import Path

CODE_EXTS = {
    ".py",
    ".ts",
    ".js",
    ".go",
    ".rs",
    ".java",
    ".cpp",
    ".c",
    ".rb",
    ".swift",
    ".kt",
    ".cs",
    ".scala",
    ".php",
    ".cc",
    ".cxx",
    ".hpp",
    ".h",
    ".kts",
}


def _changed_paths() -> list[Path]:
    changed_raw = os.environ.get("GRAPHIFY_CHANGED", "")
    return [Path(path.strip()) for path in changed_raw.splitlines() if path.strip()]


def main() -> int:
    try:
        from graphify.watch import _rebuild_code
    except ModuleNotFoundError:
        print("[graphify hook] graphify not installed, skipping rebuild")
        return 0

    changed = _changed_paths()
    if not changed:
        return 0

    code_existing = [path for path in changed if path.suffix.lower() in CODE_EXTS and path.exists()]
    code_deleted = [path for path in changed if path.suffix.lower() in CODE_EXTS and not path.exists()]

    if not code_existing and not code_deleted:
        return 0

    parts: list[str] = []
    if code_existing:
        parts.append(f"{len(code_existing)} modified")
    if code_deleted:
        parts.append(f"{len(code_deleted)} deleted")

    total = len(code_existing) + len(code_deleted)
    print(
        f"[graphify hook] {total} code file(s) changed "
        f"({', '.join(parts)}) - rebuilding graph..."
    )

    try:
        _rebuild_code(Path("."))
    except Exception as exc:
        print(f"[graphify hook] Rebuild failed: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
