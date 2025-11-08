#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 app/path1.py [app/path2.py ...]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

STUB_FILE="$(mktemp /tmp/mypy_shadow_stub.XXXXXX.py)"
trap 'rm -f "$STUB_FILE"' EXIT
printf '"""stub"""\n' > "$STUB_FILE"

SHADOW_ARGS=()
for target in "$@"; do
  SHADOW_ARGS+=(--shadow-file "$target" "$STUB_FILE")
done

unset MYPYPATH PYTHONPATH || true

LOG_FILE="$(mktemp /tmp/mypy_shadow_log.XXXXXX.txt)"
trap 'rm -f "$STUB_FILE" "$LOG_FILE"' EXIT

set +e
./venv/bin/mypy --no-incremental "${SHADOW_ARGS[@]}" app | tee "$LOG_FILE"
status=$?
set -e

if grep -q "Internal error: unresolved placeholder type None" "$LOG_FILE"; then
  echo "[warn] Crash still present (exit $status). See $LOG_FILE for details."
else
  if [ "$status" -eq 0 ]; then
    echo "[info] Crash disappeared (mypy exited cleanly)."
  else
    echo "[info] Crash disappeared but mypy reported regular errors (exit $status). See $LOG_FILE."
  fi
fi
