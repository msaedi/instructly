#!/usr/bin/env python3
"""Ensure main.py and openapi_app.py include the same routers.

This script prevents the situation where a router is added to main.py
but forgotten in openapi_app.py, causing types to be missing from
the generated OpenAPI schema.

Usage:
    python scripts/check_router_sync.py
    python scripts/check_router_sync.py --fix  # Show what needs to be added
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


def extract_router_includes(filepath: Path) -> dict[str, str]:
    """Extract router prefixes and their include lines from a file.

    Returns:
        dict mapping prefix -> the full include_router line
    """
    content = filepath.read_text()
    results: dict[str, str] = {}

    # Match: api_v1.include_router(..., prefix="/something")
    # Also handles referrals_v1.admin_router, etc.
    pattern = r'api_v1\.include_router\([^)]+prefix=["\']([^"\']+)["\'][^)]*\)'

    for match in re.finditer(pattern, content):
        prefix = match.group(1)
        full_line = match.group(0)
        results[prefix] = full_line

    return results


# Routers that are intentionally different between main.py and openapi_app.py
# These are excluded from sync checks
KNOWN_EXCLUSIONS = {
    # Internal metrics router is created inline in main.py, not a module
    "/internal",  # Has both internal_v1.router AND internal_metrics_router
}

# Routers in main.py that should NOT be in OpenAPI (internal/runtime only)
MAIN_ONLY_ROUTERS: set[str] = set()
# Add prefixes here if they should exist in main.py but NOT in openapi_app.py
# Example: MAIN_ONLY_ROUTERS.add("/internal-metrics")


def main() -> int:
    # Find project root
    script_dir = Path(__file__).resolve().parent
    backend_dir = script_dir.parent

    main_py = backend_dir / "app" / "main.py"
    openapi_py = backend_dir / "app" / "openapi_app.py"

    if not main_py.exists():
        print(f"❌ Could not find main.py at {main_py}")
        return 1
    if not openapi_py.exists():
        print(f"❌ Could not find openapi_app.py at {openapi_py}")
        return 1

    main_routers = extract_router_includes(main_py)
    openapi_routers = extract_router_includes(openapi_py)

    # Get prefix sets
    main_prefixes = set(main_routers.keys())
    openapi_prefixes = set(openapi_routers.keys())

    # Filter out known exclusions and main-only routers
    main_relevant = main_prefixes - KNOWN_EXCLUSIONS - MAIN_ONLY_ROUTERS
    openapi_relevant = openapi_prefixes - KNOWN_EXCLUSIONS

    # Find mismatches
    missing_in_openapi = main_relevant - openapi_relevant
    extra_in_openapi = openapi_relevant - main_relevant

    errors = []

    if missing_in_openapi:
        errors.append("Routers in main.py but NOT in openapi_app.py:")
        for prefix in sorted(missing_in_openapi):
            errors.append(f"  - {prefix}")
            # Show what needs to be added
            if "--fix" in sys.argv:
                errors.append(f"    Add: {main_routers[prefix]}")

    if extra_in_openapi:
        errors.append("\nRouters in openapi_app.py but NOT in main.py (should be removed):")
        for prefix in sorted(extra_in_openapi):
            errors.append(f"  - {prefix}")

    if errors:
        print("❌ Router sync mismatch:\n")
        for e in errors:
            print(e)
        print("\n")
        print("Fix by ensuring both files include the same routers.")
        print("If a router should be excluded from OpenAPI, add it to MAIN_ONLY_ROUTERS")
        print("in this script.")
        return 1

    # Count the shared routers (accounting for known exclusions having multiple entries)
    shared_count = len(main_relevant & openapi_relevant)
    print(f"✅ Routers in sync ({shared_count} routes checked)")

    # List all routers for visibility
    if "-v" in sys.argv or "--verbose" in sys.argv:
        print("\nRouters checked:")
        for prefix in sorted(main_relevant & openapi_relevant):
            print(f"  {prefix}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
