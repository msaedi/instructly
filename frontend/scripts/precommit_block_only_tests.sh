#!/usr/bin/env bash
# Block .only() in frontend test files (but allow conditional .skip())
#
# This prevents accidentally committing focused tests that skip other tests.
# Conditional .skip() patterns like test.skip(!isInstructor(workerInfo), ...) are allowed.

set -euo pipefail

# Find staged frontend test files
FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '^frontend/.*\.(test|spec)\.(ts|tsx|js|jsx)$' || true)

if [ -z "$FILES" ]; then
  exit 0
fi

# Pattern matches: .only(, it.only(, test.only(, describe.only(
# Does NOT match .skip() since conditional skips are valid
ONLY_PATTERN='\.only\s*\('

violations=""

for file in $FILES; do
  # Check for .only() patterns
  matches=$(grep -nE "$ONLY_PATTERN" "$file" 2>/dev/null || true)
  if [ -n "$matches" ]; then
    violations="${violations}${file}:\n${matches}\n\n"
  fi
done

if [ -n "$violations" ]; then
  echo "============================================" >&2
  echo "ERROR: Found .only() in staged test files" >&2
  echo "============================================" >&2
  echo "" >&2
  echo "Focused tests prevent other tests from running." >&2
  echo "Remove .only() before committing." >&2
  echo "" >&2
  echo "Offending files:" >&2
  echo -e "$violations" >&2
  exit 1
fi

exit 0
