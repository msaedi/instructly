#!/usr/bin/env bash
#
# Pre-commit hook: Block raw /api/ strings in frontend app code
# Part of Phase 4 API architecture refactor
#
# Usage: Called by pre-commit with staged files as arguments
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"

# Files to check (passed as arguments by pre-commit)
FILES_TO_CHECK=("$@")

# Exit if no files to check
if [ ${#FILES_TO_CHECK[@]} -eq 0 ]; then
  exit 0
fi

# Patterns to exclude (these are allowed to have /api/ strings)
ALLOWED_PATTERNS=(
  "src/api/generated/"
  "src/api/orval-mutator.ts"
  "orval.config.ts"
  "__tests__/"
  ".test.ts"
  ".test.tsx"
  ".spec.ts"
  ".spec.tsx"
  "e2e/"
  "lib/api.ts"
  "lib/apiBase.ts"
  "lib/betaApi.ts"
  "features/shared/api/"
)

# Check if a file should be excluded
should_exclude() {
  local file="$1"
  for pattern in "${ALLOWED_PATTERNS[@]}"; do
    if [[ "$file" == *"$pattern"* ]]; then
      return 0  # Should exclude
    fi
  done
  return 1  # Should NOT exclude
}

VIOLATIONS=()

# Check each file for raw /api/ strings
for file in "${FILES_TO_CHECK[@]}"; do
  # Skip if file should be excluded
  if should_exclude "$file"; then
    continue
  fi

  # Skip if file doesn't exist (might have been deleted)
  if [ ! -f "$file" ]; then
    continue
  fi

  # Search for /api/ in string literals
  # Using grep with Perl regex to match strings containing /api/
  if grep -nP '["'\''`]/api/' "$file" > /dev/null 2>&1; then
    VIOLATIONS+=("$file")
  fi
done

# If violations found, report and exit with error
if [ ${#VIOLATIONS[@]} -gt 0 ]; then
  echo "❌ Phase 4 API Guardrail: Raw /api/ strings detected"
  echo ""
  echo "The following files contain raw /api/ path strings:"
  for file in "${VIOLATIONS[@]}"; do
    echo "  - $file"
    # Show the offending lines
    grep -nP '["'\''`]/api/' "$file" | head -3 | sed 's/^/      /'
    echo ""
  done
  echo "❌ Use Orval-generated hooks from @/src/api/services/* instead of raw /api/ strings."
  echo "   See: docs/architecture/api-refactor-phase-4.md"
  exit 1
fi

exit 0
