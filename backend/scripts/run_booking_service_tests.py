#!/usr/bin/env python3
# backend/scripts/run_booking_service_tests.py
"""
Script to run BookingService tests and generate coverage report.
"""

import os
import subprocess
import sys


def run_tests():
    """Run the BookingService tests with coverage."""

    # Change to backend directory
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    print("Running BookingService tests with coverage...")
    print("-" * 60)

    # Run pytest with coverage for BookingService
    cmd = [
        "pytest",
        "-xvs",
        "--cov=app.services.booking_service",
        "--cov-report=term-missing",
        "--cov-report=html",
        "tests/integration/test_booking_service_comprehensive.py",
        "tests/integration/test_booking_service_edge_cases.py",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Print output
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        # Check if tests passed
        if result.returncode == 0:
            print("\n✅ Tests passed!")
            print("\nCoverage report saved to: htmlcov/index.html")

            # Also run coverage report command for detailed view
            print("\n" + "-" * 60)
            print("Detailed coverage for BookingService:")
            subprocess.run(["coverage", "report", "-m", "app/services/booking_service.py"])
        else:
            print("\n❌ Tests failed!")
            return 1

    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
