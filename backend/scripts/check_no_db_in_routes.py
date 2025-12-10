#!/usr/bin/env python3
"""
Pre-commit hook to enforce repository pattern in routes.

Routes should NEVER:
- Call db.query(), db.commit(), db.add(), etc.
- Access repositories directly
- Import SQLAlchemy models for querying

Routes SHOULD:
- Call service methods only
- Let services handle all DB operations
"""

from pathlib import Path
import re
import sys
from typing import List, Tuple

# Patterns that should NEVER appear in routes
FORBIDDEN_PATTERNS = [
    # Direct session operations
    (r'\bdb\.query\s*\(', "db.query() - use service layer"),
    (r'\bdb\.commit\s*\(', "db.commit() - service should handle transactions"),
    (r'\bdb\.flush\s*\(', "db.flush() - service should handle transactions"),
    (r'\bdb\.refresh\s*\(', "db.refresh() - service should handle this"),
    (r'\bdb\.rollback\s*\(', "db.rollback() - service should handle transactions"),
    (r'\bdb\.add\s*\(', "db.add() - use repository.create()"),
    (r'\bdb\.delete\s*\(', "db.delete() - use repository.delete()"),
    (r'\bdb\.execute\s*\(', "db.execute() - use repository layer"),
    (r'\bsession\.query\s*\(', "session.query() - use service layer"),
    (r'\bsession\.commit\s*\(', "session.commit() - service should handle"),
    (r'\bsession\.add\s*\(', "session.add() - use repository.create()"),
    # Direct repository usage in routes (should go through service)
    (r'\brepository\.create\s*\(', "repository.create() - use service layer"),
    (r'\brepository\.update\s*\(', "repository.update() - use service layer"),
    (r'\brepository\.delete\s*\(', "repository.delete() - use service layer"),
    (r'\brepository\.get\s*\(', "repository.get() - use service layer"),
    (r'\b_repo\.', "Direct repo access - use service layer"),
    (r'\b_repository\.', "Direct repo access - use service layer"),
]

# Patterns in imports that suggest violations
SUSPICIOUS_IMPORTS = [
    (r'from\s+\.\.\.?models\s+import', "Importing models directly - may indicate direct DB access"),
]

# Exception marker - add to line to skip check
IGNORE_MARKER = "# db-access-ok"

# Only check route files
ROUTE_PATHS = [
    "backend/app/routes/",
]


def check_file(filepath: Path) -> List[Tuple[int, str, str]]:
    """Check a single route file for forbidden patterns."""
    violations = []

    # Only check route files
    is_route_file = any(str(filepath).startswith(p) or f"/{p}" in str(filepath)
                       for p in ROUTE_PATHS)
    if not is_route_file:
        return violations

    try:
        content = filepath.read_text()
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            # Skip if has ignore marker
            if IGNORE_MARKER in line:
                continue

            # Skip comments
            stripped = line.strip()
            if stripped.startswith('#'):
                continue

            # Check forbidden patterns
            for pattern, message in FORBIDDEN_PATTERNS:
                if re.search(pattern, line):
                    violations.append((line_num, stripped[:80], message))
                    break  # One violation per line is enough

            # Check suspicious imports (warning only)
            for pattern, message in SUSPICIOUS_IMPORTS:
                if re.search(pattern, line):
                    # Just a warning, not a hard violation
                    pass

    except Exception as e:
        print(f"Warning: Error processing {filepath}: {e}", file=sys.stderr)

    return violations


def main():
    """Main entry point."""
    all_violations = []

    # Get files from command line or scan routes directory
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:] if f.endswith('.py')]
    else:
        files = []
        for route_path in ROUTE_PATHS:
            path = Path(route_path)
            if path.exists():
                files.extend(path.rglob("*.py"))

    for filepath in files:
        violations = check_file(filepath)
        for line_num, source, message in violations:
            all_violations.append((str(filepath), line_num, source, message))

    if all_violations:
        print("\n" + "=" * 60)
        print("REPOSITORY PATTERN VIOLATIONS IN ROUTES")
        print("=" * 60)
        print("\nRoutes should NEVER access the database directly.")
        print("All DB operations must go through the service layer.\n")

        for filepath, line, source, message in all_violations:
            print(f"  {filepath}:{line}")
            print(f"    Code: {source}")
            print(f"    Issue: {message}")
            print()

        print(f"{'='*60}")
        print(f"Total violations: {len(all_violations)}")
        print(f"{'='*60}")
        print("\nFix: Move DB operations into service methods")
        print(f"Skip check: Add '{IGNORE_MARKER}' comment to line (use sparingly)")
        sys.exit(1)

    print("No repository pattern violations in routes")
    sys.exit(0)


if __name__ == "__main__":
    main()
