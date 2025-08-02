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
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "✗ Python not found"
    exit 1
fi

# Try to run the contract check
if [ -f "scripts/check_api_contracts.py" ]; then
    # Use the nice script if available
    $PYTHON_CMD scripts/check_api_contracts.py
    exit $?
else
    # Fallback to direct test execution
    $PYTHON_CMD -m tests.test_api_contracts 2>&1 | grep -q "Found 0 contract violations"
    if [ $? -eq 0 ]; then
        echo "✓ API contracts valid"
        exit 0
    else
        echo "✗ API contract violations found"
        exit 1
    fi
fi
