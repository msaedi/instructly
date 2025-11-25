#!/usr/bin/env bash
#
# Pre-commit hook: Block raw /api/, /bookings, /instructors, and /messages strings in frontend app code
# Part of Phase 4+ API architecture refactor (Phase 7+: bookings + instructors v1, Phase 10: messages v1)
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

# Patterns to exclude (these are allowed to have /api/, /bookings, /instructors, and /messages strings)
# Phase 9: Removed lib/api/bookings.ts from allowlist (file deleted)
# Phase 10: Added messages service layer files to allowlist (use v1 endpoints)
ALLOWED_PATTERNS=(
  "src/api/generated/"
  "src/api/orval-mutator.ts"
  "src/api/services/"
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
  "lib/beta-config.ts"
  "features/shared/api/"
  "services/messageService.ts"
  "hooks/useSSEMessages.ts"
  "hooks/useMessageQueries.ts"
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

VIOLATIONS_API=()
VIOLATIONS_BOOKINGS=()
VIOLATIONS_INSTRUCTORS=()
VIOLATIONS_MESSAGES=()

# Check each file for raw /api/, /bookings, /instructors, and /messages strings
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
  if grep -nP '["'\''`]/api/' "$file" > /dev/null 2>&1; then
    VIOLATIONS_API+=("$file")
  fi

  # Search for /bookings in string literals (Phase 7: block legacy bookings endpoints)
  if grep -nP '["'\''`]/bookings' "$file" > /dev/null 2>&1; then
    VIOLATIONS_BOOKINGS+=("$file")
  fi

  # Search for /instructors in string literals (Phase 7+: block legacy instructor endpoints)
  if grep -nP '["'\''`]/instructors(?![/])' "$file" > /dev/null 2>&1; then
    VIOLATIONS_INSTRUCTORS+=("$file")
  fi

  # Search for /messages in string literals (Phase 10: block legacy messages endpoints)
  if grep -nP '["'\''`]/messages(?![/])' "$file" > /dev/null 2>&1; then
    VIOLATIONS_MESSAGES+=("$file")
  fi
done

# If violations found, report and exit with error
if [ ${#VIOLATIONS_API[@]} -gt 0 ] || [ ${#VIOLATIONS_BOOKINGS[@]} -gt 0 ] || [ ${#VIOLATIONS_INSTRUCTORS[@]} -gt 0 ] || [ ${#VIOLATIONS_MESSAGES[@]} -gt 0 ]; then
  echo "❌ API Architecture Guardrail: Raw endpoint strings detected"
  echo ""

  if [ ${#VIOLATIONS_API[@]} -gt 0 ]; then
    echo "Files with raw /api/ strings:"
    for file in "${VIOLATIONS_API[@]}"; do
      echo "  - $file"
      grep -nP '["'\''`]/api/' "$file" | head -3 | sed 's/^/      /'
      echo ""
    done
  fi

  if [ ${#VIOLATIONS_BOOKINGS[@]} -gt 0 ]; then
    echo "Files with raw /bookings strings (Phase 7 migration):"
    for file in "${VIOLATIONS_BOOKINGS[@]}"; do
      echo "  - $file"
      grep -nP '["'\''`]/bookings' "$file" | head -3 | sed 's/^/      /'
      echo ""
    done
  fi

  if [ ${#VIOLATIONS_INSTRUCTORS[@]} -gt 0 ]; then
    echo "Files with raw /instructors strings (Phase 7+ instructor migration):"
    for file in "${VIOLATIONS_INSTRUCTORS[@]}"; do
      echo "  - $file"
      grep -nP '["'\''`]/instructors(?![/])' "$file" | head -3 | sed 's/^/      /'
      echo ""
    done
  fi

  if [ ${#VIOLATIONS_MESSAGES[@]} -gt 0 ]; then
    echo "Files with raw /messages strings (Phase 10 messages migration):"
    for file in "${VIOLATIONS_MESSAGES[@]}"; do
      echo "  - $file"
      grep -nP '["'\''`]/messages(?![/])' "$file" | head -3 | sed 's/^/      /'
      echo ""
    done
  fi

  echo "❌ Use Orval-generated hooks from @/src/api/services/* instead of raw endpoint strings."
  echo "   For bookings: import from @/src/api/services/bookings or @/src/api/services/instructor-bookings"
  echo "   For instructors: import from @/src/api/services/instructors"
  echo "   For messages: import from @/src/api/services/messages"
  echo "   See: docs/architecture/api-refactor-phase-7.md"
  exit 1
fi

exit 0
