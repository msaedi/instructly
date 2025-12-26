#!/usr/bin/env python3
"""Block ad-hoc time-to-minutes conversions."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]

PATTERNS = [
    (
        re.compile(r"\.hour\s*\*\s*60\s*\+\s*[^#\n]*\.minute"),
        "Use app.utils.time_utils.time_to_minutes() instead of ad-hoc conversions.",
    ),
    (
        re.compile(r"^\s*def\s+tmin\s*\("),
        "Do not define local tmin helpers; use time_to_minutes().",
    ),
]

ALLOWED_FILES = {
    "backend/app/utils/time_utils.py",
}


def _iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_dir():
            files.extend(path.rglob("*.py"))
        elif path.suffix == ".py":
            files.append(path)
    return files


def _is_allowed(path: Path) -> bool:
    try:
        rel_path = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return False
    return rel_path in ALLOWED_FILES


def _check_file(path: Path) -> list[str]:
    if _is_allowed(path):
        return []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: unable to read file ({exc})"]

    errors: list[str] = []
    for idx, line in enumerate(content.splitlines(), start=1):
        for pattern, message in PATTERNS:
            if pattern.search(line):
                errors.append(f"{path}:{idx}: {message}")
    return errors


def main() -> int:
    paths = [Path(arg) for arg in sys.argv[1:]]
    if not paths:
        return 0
    errors: list[str] = []
    for file_path in _iter_files(paths):
        errors.extend(_check_file(file_path))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
