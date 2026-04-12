#!/usr/bin/env sh
# graphify-checkout-hook-start
# Auto-rebuilds the knowledge graph (code only) when switching branches.
# Installed by: graphify hook install (migrated to Husky)

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PREV_HEAD=$1
NEW_HEAD=$2
BRANCH_SWITCH=$3

# Only run on branch switches, not file checkouts
if [ "$BRANCH_SWITCH" != "1" ]; then
    exit 0
fi

# Only run if graphify-out/ exists (graph has been built before)
if [ ! -d "$REPO_ROOT/graphify-out" ]; then
    exit 0
fi

pick_graphify_python() {
    if [ -x "$REPO_ROOT/backend/venv/bin/python" ] && \
        "$REPO_ROOT/backend/venv/bin/python" -c "import graphify" 2>/dev/null; then
        printf '%s\n' "$REPO_ROOT/backend/venv/bin/python"
        return 0
    fi

    if [ -n "${VIRTUAL_ENV:-}" ] && \
        [ -x "$VIRTUAL_ENV/bin/python" ] && \
        "$VIRTUAL_ENV/bin/python" -c "import graphify" 2>/dev/null; then
        printf '%s\n' "$VIRTUAL_ENV/bin/python"
        return 0
    fi

    GRAPHIFY_BIN=$(command -v graphify 2>/dev/null || true)
    if [ -n "$GRAPHIFY_BIN" ]; then
        SHEBANG=$(head -1 "$GRAPHIFY_BIN" | sed 's/^#![[:space:]]*//')
        case "$SHEBANG" in
            */env\ *) CANDIDATE_PYTHON="${SHEBANG#*/env }" ;;
            *)         CANDIDATE_PYTHON="$SHEBANG" ;;
        esac
        case "$CANDIDATE_PYTHON" in
            *[!a-zA-Z0-9/_.-]*) CANDIDATE_PYTHON="python3" ;;
        esac
        if "$CANDIDATE_PYTHON" -c "import graphify" 2>/dev/null; then
            printf '%s\n' "$CANDIDATE_PYTHON"
            return 0
        fi
    fi

    printf '%s\n' "python3"
}

GRAPHIFY_PYTHON=$(pick_graphify_python)
echo "[graphify hook] Using python: $GRAPHIFY_PYTHON"

# Check if graphify is importable before spawning background process
if ! "$GRAPHIFY_PYTHON" -c "import graphify" 2>/dev/null; then
    echo "[graphify hook] graphify not installed, skipping rebuild"
    exit 0
fi

echo "[graphify] Graph rebuild started in background"
nohup "$GRAPHIFY_PYTHON" -c "
from graphify.watch import _rebuild_code
from pathlib import Path
try:
    _rebuild_code(Path('.'))
except Exception as exc:
    print(f'[graphify] Rebuild failed: {exc}')
" > "$REPO_ROOT/graphify-out/rebuild.log" 2>&1 &
# graphify-checkout-hook-end
