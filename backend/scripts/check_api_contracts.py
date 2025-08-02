#!/usr/bin/env python3
"""
Check API contracts for violations.

This script runs contract tests and provides a detailed report of any violations found.
It can be run locally before committing changes.
"""

import os
import subprocess
import sys
from pathlib import Path

# Colors for terminal output (disabled in CI)
if os.getenv("CI") or not sys.stdout.isatty():
    RED = ""
    GREEN = ""
    YELLOW = ""
    BLUE = ""
    RESET = ""
else:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def main():
    """Run contract checks and report results."""
    print(f"{BLUE}🔍 Checking API Contracts...{RESET}")
    print("=" * 50)

    # Find backend directory
    backend_dir = Path(__file__).parent.parent

    # Set environment to suppress database messages
    env = os.environ.copy()
    env["SUPPRESS_DB_MESSAGES"] = "1"

    # Run the comprehensive contract test directly
    # This is more reliable than the simple test
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_api_contracts.py::TestAPIContracts::test_no_contract_violations",
            "-v",
            "--tb=short",
            "-q",  # Quieter output
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode == 0:
        print(f"\n{GREEN}✅ All API contracts are valid!{RESET}")
        print("\nContract tests passed:")
        print("  ✓ All endpoints declare response models")
        print("  ✓ No direct dictionary returns")
        print("  ✓ No manual JSON responses")
        print("  ✓ Consistent field naming")
        return 0

    else:
        print(f"\n{RED}❌ API Contract Violations Found!{RESET}")

        # Debug output in CI
        if os.getenv("CI"):
            print("\nDEBUG: Test stdout:")
            print(result.stdout)
            print("\nDEBUG: Test stderr:")
            print(result.stderr)

        # Try to extract violations from the test output
        if "contract violations:" in result.stdout.lower():
            print("\nViolations detected:")
            violations_start = result.stdout.lower().find("contract violations:")
            if violations_start != -1:
                violations_text = result.stdout[violations_start:]
                for line in violations_text.split("\n")[1:33]:  # Show first 32 violations
                    if line.strip() and (
                        "GET" in line or "POST" in line or "PUT" in line or "PATCH" in line or "DELETE" in line
                    ):
                        print(f"  {YELLOW}⚠️  {line.strip()}{RESET}")

        print(f"\n{YELLOW}To see full details, run:{RESET}")
        print(f"  cd {backend_dir}")
        print("  pytest tests/test_api_contracts.py -v")

        return 1


if __name__ == "__main__":
    sys.exit(main())
