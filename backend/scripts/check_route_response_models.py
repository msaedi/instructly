#!/usr/bin/env python3
"""Pre-commit: routes have response_model or status_code=204.

This script statically analyzes route files to ensure every endpoint has either:
1. A response_model parameter
2. A status_code=204 parameter
3. An openapi-exempt comment

Usage:
    python scripts/check_route_response_models.py
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}


def check_file(filepath: Path) -> list[str]:
    """Check a single route file for response model compliance.

    Args:
        filepath: Path to the route file

    Returns:
        List of errors found (empty if compliant)
    """
    errors: list[str] = []
    try:
        content = filepath.read_text()
        tree = ast.parse(content)
    except SyntaxError:
        return []

    lines = content.split("\n")

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            func = decorator.func
            if not isinstance(func, ast.Attribute) or func.attr not in ROUTE_METHODS:
                continue

            has_response_model = False
            has_204_status = False

            for kw in decorator.keywords:
                if kw.arg == "response_model":
                    # response_model=None is NOT valid (explicit no-schema)
                    if isinstance(kw.value, ast.Constant) and kw.value.value is None:
                        continue
                    has_response_model = True
                if kw.arg == "status_code":
                    # Check for 204 or status.HTTP_204_NO_CONTENT
                    if isinstance(kw.value, ast.Constant) and kw.value.value == 204:
                        has_204_status = True
                    elif isinstance(kw.value, ast.Attribute):
                        # status.HTTP_204_NO_CONTENT
                        if "204" in kw.value.attr:
                            has_204_status = True

            # Check for openapi-exempt comment on lines before the decorator
            has_exempt = False
            for offset in range(-3, 1):  # Check 3 lines before and the decorator line
                line_idx = decorator.lineno - 1 + offset
                if 0 <= line_idx < len(lines):
                    if "openapi-exempt" in lines[line_idx]:
                        has_exempt = True
                        break

            if not has_response_model and not has_204_status and not has_exempt:
                errors.append(f"{filepath}:{node.lineno} - {node.name}()")

    return errors


def main() -> int:
    """Main entry point."""
    errors: list[str] = []

    # Find routes directory
    for routes_dir in [Path("backend/app/routes"), Path("app/routes")]:
        if routes_dir.exists():
            for filepath in routes_dir.rglob("*.py"):
                # Skip __init__.py files
                if filepath.name == "__init__.py":
                    continue
                errors.extend(check_file(filepath))
            break
    else:
        print("Warning: Could not find routes directory")
        return 0

    if errors:
        print("❌ Routes missing response_model or status_code=204:\n")
        for error in errors:
            print(f"  {error}")
        print("\nFix by adding response_model=YourResponseModel to the decorator,")
        print("or add status_code=204 for no-content responses,")
        print("or add # openapi-exempt: <reason> comment for legitimate exceptions.")
        return 1

    print("✅ All routes properly typed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
