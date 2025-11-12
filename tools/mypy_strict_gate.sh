#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ARTIFACT_DIR="$ROOT_DIR/.artifacts"
LATEST_FILE="$ARTIFACT_DIR/mypy-latest.txt"

mkdir -p "$ARTIFACT_DIR"

pushd "$BACKEND_DIR" >/dev/null
mypy app > "$LATEST_FILE" 2>&1 || true
popd >/dev/null

COUNT_LINE=$(grep -Eo 'Found [0-9]+ errors' "$LATEST_FILE" || true)
COUNT=$(echo "$COUNT_LINE" | tail -n1 | awk '{print $2}')
COUNT=${COUNT:-0}
CUR=$COUNT
if ! [[ "$CUR" =~ ^[0-9]+$ ]]; then
  CUR=0
fi

# Hard fail when mypy strict reports any errors
if (( CUR > 0 )); then
  echo "mypy strict gate: found $CUR errors (hard fail)"
  exit 1
else
  echo "mypy strict gate: clean (0 errors)"
fi

exit 0
