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

COUNT=$(grep -Eo 'Found [0-9]+ errors' "$LATEST_FILE" | tail -n1 | awk '{print $2}')
COUNT=${COUNT:-0}

if [[ ! -f "$BASELINE_FILE" ]]; then
  if [[ "$WRITE_BASELINE" -eq 1 ]]; then
    echo "$COUNT" > "$BASELINE_FILE"
    echo "mypy baseline initialized at ${COUNT} errors"
    exit 0
  fi

  echo "mypy strict gate: baseline file missing; rerun with --write-baseline to initialize" >&2
  exit 1
fi

BASELINE=$(cat "$BASELINE_FILE" | tr -d '\r')
BASELINE=${BASELINE:-0}

if (( COUNT > BASELINE )); then
  echo "mypy strict gate failed: error count ${COUNT} exceeded baseline ${BASELINE}" >&2
  exit 1
fi

if (( COUNT < BASELINE )); then
  if [[ "$WRITE_BASELINE" -eq 1 ]]; then
    echo "$COUNT" > "$BASELINE_FILE"
    echo "mypy strict gate: error count decreased from ${BASELINE} to ${COUNT}" >&2
  else
    echo "mypy strict gate: error count decreased from ${BASELINE} to ${COUNT} (baseline unchanged)" >&2
  fi
else
  if [[ "$WRITE_BASELINE" -eq 1 ]]; then
    echo "$COUNT" > "$BASELINE_FILE"
  fi
  echo "mypy strict gate: error count stable at ${COUNT}" >&2
fi

exit 0
