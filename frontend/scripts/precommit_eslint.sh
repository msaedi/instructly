#!/bin/bash
set -euo pipefail

# Run ESLint only on provided file args; fallback to full lint if none
cd "$(dirname "$0")/.."

FILES=("$@")

if [ ${#FILES[@]} -eq 0 ]; then
  npx next lint
  exit $?
fi

# Filter to TS/TSX files inside frontend
FILTERED=()
for f in "${FILES[@]}"; do
  case "$f" in
    *.ts|*.tsx)
      FILTERED+=("$f")
      ;;
  esac
done

if [ ${#FILTERED[@]} -eq 0 ]; then
  exit 0
fi

npx eslint "${FILTERED[@]}"
