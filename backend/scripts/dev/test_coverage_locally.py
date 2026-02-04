# backend/scripts/test_coverage_locally.py
"""
Test coverage locally in the same way GitHub Actions does.
This helps debug coverage issues without pushing to GitHub.
"""

import json
import os
from pathlib import Path
import subprocess


def run_command(cmd, cwd=None):
    """Run a command and return output."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    return result.returncode, result.stdout, result.stderr


def main():
    # Change to backend directory
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)
    print(f"Working directory: {os.getcwd()}")

    # Set environment variables
    os.environ["COVERAGE_FILE"] = ".coverage"
    os.environ["SECRET_KEY"] = "test-secret-key-for-local-coverage-run!"
    os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/instainstru_test"
    os.environ["RESEND_API_KEY"] = "test-resend-key"
    os.environ["REDIS_URL"] = "redis://localhost:6379"

    print("\n=== Running tests with coverage (same as GitHub Actions) ===")

    # Method 1: Using coverage run
    print("\nMethod 1: coverage run")
    returncode, stdout, stderr = run_command(
        "coverage run --source=app --branch -m pytest -v tests/test_auth.py"  # Quick test for demo
    )

    # Check if .coverage exists
    if os.path.exists(".coverage"):
        print("\n✅ .coverage file created!")
        print(f"File size: {os.path.getsize('.coverage')} bytes")

        # Generate reports
        print("\n=== Generating reports ===")
        run_command("coverage xml")
        run_command("coverage json")
        run_command("coverage report --show-missing")

        # Parse JSON for stats
        if os.path.exists("coverage.json"):
            with open("coverage.json") as f:
                data = json.load(f)
                total = data["totals"]
                print(f"\nTotal Coverage: {total['percent_covered']:.2f}%")
                print(f"Lines Covered: {total['covered_lines']}/{total['num_statements']}")
    else:
        print("\n❌ No .coverage file found!")
        print("Files in current directory:")
        for f in os.listdir("."):
            if "coverage" in f.lower() or ".coverage" in f:
                print(f"  - {f}")

    print("\n=== Alternative Method: pytest --cov ===")
    returncode, stdout, stderr = run_command(
        "pytest --cov=app --cov-branch --cov-report=term --cov-report=xml tests/test_auth.py"
    )

    # Check what files were created
    print("\n=== Coverage files created ===")
    for pattern in [".coverage*", "coverage.*"]:
        run_command(f"ls -la {pattern} 2>/dev/null || true")

    # Debug coverage configuration
    print("\n=== Coverage configuration ===")
    run_command("coverage debug config")

    print("\n=== Python module versions ===")
    run_command("python -c \"import coverage; print(f'coverage: {coverage.__version__}')\"")
    run_command("python -c \"import pytest_cov; print(f'pytest-cov: {pytest_cov.__version__}')\"")


if __name__ == "__main__":
    main()
