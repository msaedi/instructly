#!/usr/bin/env bash
#
# Pre-commit hook: block inline ESLint suppression comments.
# This prevents regression to "eslint-disable" style bypasses in code.
#

set -euo pipefail

FILES_TO_CHECK=("$@")

if [ ${#FILES_TO_CHECK[@]} -eq 0 ]; then
  exit 0
fi

# Block all inline/file-level disable forms:
#   // eslint-disable-next-line ...
#   // eslint-disable-line ...
#   /* eslint-disable ... */
SUPPRESSION_PATTERN='eslint-disable(-next-line|-line)?'

violations=()

for file in "${FILES_TO_CHECK[@]}"; do
  # pre-commit can pass deleted paths when diff-filter includes D in other hooks
  if [ ! -f "$file" ]; then
    continue
  fi

  if grep -nE "$SUPPRESSION_PATTERN" "$file" >/dev/null 2>&1; then
    violations+=("$file")
  fi
done

if [ ${#violations[@]} -gt 0 ]; then
  echo "❌ Inline ESLint suppressions are not allowed." >&2
  echo "   Remove eslint-disable comments and fix the underlying lint issue." >&2
  echo "" >&2
  echo "Offending files/lines:" >&2

  for file in "${violations[@]}"; do
    echo "  - $file" >&2
    grep -nE "$SUPPRESSION_PATTERN" "$file" | sed 's/^/      /' >&2
  done

  echo "" >&2
  echo "If an exception is absolutely required, use a scoped rule override in eslint.config.mjs." >&2
  exit 1
fi

exit 0
