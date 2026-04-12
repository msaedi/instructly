#!/usr/bin/env sh
# graphify-hook-start
# Auto-rebuilds the knowledge graph after each commit (code files only, no LLM needed).
# Installed by: graphify hook install (migrated to Husky)

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
CHANGED=$(git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --name-only HEAD 2>/dev/null)
if [ -z "$CHANGED" ]; then
    exit 0
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

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

export GRAPHIFY_CHANGED="$CHANGED"
SUMMARY=$("$GRAPHIFY_PYTHON" "$SCRIPT_DIR/_graphify_rebuild.py" --summary 2>&1)
STATUS=$?

case "$STATUS" in
    0)
        mkdir -p "$REPO_ROOT/graphify-out"
        echo "[graphify] Graph rebuild started in background ($SUMMARY)"
        nohup "$GRAPHIFY_PYTHON" "$SCRIPT_DIR/_graphify_rebuild.py" > "$REPO_ROOT/graphify-out/rebuild.log" 2>&1 &
        ;;
    10)
        printf '%s\n' "$SUMMARY"
        ;;
    11)
        ;;
    *)
        printf '%s\n' "$SUMMARY"
        exit "$STATUS"
        ;;
esac
# graphify-hook-end
