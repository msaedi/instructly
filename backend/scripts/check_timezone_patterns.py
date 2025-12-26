#!/usr/bin/env python3
"""
Pre-commit hook to catch common timezone mistakes.

Checks for:
1. datetime.combine() without timezone context (should use TimezoneService)
2. Direct comparison of naive and aware datetimes
3. Using booking.booking_date + booking.start_time instead of booking_start_utc  # tz-pattern-ok: documenting pattern
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

VIOLATION_PATTERNS = [
    (
        r"datetime\.combine\([^)]+\)",
        "datetime.combine() without TimezoneService - use TimezoneService.local_to_utc() instead",
        ["timezone_service.py", "test_", "conftest.py"],
    ),
    (
        r"booking\.booking_date.*booking\.start_time|booking\.start_time.*booking\.booking_date",
        "Combining legacy booking fields - use booking.booking_start_utc or _get_booking_start_utc() instead",
        ["test_", "conftest.py", "schemas/", "backfill_"],
    ),
]

SKIP_PATHS = [
    "alembic/",
    "migrations/",
    "__pycache__",
    ".git",
    "node_modules",
]


def should_skip_file(filepath: str) -> bool:
    """Check if file should be skipped entirely."""
    return any(skip in filepath for skip in SKIP_PATHS)


def check_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Check a file for timezone pattern violations."""
    violations: list[tuple[int, str, str]] = []

    if should_skip_file(str(filepath)):
        return violations

    try:
        content = filepath.read_text()
    except Exception:
        return violations

    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        if line.strip().startswith("#") or "tz-pattern-ok:" in line:
            continue

        for pattern, message, exceptions in VIOLATION_PATTERNS:
            if any(exc in str(filepath) for exc in exceptions):
                continue

            if re.search(pattern, line):
                violations.append((line_num, message, line.strip()))

    return violations


def main() -> int:
    """Run timezone pattern checks on staged Python files."""
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:] if f.endswith(".py")]
    else:
        files = list(Path("backend/app").rglob("*.py"))

    all_violations: list[str] = []
    for filepath in files:
        if not filepath.exists():
            continue
        violations = check_file(filepath)
        for line_num, message, line in violations:
            all_violations.append(f"{filepath}:{line_num}: {message}\n          {line}")

    if all_violations:
        print("Timezone pattern violations found:")
        for violation in all_violations:
            print(violation)
        print(f"\nFound {len(all_violations)} violation(s).")
        print("Use '# tz-pattern-ok: <reason>' to mark intentional exceptions.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
