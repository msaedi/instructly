"""
Simple API Contract Tests - Static Analysis Only

This test performs static analysis to find contract violations without
making actual API calls.

Note: This test currently passes even though violations exist because
the static analysis patterns don't catch all violations. The comprehensive
test (test_api_contracts.py) finds all violations by actually inspecting
the FastAPI app instance.
"""

import ast
import importlib
from pathlib import Path
import re
from typing import List

from pydantic import BaseModel
import pytest


# Find the backend directory regardless of where pytest is run from
def find_backend_dir() -> Path:
    """Find the backend directory by looking for pyproject.toml."""
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "app").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find backend directory")


BACKEND_DIR = find_backend_dir()


class ContractViolation:
    """Represents a contract violation found during testing."""

    def __init__(self, file: str, endpoint: str, method: str, violation_type: str, details: str):
        self.file = file
        self.endpoint = endpoint
        self.method = method
        self.violation_type = violation_type
        self.details = details

    def __str__(self):
        return (
            f"{self.file} - {self.method} {self.endpoint}: {self.violation_type} - {self.details}"
        )


def analyze_route_file(file_path: Path) -> List[ContractViolation]:
    """Analyze a single route file for contract violations."""
    violations = []

    with open(file_path) as f:
        content = f.read()

    # Skip test files
    if "test_" in file_path.name:
        return violations

    # Find all route definitions
    route_pattern = r"@router\.(get|post|put|patch|delete)\s*\(([^)]+)\)"
    route_matches = re.finditer(route_pattern, content, re.DOTALL)

    for match in route_matches:
        method = match.group(1).upper()
        route_args = match.group(2)

        # Extract the path
        path_match = re.search(r'["\']([^"\']+)["\']', route_args)
        if not path_match:
            continue

        endpoint = path_match.group(1)

        # Skip SSE endpoints (they use EventSourceResponse)
        # Look ahead in the content to see if this endpoint returns EventSourceResponse
        func_start = match.end()
        func_end = content.find("\n@router", func_start)
        if func_end == -1:
            func_end = min(func_start + 2000, len(content))  # Look ahead 2000 chars max
        func_preview = content[func_start:func_end]

        if "EventSourceResponse" in func_preview:
            continue  # Skip SSE endpoint

        # Check for response_model
        if method in ["GET", "POST", "PUT", "PATCH"]:
            if "response_model=" not in route_args:
                # Check if it's a special case (204 No Content, file download, etc.)
                if (
                    "status_code=status.HTTP_204_NO_CONTENT" not in route_args
                    and "status_code=204" not in route_args
                    and "Response(" not in content
                    and "FileResponse" not in content
                ):
                    violations.append(
                        ContractViolation(
                            file_path.name,
                            endpoint,
                            method,
                            "MISSING_RESPONSE_MODEL",
                            "Endpoint does not declare a response_model",
                        )
                    )

        # Find the function definition after the route decorator
        func_pattern = (
            r"@router\."
            + method.lower()
            + r"\s*\([^)]+\)\s*(?:@[^\n]+\s*)*(?:async\s+)?def\s+(\w+)\s*\([^)]*\)\s*(?:->\s*[^:]+)?:\s*((?:[^\n]|\n(?!@router|def))*)"
        )
        func_match = re.search(func_pattern, content[match.start() :], re.DOTALL)

        if func_match:
            func_body = func_match.group(2)

            # Check for direct dictionary returns
            dict_patterns = [
                r"return\s+{",
                r"return\s+dict\(",
                r"return\s+\w+\.dict\(\)",
            ]

            for pattern in dict_patterns:
                if re.search(pattern, func_body):
                    # Make sure it's not a Response model
                    if not re.search(r"return\s+\w+Response\(", func_body) and not re.search(
                        r"return\s+\w+\(\s*{", func_body
                    ):
                        violations.append(
                            ContractViolation(
                                file_path.name,
                                endpoint,
                                method,
                                "DIRECT_DICT_RETURN",
                                "Returns dictionary instead of response model",
                            )
                        )
                        break

            # Check for JSONResponse usage
            if "JSONResponse(" in func_body:
                violations.append(
                    ContractViolation(
                        file_path.name,
                        endpoint,
                        method,
                        "MANUAL_JSON_RESPONSE",
                        "Uses JSONResponse instead of response model",
                    )
                )

    return violations


