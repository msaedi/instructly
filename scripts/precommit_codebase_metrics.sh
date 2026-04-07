#!/usr/bin/env bash
set -euo pipefail

# Re-entry guard: prevent recursive invocation when nested pre-commit runs
# accidentally re-trigger this hook.
if [[ -n "${CODEBASE_METRICS_RUNNING:-}" ]]; then
    exit 0
fi
export CODEBASE_METRICS_RUNNING=1

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Skip doc-only and config-only commits.
if [[ -z "$(git diff --cached --name-only -- 'backend/' 'frontend/')" ]]; then
    echo "[pre-commit] No backend/frontend changes, skipping codebase metrics"
    exit 0
fi

METRICS_FILE="metrics_history.json"
SKIP_HOOKS="codebase-metrics,mypy-strict-gate,backend-no-focused-tests,frontend-no-focused-tests"

echo "Generating codebase metrics..."
python backend/scripts/codebase_metrics.py > "$METRICS_FILE"

# Format only the generated metrics file without re-entering expensive
# filename-agnostic hooks or recursively re-entering this same hook.
SKIP="$SKIP_HOOKS" pre-commit run --files "$METRICS_FILE"

git add "$METRICS_FILE"

exit 0
