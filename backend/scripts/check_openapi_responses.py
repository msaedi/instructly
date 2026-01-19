#!/usr/bin/env python3
"""CI check: all endpoints have response schemas or valid 204.

This script validates that every API endpoint either:
1. Has a proper response schema (response_model)
2. Returns 204 No Content
3. Is explicitly exempt (streaming endpoints, file downloads)

Usage:
    python scripts/check_openapi_responses.py
"""

from __future__ import annotations

from pathlib import Path
import sys

# Add the backend directory to Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))


# Patterns for endpoints that are intentionally exempt from response schema requirements
EXEMPT_PATTERNS = [
    "/stream",       # SSE streams
    "/export",       # File downloads
    "/ws",           # WebSocket endpoints
    "/metrics",      # Prometheus metrics (text/plain)
]


def check_openapi_responses() -> list[str]:
    """Check all OpenAPI endpoints have response schemas or valid 204.

    Returns:
        List of endpoint errors (empty if all pass)
    """
    # Import here to avoid import errors before path setup
    from app.openapi_app import openapi_app

    spec = openapi_app.openapi()
    errors: list[str] = []

    for path, methods in spec.get("paths", {}).items():
        # Skip exempt patterns
        if any(pattern in path for pattern in EXEMPT_PATTERNS):
            continue

        for method, details in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue

            responses = details.get("responses", {})

            # 204 No Content is valid without schema
            if "204" in responses:
                continue

            # Check 200/201 for schema
            has_schema = False
            for code in ["200", "201"]:
                if code in responses:
                    content = responses[code].get("content", {})
                    json_content = content.get("application/json", {})
                    if "schema" in json_content:
                        schema = json_content["schema"]
                        # Check for $ref or inline properties
                        if "$ref" in str(schema) or schema.get("properties"):
                            has_schema = True
                            break

            if not has_schema:
                errors.append(f"{method.upper()} {path}")

    return errors


def main() -> int:
    """Main entry point."""
    print("Checking OpenAPI response schemas...")
    errors = check_openapi_responses()

    if errors:
        print(f"\n❌ {len(errors)} endpoints missing response schemas:\n")
        for error in sorted(errors):
            print(f"  - {error}")
        print("\nFix by adding response_model to the endpoint decorator,")
        print("or add status_code=204 for no-content responses.")
        return 1

    print("✅ All endpoints have response schemas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
