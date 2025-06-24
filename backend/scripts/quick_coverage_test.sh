#!/bin/bash
# backend/scripts/quick_coverage_test.sh
# Quick test to verify coverage is working before pushing to GitHub

cd backend

echo "=== Quick Coverage Test ==="
echo "Testing with just auth tests (10 tests, ~6 seconds)"
echo ""

# Clean up any existing coverage files
rm -f .coverage coverage.xml coverage.json

# Run coverage with just auth tests (fast)
echo "Running: coverage run --source=app --branch -m pytest -v tests/test_auth.py"
coverage run --source=app --branch -m pytest -v tests/test_auth.py

# Check if .coverage was created
if [ -f .coverage ]; then
    echo ""
    echo "✅ SUCCESS: .coverage file created!"
    echo "File size: $(ls -lh .coverage | awk '{print $5}')"

    # Generate XML for Codecov
    coverage xml
    echo "✅ coverage.xml created: $(ls -lh coverage.xml | awk '{print $5}')"

    # Show quick summary
    echo ""
    echo "=== Coverage Summary ==="
    coverage report | tail -n 5

    echo ""
    echo "✅ Coverage is working correctly! Safe to push to GitHub."
else
    echo ""
    echo "❌ ERROR: .coverage file not created!"
    echo "Check your coverage installation:"
    echo "  pip show coverage"
    echo "  pip show pytest-cov"
fi

# For specific service testing (example)
echo ""
echo "=== Test Specific Service (example) ==="
echo "To test a specific service quickly:"
echo "  coverage run --source=app --branch -m pytest -v tests/*booking*.py"
echo "  coverage report --include='app/services/booking_service.py'"
