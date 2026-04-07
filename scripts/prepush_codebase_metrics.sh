#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

METRICS_FILE="metrics_history.json"

echo "Generating codebase metrics..."
python backend/scripts/codebase_metrics.py > "$METRICS_FILE"

# Apply formatting hooks to the generated file
pre-commit run --files "$METRICS_FILE" || true

# If the file changed since last commit, amend it
if ! git diff --quiet "$METRICS_FILE" 2>/dev/null || \
   ! git diff --cached --quiet "$METRICS_FILE" 2>/dev/null; then
    git add "$METRICS_FILE"
    git commit --amend --no-edit --no-verify
    echo "Amended commit with updated metrics"
fi

exit 0
