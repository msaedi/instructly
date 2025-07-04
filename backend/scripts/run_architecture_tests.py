#!/usr/bin/env python3
# backend/scripts/run_architecture_tests.py
"""
Run the schema architecture tests to verify clean architecture.
"""

import os
import subprocess
import sys


def main():
    print("=" * 60)
    print("RUNNING SCHEMA ARCHITECTURE TESTS")
    print("=" * 60)
    print("\nThese tests validate that our schemas follow clean architecture:")
    print("- No availability_slot_id references")
    print("- No is_available fields")
    print("- Bookings are self-contained")
    print("- Dead code has been removed")
    print()

    # Change to backend directory
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    # Run the architecture tests
    cmd = [sys.executable, "-m", "pytest", "tests/schemas/test_schema_architecture.py", "-v"]

    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    print("-" * 60)

    if result.returncode == 0:
        print("✅ ALL TESTS PASSED! Clean architecture achieved!")
    else:
        print(f"❌ Tests failed with exit code: {result.returncode}")
        print("\nIf you see validator errors, make sure all validators have:")
        print("1. @classmethod decorator")
        print("2. Use info.data.get('field') instead of 'field' in info")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
