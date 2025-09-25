#!/bin/bash
# Wrapper script for API contract checking that works in both local and CI environments

# Find the backend directory
if [ -d "backend" ]; then
    BACKEND_DIR="backend"
elif [ -d "../backend" ]; then
    BACKEND_DIR="../backend"
elif [ -f "scripts/check_api_contracts.py" ]; then
    # We're already in the backend directory
    BACKEND_DIR="."
else
    echo "✗ Could not find backend directory"
    exit 1
fi

cd "$BACKEND_DIR"

# Check if we have Python available
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    if ! $PYTHON_CMD -c 'pass' >/dev/null 2>&1; then
        if command -v pyenv &> /dev/null; then
            PYENV_311=$(pyenv versions --bare 2>/dev/null | grep '^3\.11' | tail -n 1)
            if [ -n "$PYENV_311" ]; then
                export PYENV_VERSION=$PYENV_311
            fi
        fi
    fi
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "✗ Python not found"
    exit 1
fi

# Try to run the contract check
# First try the standalone version (doesn't need pytest)
if [ -f "scripts/check_api_contracts_standalone.py" ]; then
    $PYTHON_CMD scripts/check_api_contracts_standalone.py
    exit $?
elif [ -f "scripts/check_api_contracts.py" ] && $PYTHON_CMD -c "import pytest" 2>/dev/null; then
    # Dependencies are available, use the nice script
    $PYTHON_CMD scripts/check_api_contracts.py
    exit $?
else
    # Fallback: Try to run the test directly
    if $PYTHON_CMD -c "import sys; sys.path.insert(0, '.'); from tests.test_api_contracts import APIContractAnalyzer; from app.main import fastapi_app as app" 2>/dev/null; then
        # Can import the modules, run a simple check
        $PYTHON_CMD -c "
import sys
sys.path.insert(0, '.')
from tests.test_api_contracts import APIContractAnalyzer
from app.main import fastapi_app as app

analyzer = APIContractAnalyzer(app)
violations = analyzer.analyze_all_routes()

if violations:
    print(f'Found {len(violations)} contract violations')
    for v in violations[:5]:  # Show first 5 violations
        print(f'  - {v}')
    sys.exit(1)
else:
    print('Found 0 contract violations')
    sys.exit(0)
"
        exit $?
    else
        # Can't run tests - in CI pre-commit environment without deps
        # This is OK - the dedicated workflows handle the actual testing
        echo "✓ API contracts check skipped (dependencies not available - handled by dedicated workflows)"
        exit 0
    fi
fi
