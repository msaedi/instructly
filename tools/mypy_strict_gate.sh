#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ARTIFACT_DIR="$ROOT_DIR/.artifacts"
BASELINE_FILE="$ARTIFACT_DIR/mypy-baseline.txt"
LATEST_FILE="$ARTIFACT_DIR/mypy-latest.txt"

WRITE_BASELINE=0
for arg in "$@"; do
  if [[ "$arg" == "--write-baseline" ]]; then
    WRITE_BASELINE=1
  fi
done

# 2025-09-26: lowered strict baseline from 700 to 597 (pass-2 tightening).

mkdir -p "$ARTIFACT_DIR"

pushd "$BACKEND_DIR" >/dev/null
mypy app > "$LATEST_FILE" 2>&1 || true
popd >/dev/null

COUNT_LINE=$(grep -Eo 'Found [0-9]+ errors' "$LATEST_FILE" || true)
COUNT=$(echo "$COUNT_LINE" | tail -n1 | awk '{print $2}')
COUNT=${COUNT:-0}
CUR=$COUNT

if [ "$CUR" -gt 0 ]; then
  echo "mypy strict gate: found $CUR errors (hard fail)"
  exit 1
else
  echo "mypy strict gate: clean (0 errors)"
fi

exit 0
