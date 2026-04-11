#!/usr/bin/env bash
set -e

log() {
  echo "[conductor-setup] $*"
}

link_file() {
  src="$1"
  dest="$2"

  if [ -f "$src" ]; then
    mkdir -p "$(dirname "$dest")"
    rm -rf "$dest"
    ln -sfn "$src" "$dest"
    log "Linked ${dest#$WORKSPACE_ROOT/} -> $src"
  else
    log "Skipping ${dest#$WORKSPACE_ROOT/}; source file not found at $src"
  fi
}

link_dir() {
  src="$1"
  dest="$2"

  if [ -d "$src" ]; then
    mkdir -p "$(dirname "$dest")"
    rm -rf "$dest"
    ln -sfn "$src" "$dest"
    log "Linked ${dest#$WORKSPACE_ROOT/} -> $src"
  else
    log "Skipping ${dest#$WORKSPACE_ROOT/}; source directory not found at $src"
  fi
}

if [ -z "${CONDUCTOR_ROOT_PATH:-}" ]; then
  log "CONDUCTOR_ROOT_PATH is not set."
  exit 1
fi

if [ ! -d "$CONDUCTOR_ROOT_PATH" ]; then
  log "Source repo not found at $CONDUCTOR_ROOT_PATH"
  exit 1
fi

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOURCE_ROOT="$(cd "$CONDUCTOR_ROOT_PATH" && pwd -P)"

if [ "$WORKSPACE_ROOT" = "$SOURCE_ROOT" ]; then
  log "Workspace root matches CONDUCTOR_ROOT_PATH; nothing to set up."
  exit 0
fi

log "Using source repo at $SOURCE_ROOT"
log "Preparing workspace at $WORKSPACE_ROOT"

link_dir "$SOURCE_ROOT/backend/venv" "$WORKSPACE_ROOT/backend/venv"
link_file "$SOURCE_ROOT/.env" "$WORKSPACE_ROOT/.env"
link_file "$SOURCE_ROOT/backend/.env" "$WORKSPACE_ROOT/backend/.env"
link_file "$SOURCE_ROOT/frontend/.env.local" "$WORKSPACE_ROOT/frontend/.env.local"
link_file "$SOURCE_ROOT/mcp-server/.env" "$WORKSPACE_ROOT/mcp-server/.env"
link_dir "$SOURCE_ROOT/graphify-out" "$WORKSPACE_ROOT/graphify-out"

SOURCE_FRONTEND_NODE_MODULES="$SOURCE_ROOT/frontend/node_modules"
TARGET_FRONTEND_NODE_MODULES="$WORKSPACE_ROOT/frontend/node_modules"

if [ -d "$SOURCE_FRONTEND_NODE_MODULES" ]; then
  mkdir -p "$(dirname "$TARGET_FRONTEND_NODE_MODULES")"
  rm -rf "$TARGET_FRONTEND_NODE_MODULES"
  ln -sfn "$SOURCE_FRONTEND_NODE_MODULES" "$TARGET_FRONTEND_NODE_MODULES"
  log "Linked frontend/node_modules -> $SOURCE_FRONTEND_NODE_MODULES"
else
  if [ -d "$TARGET_FRONTEND_NODE_MODULES" ] && [ ! -L "$TARGET_FRONTEND_NODE_MODULES" ]; then
    log "Source frontend/node_modules not found; keeping existing workspace frontend/node_modules"
  else
    rm -rf "$TARGET_FRONTEND_NODE_MODULES"
    log "Source frontend/node_modules not found; running npm ci in frontend/"
    (
      cd "$WORKSPACE_ROOT/frontend"
      npm ci
    )
    log "Installed frontend/node_modules with npm ci"
  fi
fi

PRECOMMIT_BIN="$WORKSPACE_ROOT/backend/venv/bin/pre-commit"
if git -C "$WORKSPACE_ROOT" config --get core.hooksPath >/dev/null 2>&1; then
  log "Skipping pre-commit install — hooks managed by core.hooksPath"
elif [ -x "$PRECOMMIT_BIN" ]; then
  log "Installing pre-commit hooks"
  (
    cd "$WORKSPACE_ROOT"
    "$PRECOMMIT_BIN" install
  )
else
  log "Skipping pre-commit hook install; $PRECOMMIT_BIN not found"
fi

log "Conductor workspace setup complete"
