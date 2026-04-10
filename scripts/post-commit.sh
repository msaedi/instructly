#!/usr/bin/env sh
# graphify-hook-start
# Auto-rebuilds the knowledge graph after each commit (code files only, no LLM needed).
# Installed by: graphify hook install (migrated to Husky)

CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --name-only HEAD 2>/dev/null)
if [ -z "$CHANGED" ]; then
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

export GRAPHIFY_CHANGED="$CHANGED"
$GRAPHIFY_PYTHON -c "
import os, sys
from pathlib import Path

CODE_EXTS = {
    '.py', '.ts', '.js', '.go', '.rs', '.java', '.cpp', '.c', '.rb', '.swift',
    '.kt', '.cs', '.scala', '.php', '.cc', '.cxx', '.hpp', '.h', '.kts',
}

changed_raw = os.environ.get('GRAPHIFY_CHANGED', '')
changed = [Path(f.strip()) for f in changed_raw.strip().splitlines() if f.strip()]
code_changed = [f for f in changed if f.suffix.lower() in CODE_EXTS and f.exists()]

if not code_changed:
    sys.exit(0)

print(f'[graphify hook] {len(code_changed)} code file(s) changed - rebuilding graph...')

try:
    from graphify.watch import _rebuild_code
    _rebuild_code(Path('.'))
except Exception as exc:
    print(f'[graphify hook] Rebuild failed: {exc}')
    sys.exit(1)
"
# graphify-hook-end
