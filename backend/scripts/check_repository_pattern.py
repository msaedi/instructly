#!/usr/bin/env python3
"""
Repository Pattern Violation Checker

Ensures that service files don't make direct database queries and only use repositories.
Similar to check_api_contracts.py and check_timezone_consistency.py

Supports inline markers for legitimate DB access:
  # repo-pattern-ignore: Legitimate reason
  # repo-pattern-migrate: TODO: Will be fixed in migration
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Patterns that indicate direct database access
VIOLATION_PATTERNS = [
    r"self\.db\.query\(",
    r"self\.db\.add\(",
    r"self\.db\.delete\(",
    r"self\.db\.execute\(",
    r"self\.db\.flush\(",
    r"self\.db\.commit\(",
    r"self\.db\.rollback\(",
    r"self\.db\.refresh\(",
    r"self\.db\.merge\(",
    r"db\.query\(",  # For utilities like timezone_utils
]

# Additional patterns for query operations
QUERY_METHOD_PATTERNS = [
    r"\.filter\(",
    r"\.filter_by\(",
    r"\.first\(\)",
    r"\.all\(\)",
    r"\.one\(\)",
    r"\.one_or_none\(\)",
    r"\.count\(\)",
    r"\.scalar\(",
    r"\.delete\(\)",  # for query.delete()
    r"\.update\(",  # for query.update()
]

# Files/directories to check
SERVICE_PATHS = [
    "backend/app/services",
    "backend/app/core",  # Some utilities might violate
]

# Files to exclude from checks
EXCLUDED_FILES = [
    "__pycache__",
    ".pyc",
    "base.py",  # BaseService needs direct DB for transactions
    "database.py",  # Database configuration
]

# Inline comment markers
IGNORE_MARKER = "repo-pattern-ignore"  # Permanent, legitimate DB access
MIGRATE_MARKER = "repo-pattern-migrate"  # Temporary, will be migrated

# Migration tracking file
MIGRATION_TRACKING_FILE = "backend/.repository-migration-tracking.json"


class RepositoryPatternChecker:
    def __init__(self):
        self.violations: List[Tuple[Path, int, str, str]] = []
        self.ignored_violations: List[Tuple[Path, int, str, str]] = []
        self.migration_violations: List[Tuple[Path, int, str, str]] = []
        self.checked_files = 0
        self.migration_tracking = self.load_migration_tracking()

    def load_migration_tracking(self) -> Dict:
        """Load migration tracking data."""
        tracking_file = Path(MIGRATION_TRACKING_FILE)
        if tracking_file.exists():
            with open(tracking_file, "r") as f:
                return json.load(f)
        return {
            "known_violations": {},
            "statistics": {"total_marked": 0, "migration_marked": 0, "ignored_marked": 0, "migrated_count": 0},
            "last_updated": None,
        }

    def save_migration_tracking(self) -> None:
        """Save updated migration tracking data."""
        self.migration_tracking["last_updated"] = datetime.now().isoformat()

        # Update statistics
        self.migration_tracking["statistics"]["migration_marked"] = len(self.migration_violations)
        self.migration_tracking["statistics"]["ignored_marked"] = len(self.ignored_violations)
        self.migration_tracking["statistics"]["total_marked"] = len(self.migration_violations) + len(
            self.ignored_violations
        )

        # Ensure we use correct path
        cwd = Path.cwd()
        if cwd.name == "backend":
            tracking_file = Path(".repository-migration-tracking.json")
        else:
            tracking_file = Path("backend/.repository-migration-tracking.json")

        # Create parent directory if needed
        tracking_file.parent.mkdir(parents=True, exist_ok=True)

        with open(tracking_file, "w") as f:
            json.dump(self.migration_tracking, f, indent=2)

    def check_file(self, filepath: Path) -> List[Tuple[int, str, str, str]]:
        """Check a single file for repository pattern violations.
        Returns: List of (line_num, line_content, context, marker_type)
        """
        violations = []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Check if file is a repository (repositories are allowed DB access)
            if "repository" in filepath.name.lower() or filepath.name.endswith("_repository.py"):
                return []

            # Check if file is excluded
            if any(excluded in filepath.name for excluded in EXCLUDED_FILES):
                return []

            # Check each line for violation patterns
            for line_num, line in enumerate(lines, 1):
                # Skip empty lines and comments
                stripped_line = line.strip()
                if not stripped_line or stripped_line.startswith("#"):
                    continue

                violation_found = False

                # Check for direct DB access patterns
                for pattern in VIOLATION_PATTERNS:
                    if re.search(pattern, line):
                        violation_found = True
                        break

                # Check for query method patterns (but only if there's a query first)
                if not violation_found:
                    # Look for query operations that might span multiple lines
                    if any(re.search(p, line) for p in QUERY_METHOD_PATTERNS):
                        # Check if this line or previous lines contain .query(
                        context_start = max(0, line_num - 5)
                        context_lines = lines[context_start:line_num]
                        if any("query(" in l for l in context_lines):
                            violation_found = True

                if violation_found:
                    # Check for inline markers
                    marker_type = None

                    # Check previous line for marker
                    if line_num > 1:
                        prev_line = lines[line_num - 2]
                        if IGNORE_MARKER in prev_line:
                            marker_type = "ignored"
                        elif MIGRATE_MARKER in prev_line:
                            marker_type = "migration"

                    # Check same line for marker
                    if IGNORE_MARKER in line:
                        marker_type = "ignored"
                    elif MIGRATE_MARKER in line:
                        marker_type = "migration"

                    # Get more context (previous and next line)
                    context_start = max(0, line_num - 2)
                    context_end = min(len(lines), line_num + 1)
                    context = "\n".join(lines[context_start:context_end])

                    violations.append((line_num, stripped_line[:100], context, marker_type))

        except Exception as e:
            print(f"Error checking {filepath}: {e}")

        return violations

    def check_directory(self, directory: Path) -> None:
        """Recursively check directory for violations."""
        for path in directory.rglob("*.py"):
            # Skip excluded files
            if any(excluded in str(path) for excluded in EXCLUDED_FILES):
                continue

            # Skip test files
            if "test" in path.name or "tests" in str(path):
                continue

            # Skip migration files
            if "migrations" in str(path) or "alembic" in str(path):
                continue

            self.checked_files += 1

            violations = self.check_file(path)
            if violations:
                for line_num, line, context, marker_type in violations:
                    if marker_type == "ignored":
                        self.ignored_violations.append((path, line_num, line, context))
                    elif marker_type == "migration":
                        self.migration_violations.append((path, line_num, line, context))
                    else:
                        self.violations.append((path, line_num, line, context))

    def check_all(self, save_tracking=True) -> bool:
        """Check all service directories for violations."""
        cwd = Path.cwd()

        # Ensure we're in the right directory
        if not (cwd / "backend").exists():
            # Try to find backend directory
            if (cwd.parent / "backend").exists():
                cwd = cwd.parent
            elif cwd.name == "backend":
                cwd = cwd.parent

        for service_path in SERVICE_PATHS:
            path = cwd / service_path if not service_path.startswith("/") else Path(service_path)
            if path.exists():
                self.check_directory(path)

        # Save tracking data only if requested (not during pre-commit)
        if save_tracking:
            self.save_migration_tracking()

        # Return True only if there are no unmarked violations
        return len(self.violations) == 0

    def print_report(self) -> None:
        """Print violation report."""
        print("\n" + "=" * 80)
        print("REPOSITORY PATTERN VIOLATION CHECK")
        print("=" * 80)

        print(f"\n📊 Summary:")
        print(f"  Files checked: {self.checked_files}")
        print(f"  ❌ Unmarked violations: {len(self.violations)}")
        print(f"  ⚠️  Migration-marked violations: {len(self.migration_violations)}")
        print(f"  ✅ Ignored (legitimate): {len(self.ignored_violations)}")

        # Show unmarked violations (these are the problems)
        if self.violations:
            print("\n❌ UNMARKED VIOLATIONS (Must Fix or Mark):\n")

            # Group violations by file
            violations_by_file: Dict[Path, List] = {}
            for path, line_num, line, context in self.violations:
                if path not in violations_by_file:
                    violations_by_file[path] = []
                violations_by_file[path].append((line_num, line, context))

            for filepath, file_violations in violations_by_file.items():
                try:
                    rel_path = filepath.relative_to(Path.cwd())
                except ValueError:
                    rel_path = filepath

                print(f"\n📁 {rel_path}")
                print(f"   Violations: {len(file_violations)}")

                for line_num, line, context in file_violations[:3]:  # Show max 3 per file
                    print(f"\n   Line {line_num}:")
                    print(f"   >>> {line}")
                    print(f"   Fix: Add '# repo-pattern-migrate: TODO: migrate to repository' above this line")

                if len(file_violations) > 3:
                    print(f"   ... and {len(file_violations) - 3} more violations")

            print("\n" + "=" * 80)
            print("❌ REPOSITORY PATTERN VIOLATIONS DETECTED")
            print("\nTo fix these violations, either:")
            print("1. Replace with repository calls (preferred)")
            print("2. Add '# repo-pattern-migrate: TODO: <reason>' above the line")
            print("3. Add '# repo-pattern-ignore: <reason>' if legitimately needed")
            print("=" * 80)

        # Show migration-marked violations (tracking)
        if self.migration_violations:
            print(f"\n⚠️  MIGRATION TRACKING ({len(self.migration_violations)} violations marked for migration)")

            # Summary by file
            migration_by_file: Dict[Path, int] = {}
            for path, _, _, _ in self.migration_violations:
                migration_by_file[path] = migration_by_file.get(path, 0) + 1

            for filepath, count in list(migration_by_file.items())[:5]:
                try:
                    rel_path = filepath.relative_to(Path.cwd())
                except ValueError:
                    rel_path = filepath
                print(f"  - {rel_path}: {count} violations")

            if len(migration_by_file) > 5:
                print(f"  ... and {len(migration_by_file) - 5} more files")

        # Show ignored violations (legitimate)
        if self.ignored_violations:
            print(f"\n✅ IGNORED (Legitimate DB Access): {len(self.ignored_violations)} violations")

            # Summary by file
            ignored_by_file: Dict[Path, int] = {}
            for path, _, _, _ in self.ignored_violations:
                ignored_by_file[path] = ignored_by_file.get(path, 0) + 1

            for filepath, count in ignored_by_file.items():
                try:
                    rel_path = filepath.relative_to(Path.cwd())
                except ValueError:
                    rel_path = filepath
                print(f"  - {rel_path}: {count} legitimate uses")

    def generate_initial_markers(self) -> None:
        """Generate a report of all violations for initial marking."""
        all_violations = []

        # Collect all violations
        for path, line_num, line, _ in self.violations:
            try:
                rel_path = path.relative_to(Path.cwd())
            except ValueError:
                rel_path = path

            all_violations.append({"file": str(rel_path), "line": line_num, "code": line[:80]})  # Truncate long lines

        if all_violations:
            output_file = Path("repository_violations_to_mark.json")
            with open(output_file, "w") as f:
                json.dump(
                    {
                        "total_violations": len(all_violations),
                        "instructions": "Add '# repo-pattern-migrate: TODO: migrate to repository' above each violation",
                        "violations": all_violations,
                    },
                    f,
                    indent=2,
                )

            print(f"\n📝 Generated violation list: {output_file}")
            print(f"   Total violations to mark: {len(all_violations)}")
            print(f"   Add migration markers to proceed with commits")


def main():
    """Main entry point."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Check repository pattern compliance")
    parser.add_argument(
        "--generate-markers", action="store_true", help="Generate list of violations for initial marking"
    )
    parser.add_argument("--show-all", action="store_true", help="Show all violations including marked ones")
    parser.add_argument(
        "--add-markers", action="store_true", help="Automatically add migration markers to all violations"
    )
    args = parser.parse_args()

    checker = RepositoryPatternChecker()

    # Detect if running in pre-commit context (don't save tracking file during pre-commit)
    is_precommit = os.environ.get("PRE_COMMIT", "0") == "1" or "pre-commit" in sys.argv[0]

    # Check for violations
    success = checker.check_all(save_tracking=not is_precommit)

    # Print report
    checker.print_report()

    # Generate initial markers if requested
    if args.generate_markers and checker.violations:
        checker.generate_initial_markers()

    # Auto-add markers if requested
    if args.add_markers and checker.violations:
        print("\n🔧 Adding migration markers to violations...")
        # This would require modifying files - left as exercise
        print("   (Auto-marking not yet implemented - add manually)")

    # Show statistics
    total_violations = len(checker.violations) + len(checker.migration_violations) + len(checker.ignored_violations)

    if total_violations > 0:
        print(f"\n📈 Progress Tracking:")
        print(f"  Total DB accesses found: {total_violations}")
        print(f"  Unmarked (blocking): {len(checker.violations)}")
        print(f"  Marked for migration: {len(checker.migration_violations)}")
        print(f"  Legitimate (ignored): {len(checker.ignored_violations)}")

        if len(checker.migration_violations) > 0:
            migration_percentage = (len(checker.migration_violations) / total_violations) * 100
            print(f"  Migration progress: {migration_percentage:.1f}% marked for migration")

    # Exit with appropriate code
    # Only fail on unmarked violations
    if len(checker.violations) > 0:
        print("\n❌ Pre-commit check FAILED - unmarked violations found")
        print("   Run with --generate-markers to get list of violations to mark")
        sys.exit(1)
    else:
        print("\n✅ Pre-commit check PASSED")
        if len(checker.migration_violations) > 0:
            print(f"   ({len(checker.migration_violations)} violations marked for future migration)")
        sys.exit(0)


if __name__ == "__main__":
    main()
