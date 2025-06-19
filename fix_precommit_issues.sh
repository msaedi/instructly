#!/bin/bash
# fix_precommit_issues.sh
# Script to fix pre-commit issues and get everything passing

echo "🚀 X-Team Pre-commit Fixer - Let's get this working!"

# Stage all the auto-formatted files
echo "📝 Staging all auto-formatted files..."
git add .

# Run pre-commit again to see what's left
echo "🔍 Running pre-commit again to check remaining issues..."
pre-commit run --all-files --show-diff-on-failure > precommit_output.txt 2>&1

# Check if flake8 is still failing
if grep -q "flake8.*Failed" precommit_output.txt; then
    echo "⚠️  Flake8 still has issues. Let's see what they are..."
    cd backend
    flake8 . --config=../.flake8 --format='%(path)s:%(row)d:%(col)d: %(code)s %(text)s' > ../flake8_errors.txt 2>&1
    cd ..

    echo "📊 Flake8 errors summary:"
    cat flake8_errors.txt | grep -E "E[0-9]{3}|F[0-9]{3}|W[0-9]{3}" | cut -d: -f4 | sort | uniq -c | sort -nr
fi

# If everything is passing, we're done!
if ! grep -q "Failed" precommit_output.txt; then
    echo "✅ All pre-commit hooks are passing! You can commit now."
    exit 0
fi

echo ""
echo "📋 Summary of remaining issues:"
echo "--------------------------------"

# Check each hook status
for hook in autoflake black isort flake8 prettier eslint; do
    if grep -q "$hook.*Failed" precommit_output.txt; then
        echo "❌ $hook - Still has issues"
    else
        echo "✅ $hook - Passing"
    fi
done

echo ""
echo "🔧 Next steps:"
echo "1. Review flake8_errors.txt for Python linting issues"
echo "2. For urgent commits, use: git commit --no-verify -m 'your message'"
echo "3. Or fix the remaining issues and run: pre-commit run --all-files"

# Show first 10 flake8 errors if any
if [ -f flake8_errors.txt ]; then
    echo ""
    echo "📌 First 10 flake8 errors:"
    head -10 flake8_errors.txt
fi
