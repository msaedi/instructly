#!/usr/bin/env python3
"""
Helper script to add migration markers to existing repository pattern violations.
This is a one-time script to mark all current violations for migration.
"""

import json
from pathlib import Path
import sys


def add_migration_markers():
    """Add migration markers to all violations listed in the JSON file."""

    violations_file = Path("repository_violations_to_mark.json")
    if not violations_file.exists():
        print("❌ No violations file found. Run 'python scripts/check_repository_pattern.py --generate-markers' first")
        return False

    with open(violations_file, "r") as f:
        data = json.load(f)

    violations_by_file = {}
    for violation in data["violations"]:
        file_path = violation["file"]
        if file_path not in violations_by_file:
            violations_by_file[file_path] = []
        violations_by_file[file_path].append(violation["line"])

    marked_count = 0
    for file_path, line_numbers in violations_by_file.items():
        # Sort line numbers in reverse to avoid offset issues when inserting
        line_numbers.sort(reverse=True)

        full_path = Path(file_path)
        if not full_path.exists():
            print(f"⚠️  File not found: {file_path}")
            continue

        with open(full_path, "r") as f:
            lines = f.readlines()

        modified = False
        for line_num in line_numbers:
            # Line numbers are 1-based, array is 0-based
            idx = line_num - 1
            if idx < len(lines):
                # Check if already marked
                if idx > 0 and "repo-pattern" in lines[idx - 1]:
                    continue

                # Add marker with proper indentation
                indent = len(lines[idx]) - len(lines[idx].lstrip())
                marker = " " * indent + "# repo-pattern-migrate: TODO: Migrate to repository pattern\n"
                lines.insert(idx, marker)
                marked_count += 1
                modified = True

        if modified:
            with open(full_path, "w") as f:
                f.writelines(lines)
            print(f"✅ Marked {len([n for n in line_numbers])} violations in {file_path}")

    print(f"\n📊 Summary: Marked {marked_count} violations for migration")
    return True


def main():
    """Main entry point."""
    print("🔧 Adding Migration Markers to Repository Pattern Violations")
    print("=" * 60)

    if add_migration_markers():
        print("\n✅ Success! All violations have been marked.")
        print("You can now commit these files with the pre-commit hook enabled.")
        print("\nNext steps:")
        print("1. Review the marked violations")
        print("2. Gradually migrate them to use repositories")
        print("3. Remove the markers as you fix each violation")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
