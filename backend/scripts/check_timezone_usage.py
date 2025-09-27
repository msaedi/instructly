#!/usr/bin/env python3
"""
Pre-commit hook to prevent date.today() usage in user-facing code.

This script checks for instances of date.today() in user-facing code paths
and suggests using get_user_today_by_id() instead.
"""

from pathlib import Path
import re
import sys

# Files/directories that are allowed to use date.today()
ALLOWED_PATTERNS = [
    "cache_service.py",  # Cache TTL management
    "logging_service.py",  # System logs
    "metrics_service.py",  # System metrics
    "test_",  # Test files
    "__pycache__",  # Compiled files
]

# Patterns to detect timezone-unaware date usage
DATE_TODAY_PATTERN = re.compile(r"date\.today\(\)")
DATETIME_NOW_DATE_PATTERN = re.compile(r"datetime\.now\(\)\.date\(\)")
DATETIME_UTCNOW_PATTERN = re.compile(r"datetime\.utcnow\(\)")
DATETIME_NOW_NAIVE_PATTERN = re.compile(r"datetime\.now\(\)\s*[<>]|[<>]\s*datetime\.now\(\)")

# Pattern to check if timezone utilities are imported
TIMEZONE_IMPORT_PATTERN = re.compile(r"from\s+.*timezone_utils\s+import|import\s+.*timezone_utils")


def is_allowed_file(filepath: Path) -> bool:
    """Check if the file is allowed to use date.today()."""
    for pattern in ALLOWED_PATTERNS:
        if pattern in str(filepath):
            return True
    return False


def check_file(filepath: Path) -> list:
    """
    Check a single file for date.today() usage.

    Returns a list of violations with line numbers.
    """
    if is_allowed_file(filepath):
        return []

    violations = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Check if file imports timezone utilities
        has_timezone_import = bool(TIMEZONE_IMPORT_PATTERN.search(content))

        # Find all timezone-unaware date/time usage
        for line_num, line in enumerate(content.splitlines(), 1):
            has_violation = False
            violation_text = ""
            suggestion = "get_user_today_by_id(user_id, db)"

            if DATE_TODAY_PATTERN.search(line):
                has_violation = True
                violation_text = "date.today()"
            elif DATETIME_NOW_DATE_PATTERN.search(line):
                has_violation = True
                violation_text = "datetime.now().date()"
            elif DATETIME_UTCNOW_PATTERN.search(line):
                has_violation = True
                violation_text = "datetime.utcnow()"
                suggestion = "datetime.now(timezone.utc)"
            elif DATETIME_NOW_NAIVE_PATTERN.search(line):
                has_violation = True
                violation_text = "datetime.now() comparison"
                suggestion = "datetime.now(timezone.utc) for comparisons"

            if has_violation:
                # Check if it's in a comment
                if "#" in line and violation_text in line and line.index("#") < line.index(violation_text):
                    continue

                # Check for known acceptable patterns
                if "system_" in line.lower() or "reference" in line.lower():
                    # This is likely a system reference, check surrounding context
                    continue

                # Check if it's in a string
                if line.count('"') >= 2 or line.count("'") >= 2:
                    # Simple check - might have false positives
                    in_string = False
                    quote_positions = []
                    for i, char in enumerate(line):
                        if char in ['"', "'"]:
                            quote_positions.append(i)

                    date_pos = line.index(violation_text)
                    for i in range(0, len(quote_positions), 2):
                        if i + 1 < len(quote_positions):
                            if quote_positions[i] < date_pos < quote_positions[i + 1]:
                                in_string = True
                                break

                    if in_string:
                        continue

                violations.append(
                    {
                        "line": line_num,
                        "code": line.strip(),
                        "has_timezone_import": has_timezone_import,
                        "suggestion": suggestion,
                    }
                )

    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []

    return violations


def main():
    """Main function to check all files passed as arguments."""
    if len(sys.argv) < 2:
        # No files to check
        return 0

    all_violations = []

    for filepath_str in sys.argv[1:]:
        filepath = Path(filepath_str)
        if filepath.is_file() and filepath.suffix == ".py":
            violations = check_file(filepath)
            if violations:
                all_violations.append((filepath, violations))

    if all_violations:
        print("\n❌ Found timezone-unaware date usage in user-facing code!\n")
        print("User operations must use timezone-aware functions.\n")

        for filepath, violations in all_violations:
            print(f"File: {filepath}")
            for v in violations:
                print(f"  Line {v['line']}: {v['code']}")
                if v["suggestion"] == "get_user_today_by_id(user_id, db)" and not v["has_timezone_import"]:
                    print("    💡 Add: from app.core.timezone_utils import get_user_today_by_id")
                elif v["suggestion"] == "datetime.now(timezone.utc)":
                    print("    💡 Add: from datetime import timezone")
                print(f"    💡 Use: {v['suggestion']} instead")
            print()

        print("Please update your code to use timezone-aware date functions.")
        print("See docs/development/timezone-handling.md for more information.\n")

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
