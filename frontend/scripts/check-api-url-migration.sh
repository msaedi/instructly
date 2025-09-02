#!/bin/bash

# Script to verify NEXT_PUBLIC_API_URL has been completely migrated to NEXT_PUBLIC_API_BASE
# This should be run in CI to prevent regression

echo "🔍 Checking for deprecated NEXT_PUBLIC_API_URL usage..."

# Files to exclude from the check (apiBase.ts contains the intentional guard, tests verify the guard)
EXCLUDE_PATTERNS="-e lib/apiBase.ts -e __tests__/apiBase.test.ts"

# Check for any remaining NEXT_PUBLIC_API_URL references
FOUND_FILES=$(grep -r "NEXT_PUBLIC_API_URL" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" --include="*.json" --include="*.env*" . 2>/dev/null | grep -v "node_modules" | grep -v ".next" | grep -v $EXCLUDE_PATTERNS)

if [ -n "$FOUND_FILES" ]; then
    echo "❌ Found deprecated NEXT_PUBLIC_API_URL usage in the following files:"
    echo "$FOUND_FILES"
    echo ""
    echo "Please update these files to use NEXT_PUBLIC_API_BASE instead."
    exit 1
else
    echo "✅ No deprecated NEXT_PUBLIC_API_URL usage found!"
    echo "All files correctly use NEXT_PUBLIC_API_BASE."
fi

# Verify that apiBase.ts contains the guard
if ! grep -q "NEXT_PUBLIC_API_URL is deprecated" lib/apiBase.ts 2>/dev/null; then
    echo "⚠️  Warning: lib/apiBase.ts doesn't contain the deprecation guard"
    exit 1
fi

echo "✅ Deprecation guard is in place in lib/apiBase.ts"
echo "🎉 API URL migration check passed!"