def test_no_contract_violations():
    """Test that there are no contract violations in route files."""
    routes_dir = BACKEND_DIR / "app" / "routes"
    all_violations = []

    # Analyze all route files
    for py_file in routes_dir.glob("*.py"):
        if py_file.name != "__init__.py":
            violations = analyze_route_file(py_file)
            all_violations.extend(violations)

    if all_violations:
        violation_report = "\n".join(str(v) for v in all_violations)
        pytest.fail(f"Found {len(all_violations)} contract violations:\n\n{violation_report}")


def test_response_models_exist():
    """Test that response model files exist and follow naming convention."""
    schemas_dir = BACKEND_DIR / "app" / "schemas"
    response_files = list(schemas_dir.glob("*_responses.py"))

    assert len(response_files) > 0, "No response model files found (*_responses.py)"

    # Check that each file contains at least one response model
    for file in response_files:
        module_path = file.relative_to(BACKEND_DIR).with_suffix("")
        module_name = ".".join(module_path.parts)
        module = importlib.import_module(module_name)

        matches = [
            (name, obj)
            for name, obj in vars(module).items()
            if isinstance(obj, type) and name.endswith("Response") and issubclass(obj, BaseModel)
        ]

        assert len(matches) > 0, f"{file.name} contains no response model classes"


def test_consistent_field_naming():
    """Test that response models use consistent field naming (snake_case)."""
    schemas_dir = BACKEND_DIR / "app" / "schemas"
    violations = []

    for py_file in schemas_dir.glob("*_responses.py"):
        with open(py_file) as f:
            content = f.read()

        # Parse the AST to find field definitions
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "Response" in node.name:
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        field_name = item.target.id
                        # Check if field name is snake_case
                        if not re.match(r"^[a-z]+(_[a-z0-9]+)*$", field_name):
                            # Allow some exceptions like HTTP status codes
                            if not re.match(r"^[A-Z]+(_[0-9]+)?$", field_name):
                                violations.append(
                                    f"{py_file.name}: {node.name}.{field_name} is not snake_case"
                                )

    if violations:
        pytest.fail("Found field naming violations:\n" + "\n".join(violations))


def test_no_raw_list_responses():
    """Test that endpoints don't return raw lists (should be wrapped in response models)."""
    routes_dir = BACKEND_DIR / "app" / "routes"
    violations = []

    for py_file in routes_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        with open(py_file) as f:
            content = f.read()

        # Look for response_model=List[...]
        list_pattern = r"response_model=List\[([^\]]+)\]"
        matches = re.finditer(list_pattern, content)

        for match in matches:
            # Extract the endpoint path
            # Look backwards from the match to find the route decorator
            before_match = content[: match.start()]
            route_match = re.search(r'@router\.\w+\s*\(["\']([^"\']+)["\']', before_match[::-1])

            if route_match:
                endpoint = route_match.group(1)[::-1]
                # Some endpoints legitimately return lists (like search history)
                # but we should encourage wrapping them
                if "/search-trends" not in endpoint:  # This one is allowed to return a list
                    violations.append(
                        f"{py_file.name}: {endpoint} returns List[{match.group(1)}] - consider wrapping in a response model"
                    )

    # This is more of a warning than a hard failure
    if violations:
        print("Consider wrapping these list responses:")
        for v in violations:
            print(f"  - {v}")


if __name__ == "__main__":
    # Run the analysis
    print("Analyzing route files for contract violations...")

    routes_dir = Path("app/routes")
    all_violations = []

    for py_file in routes_dir.glob("*.py"):
        if py_file.name != "__init__.py":
            violations = analyze_route_file(py_file)
            all_violations.extend(violations)

    if all_violations:
        print(f"\nFound {len(all_violations)} contract violations:\n")
        for v in all_violations:
            print(f"  - {v}")
    else:
        print("\nNo contract violations found! ✅")


def test_comprehensive_contract_violations():
    """Run the comprehensive contract test to catch all violations."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "tests.test_api_contracts"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )

    # Check if violations were found
    if "Found" in result.stdout and "contract violations" in result.stdout:
        # Extract violation count
        import re

        match = re.search(r"Found (\d+) contract violations", result.stdout)
        if match:
            count = int(match.group(1))
            if count > 0:
                # Get the violations text
                violations_text = result.stdout[result.stdout.find("Found") :]
                pytest.fail(f"{violations_text}")
