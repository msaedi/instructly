#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

IGNORE_FILE="pip-audit.ignore.json"
IGNORE_FLAGS=()
EXTRA_ARGS=("$@")

if [[ -f "$IGNORE_FILE" ]]; then
  # Build --ignore-vuln flags from ignore list
  FLAGS=$(python3 - <<'PY'
import json, sys
try:
    with open('pip-audit.ignore.json', 'r') as f:
        data = json.load(f)
    ids = data.get('ignore', [])
    # Emit flags as space-separated string
    print(' '.join(sum((["--ignore-vuln", vid] for vid in ids), [])))
except Exception as e:
    print('', end='')
PY
)
  # shellcheck disable=SC2206
  IGNORE_FLAGS=($FLAGS)
fi

if ((${#IGNORE_FLAGS[@]})); then
  if ((${#EXTRA_ARGS[@]})); then
    exec pip-audit -r requirements.txt -r requirements-dev.txt --strict "${IGNORE_FLAGS[@]}" "${EXTRA_ARGS[@]}"
  else
    exec pip-audit -r requirements.txt -r requirements-dev.txt --strict "${IGNORE_FLAGS[@]}"
  fi
else
  if ((${#EXTRA_ARGS[@]})); then
    exec pip-audit -r requirements.txt -r requirements-dev.txt --strict "${EXTRA_ARGS[@]}"
  else
    exec pip-audit -r requirements.txt -r requirements-dev.txt --strict
  fi
fi
