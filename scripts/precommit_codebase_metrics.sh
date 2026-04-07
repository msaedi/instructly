#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

METRICS_FILE="metrics_history.json"
SKIP_HOOKS="codebase-metrics,mypy-strict-gate,backend-no-focused-tests,frontend-no-focused-tests"

echo "Generating codebase metrics..."
python backend/scripts/codebase_metrics.py > "$METRICS_FILE"

# Format only the generated metrics file without re-entering expensive
# filename-agnostic hooks or recursively invoking this hook.
SKIP="$SKIP_HOOKS" pre-commit run --files "$METRICS_FILE"

git add "$METRICS_FILE"

exit 0
