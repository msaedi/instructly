#!/usr/bin/env bash
set -euo pipefail

# Run ESLint on staged frontend files only.
# pre-commit passes file paths as arguments.

shopt -s extglob nullglob

frontend_files=()
for f in "$@"; do
  if [[ "$f" =~ ^frontend/.*\.(ts|tsx|js|jsx)$ ]]; then
    frontend_files+=("$f")
  fi
done

if [[ ${#frontend_files[@]} -eq 0 ]]; then
  exit 0
fi

cd frontend
npx --yes eslint --max-warnings=0 --report-unused-disable-directives --cache --cache-location .artifacts/.eslintcache "${frontend_files[@]}"
