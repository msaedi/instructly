#!/usr/bin/env sh
# graphify-checkout-hook-start
# Auto-rebuilds the knowledge graph (code only) when switching branches.
# Installed by: graphify hook install (migrated to Husky)

PREV_HEAD=$1
NEW_HEAD=$2
BRANCH_SWITCH=$3

# Only run on branch switches, not file checkouts
if [ "$BRANCH_SWITCH" != "1" ]; then
    exit 0
fi

# Only run if graphify-out/ exists (graph has been built before)
if [ ! -d "graphify-out" ]; then
    exit 0
fi

# Detect the correct Python interpreter (handles pipx, venv, system installs)
GRAPHIFY_BIN=$(command -v graphify 2>/dev/null)
if [ -n "$GRAPHIFY_BIN" ]; then
    _SHEBANG=$(head -1 "$GRAPHIFY_BIN" | sed 's/^#![[:space:]]*//')
    case "$_SHEBANG" in
        */env\ *) GRAPHIFY_PYTHON="${_SHEBANG#*/env }" ;;
        *)         GRAPHIFY_PYTHON="$_SHEBANG" ;;
    esac
    case "$GRAPHIFY_PYTHON" in
        *[!a-zA-Z0-9/_.-]*) GRAPHIFY_PYTHON="python3" ;;
    esac
    if ! "$GRAPHIFY_PYTHON" -c "import graphify" 2>/dev/null; then
        GRAPHIFY_PYTHON="python3"
    fi
else
    GRAPHIFY_PYTHON="python3"
fi

# Check if graphify is importable before spawning background process
if ! $GRAPHIFY_PYTHON -c "import graphify" 2>/dev/null; then
    echo "[graphify hook] graphify not installed, skipping rebuild"
    exit 0
fi

echo "[graphify] Graph rebuild started in background"
nohup $GRAPHIFY_PYTHON -c "
from graphify.watch import _rebuild_code
from pathlib import Path
try:
    _rebuild_code(Path('.'))
except Exception as exc:
    print(f'[graphify] Rebuild failed: {exc}')
" > graphify-out/rebuild.log 2>&1 &
# graphify-checkout-hook-end
