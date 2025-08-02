#!/usr/bin/env python3
"""
Check API contracts for violations.

This script runs contract tests and provides a detailed report of any violations found.
It can be run locally before committing changes.
"""

import subprocess
import sys
from pathlib import Path

# Colors for terminal output
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

    # Run the simple contract test
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_api_contracts_simple.py", "-v", "--tb=short"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
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
        print("\nViolations detected:")

        # Parse output for specific violations
        output_lines = result.stdout.split("\n")
        for line in output_lines:
            if "MISSING_RESPONSE_MODEL" in line:
                print(f"  {YELLOW}⚠️  Missing response_model declaration{RESET}")
            elif "DIRECT_DICT_RETURN" in line:
                print(f"  {YELLOW}⚠️  Direct dictionary return{RESET}")
            elif "MANUAL_JSON_RESPONSE" in line:
                print(f"  {YELLOW}⚠️  Manual JSON response{RESET}")

        print(f"\n{YELLOW}To see full details, run:{RESET}")
        print(f"  cd {backend_dir}")
        print("  pytest tests/test_api_contracts_simple.py -v")

        # Run the comprehensive test to show all violations
        print(f"\n{BLUE}Running comprehensive contract analysis...{RESET}")
        comprehensive_result = subprocess.run(
            [sys.executable, "-m", "tests.test_api_contracts"], cwd=backend_dir, capture_output=True, text=True
        )

        if "Found" in comprehensive_result.stdout and "contract violations" in comprehensive_result.stdout:
            print(f"\n{YELLOW}Full analysis found violations:{RESET}")
            # Extract violation count and details
            import re

            match = re.search(r"Found (\d+) contract violations", comprehensive_result.stdout)
            if match:
                count = match.group(1)
                print(f"  Total violations: {RED}{count}{RESET}")

                # Show the violations
                violations_start = comprehensive_result.stdout.find("Found")
                if violations_start != -1:
                    violations_text = comprehensive_result.stdout[violations_start:]
                    print("\nDetailed violations:")
                    for line in violations_text.split("\n")[1:33]:  # Show first 32 violations
                        if line.strip() and line.startswith("  -"):
                            print(line)

        return 1


if __name__ == "__main__":
    sys.exit(main())
