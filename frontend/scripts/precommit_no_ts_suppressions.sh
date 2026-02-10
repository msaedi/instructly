#!/usr/bin/env bash
#
# Pre-commit hook: block inline TypeScript type-checking suppression comments.
#
# Blocked everywhere:
#   @ts-ignore   — silently suppresses errors with no safety net
#   @ts-nocheck  — disables type checking for an entire file
#
# Blocked in non-test files only:
#   @ts-expect-error — acceptable in tests (for intentionally invalid types)
#

set -euo pipefail

FILES_TO_CHECK=("$@")

if [ ${#FILES_TO_CHECK[@]} -eq 0 ]; then
  exit 0
fi

# Patterns that are never acceptable
ALWAYS_BLOCKED='@ts-ignore|@ts-nocheck'
# Pattern acceptable only in test files
PROD_ONLY_BLOCKED='@ts-expect-error'

violations=()

for file in "${FILES_TO_CHECK[@]}"; do
  if [ ! -f "$file" ]; then
    continue
  fi

  # @ts-ignore and @ts-nocheck are blocked everywhere
  if grep -nE "$ALWAYS_BLOCKED" "$file" >/dev/null 2>&1; then
    violations+=("$file")
    continue
  fi

  # @ts-expect-error is only blocked in non-test files
  if [[ "$file" != *"__tests__"* && "$file" != *".test."* && "$file" != *".spec."* ]]; then
    if grep -nE "$PROD_ONLY_BLOCKED" "$file" >/dev/null 2>&1; then
      violations+=("$file")
    fi
  fi
done

if [ ${#violations[@]} -gt 0 ]; then
  echo "❌ TypeScript type-checking suppressions are not allowed." >&2
  echo "   Remove @ts-ignore / @ts-expect-error / @ts-nocheck and fix the underlying type error." >&2
  echo "" >&2
  echo "Offending files/lines:" >&2

  for file in "${violations[@]}"; do
    echo "  - $file" >&2
    grep -nE "$ALWAYS_BLOCKED|$PROD_ONLY_BLOCKED" "$file" | sed 's/^/      /' >&2
  done

  echo "" >&2
  echo "In test files, @ts-expect-error is allowed for intentionally invalid type scenarios." >&2
  exit 1
fi

exit 0
