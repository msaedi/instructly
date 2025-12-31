#!/usr/bin/env bash
set -euo pipefail

# Run ESLint on staged frontend files only.
# pre-commit passes file paths as arguments.

shopt -s extglob nullglob

frontend_files=()
for f in "$@"; do
  if [[ "$f" =~ ^frontend/.*\.(ts|tsx|js|jsx)$ ]]; then
    rel_path="${f#frontend/}"
    frontend_files+=("$rel_path")
  fi
done

if [[ ${#frontend_files[@]} -eq 0 ]]; then
  exit 0
fi

cd frontend
# If node_modules isn't installed (e.g., pre-commit run in CI before npm ci), skip fast.
if [[ ! -d node_modules ]]; then
  echo "[pre-commit] skipping ESLint (frontend/node_modules not installed)"
  exit 0
fi
npx --yes eslint --max-warnings=0 --no-warn-ignored --report-unused-disable-directives --cache --cache-location .artifacts/.eslintcache "${frontend_files[@]}"
