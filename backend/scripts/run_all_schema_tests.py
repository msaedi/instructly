#!/usr/bin/env python3
# backend/scripts/run_all_schema_tests.py
"""Run all schema validation tests to verify clean architecture."""

import os
import subprocess
import sys


def run_command(cmd, description):
    """Run a command and report results."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr and "NotOpenSSLWarning" not in result.stderr:
        print("STDERR:", result.stderr)

    return result.returncode == 0


def main():
    print(
        """
COMPREHENSIVE SCHEMA TEST SUITE
===============================

This will run all tests to verify our clean architecture implementation:
1. Quick fix verification
2. Full pytest architecture tests
3. Clean architecture verification
4. Extra field rejection test
"""
    )

    # Change to backend directory
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    all_passed = True

    # Test 1: Quick verification
    if not run_command([sys.executable, "scripts/quick_test_fixes.py"], "Quick Fix Verification"):
        all_passed = False

    # Test 2: Extra field rejection
    if not run_command([sys.executable, "scripts/test_extra_forbid.py"], "Extra Field Rejection Test"):
        all_passed = False

    # Test 3: Clean architecture verification
    if not run_command([sys.executable, "scripts/verify_clean_architecture.py"], "Clean Architecture Verification"):
        all_passed = False

    # Test 4: Full pytest suite
    if not run_command(
        [sys.executable, "-m", "pytest", "tests/schemas/test_schema_architecture.py", "-v"],
        "Full Pytest Architecture Tests",
    ):
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    if all_passed:
        print(
            """
✅ ALL TESTS PASSED!

Clean Architecture Successfully Implemented:
- No availability_slot_id references
- No is_available fields
- Bookings are self-contained
- Dead code removed
- Extra fields rejected

The schemas now implement true "Rug and Person" architecture
where bookings and availability are completely independent layers.
"""
        )
        return 0
    else:
        print(
            """
❌ Some tests failed.

Check the output above for details. Common issues:
1. Make sure you're running from the backend directory
2. Ensure all schema files have been updated
3. Check that model_config = ConfigDict(extra='forbid') is in BookingCreate
"""
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
