#!/usr/bin/env python3
"""
Verification script for the Clean Break Full Name Migration.

This script checks that no full_name references remain in the codebase
and that the migration has been completed successfully.
"""

import os
import re
import sys
from pathlib import Path

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def check_file_for_full_name(file_path):
    """Check a single file for full_name references."""
    violations = []

    # Skip binary files and this script itself
    if file_path.name == "verify_full_name_migration.py":
        return violations

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, 1):
            # Look for full_name patterns
            if "full_name" in line.lower():
                # Skip comments
                if "#" in line and line.strip().startswith("#"):
                    continue
                # Skip this verification script
                if "verify_full_name_migration" in line:
                    continue

                violations.append({"file": str(file_path), "line": line_num, "content": line.strip()})

    except (UnicodeDecodeError, PermissionError):
        # Skip binary files or files we can't read
        pass

    return violations


def check_directory(directory):
    """Recursively check all Python and HTML files in a directory."""
    all_violations = []

    # Define file extensions to check
    extensions = [".py", ".html", ".jinja2", ".txt", ".yaml", ".yml"]

    # Directories to skip
    skip_dirs = ["venv", "__pycache__", ".git", "node_modules", ".pytest_cache", "logs", "archive"]

    for root, dirs, files in os.walk(directory):
        # Skip if current path contains '/archive' anywhere
        if "/archive" in root:
            continue

        # Remove skip directories from dirs to prevent recursion
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            file_path = Path(root) / file

            # Check if file has an extension we care about
            if any(str(file_path).endswith(ext) for ext in extensions):
                violations = check_file_for_full_name(file_path)
                all_violations.extend(violations)

    return all_violations


def check_combined_names(directory):
    """Check for incorrect patterns where names are combined."""
    pattern_violations = []

    # Patterns that indicate incorrect name combinations
    bad_patterns = [
        (r'f["\'].*\{.*first_name.*\}.*\{.*last_name.*\}', "f-string combining names"),
        (r"first_name.*\+.*last_name", "concatenating names with +"),
        (r"\.join.*first_name.*last_name", "joining names"),
        (r"first_name.*\|\|.*last_name", "SQL concatenation"),
    ]

    for root, dirs, files in os.walk(directory):
        # Skip if current path contains '/archive' anywhere
        if "/archive" in root:
            continue

        # Skip unwanted directories
        dirs[:] = [d for d in dirs if d not in ["venv", "__pycache__", ".git", "node_modules", "archive"]]

        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file

                # Skip this script
                if file_path.name == "verify_full_name_migration.py":
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        lines = content.split("\n")

                    for pattern, description in bad_patterns:
                        for line_num, line in enumerate(lines, 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                # Skip comments
                                if "#" in line and line.strip().startswith("#"):
                                    continue

                                pattern_violations.append(
                                    {
                                        "file": str(file_path),
                                        "line": line_num,
                                        "pattern": description,
                                        "content": line.strip(),
                                    }
                                )

                except (UnicodeDecodeError, PermissionError):
                    pass

    return pattern_violations


def main():
    """Main verification function."""
    print("\n" + "=" * 60)
    print("Full Name Migration Verification")
    print("=" * 60)

    # Get the backend directory
    backend_dir = Path(__file__).parent.parent
    app_dir = backend_dir / "app"
    alembic_dir = backend_dir / "alembic"

    print(f"\nChecking directories:")
    print(f"  - {app_dir}")
    print(f"  - {alembic_dir}")

    # Check for full_name references
    print(f"\n{YELLOW}Checking for 'full_name' references...{RESET}")
    violations = []
    violations.extend(check_directory(app_dir))
    violations.extend(check_directory(alembic_dir))

    if violations:
        print(f"\n{RED}✗ Found {len(violations)} full_name references:{RESET}")
        for v in violations[:10]:  # Show first 10
            print(f"  {v['file']}:{v['line']}")
            print(f"    {v['content']}")
        if len(violations) > 10:
            print(f"  ... and {len(violations) - 10} more")
    else:
        print(f"{GREEN}✓ No full_name references found!{RESET}")

    # Check for combined name patterns
    print(f"\n{YELLOW}Checking for combined name patterns...{RESET}")
    pattern_violations = check_combined_names(app_dir)

    # Filter out false positives
    filtered_violations = []
    for v in pattern_violations:
        # Skip SQL migration files where concatenation might be legitimate
        if "005_performance_indexes.py" in v["file"] and "SQL concatenation" in v["pattern"]:
            continue
        # Skip test files that might be testing the old behavior
        if "test_" in v["file"]:
            continue
        filtered_violations.append(v)

    if filtered_violations:
        print(f"\n{RED}✗ Found {len(filtered_violations)} incorrect name combinations:{RESET}")
        for v in filtered_violations[:5]:  # Show first 5
            print(f"  {v['file']}:{v['line']} ({v['pattern']})")
            print(f"    {v['content']}")
        if len(filtered_violations) > 5:
            print(f"  ... and {len(filtered_violations) - 5} more")
    else:
        print(f"{GREEN}✓ No incorrect name combinations found!{RESET}")

    # Summary
    print(f"\n{'='*60}")
    total_issues = len(violations) + len(filtered_violations)

    if total_issues == 0:
        print(f"{GREEN}✓ SUCCESS: Migration verified! No issues found.{RESET}")
        print("\nNext steps:")
        print("1. Run the test suite to ensure everything works")
        print("2. Test the application end-to-end")
        print("3. Commit your changes")
        return 0
    else:
        print(f"{RED}✗ FAILED: Found {total_issues} issues that need to be fixed.{RESET}")
        print("\nPlease fix the violations listed above and run this script again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
