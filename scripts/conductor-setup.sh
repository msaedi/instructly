#!/usr/bin/env bash
set -e

log() {
  echo "[conductor-setup] $*"
}

sanitize_workspace_name() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr '-' '_' | tr -c '[:alnum:]_' '_'
}

extract_int_db_name() {
  env_path="$1"

  python3 - "$env_path" <<'PY'
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

env_path = Path(sys.argv[1])
specific_keys = {"DATABASE_URL_INT", "TEST_DATABASE_URL", "test_database_url"}
fallback_keys = {"DATABASE_URL", "database_url"}
assign_re = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(\S+)(\s+#.*)?$")


def parse_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


matches: list[tuple[str, str]] = []
for line in env_path.read_text().splitlines():
    if line.lstrip().startswith("#"):
        continue
    match = assign_re.match(line)
    if not match:
        continue
    key = match.group(2)
    if key in specific_keys or key in fallback_keys:
        matches.append((key, parse_value(match.group(4))))

selected = [item for item in matches if item[0] in specific_keys]
if not selected:
    selected = [item for item in matches if item[0] in fallback_keys]
if not selected:
    raise SystemExit(f"No INT database URL found in {env_path}")

db_name = urlparse(selected[0][1]).path.lstrip("/")
if not db_name:
    raise SystemExit(f"Could not determine database name from {env_path}")

print(db_name)
PY
}

write_isolated_backend_env() {
  source_env="$1"
  target_env="$2"
  workspace_suffix="$3"

  python3 - "$source_env" "$target_env" "$workspace_suffix" <<'PY'
from pathlib import Path
import re
import sys
from urllib.parse import urlparse, urlunparse

source_env = Path(sys.argv[1])
target_env = Path(sys.argv[2])
workspace_suffix = sys.argv[3]
specific_keys = {"DATABASE_URL_INT", "TEST_DATABASE_URL", "test_database_url"}
fallback_keys = {"DATABASE_URL", "database_url"}
assign_re = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(\S+)(\s+#.*)?$")


def parse_value(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1], value[0]
    return value, ""


def render_value(value: str, quote: str) -> str:
    if quote:
        return f"{quote}{value}{quote}"
    return value


lines = source_env.read_text().splitlines()
matches: list[tuple[int, str, str, str, str, str]] = []
for index, line in enumerate(lines):
    if line.lstrip().startswith("#"):
        continue
    match = assign_re.match(line)
    if not match:
        continue
    key = match.group(2)
    if key in specific_keys or key in fallback_keys:
        matches.append(
            (
                index,
                match.group(1),
                key,
                match.group(3),
                match.group(4),
                match.group(5) or "",
            )
        )

selected = [item for item in matches if item[2] in specific_keys]
if not selected:
    selected = [item for item in matches if item[2] in fallback_keys]
if not selected:
    raise SystemExit(f"No INT database URL found in {source_env}")

first_value, _ = parse_value(selected[0][4])
parsed_first = urlparse(first_value)
base_db_name = parsed_first.path.lstrip("/")
if not base_db_name:
    raise SystemExit(f"Could not determine database name from {source_env}")

isolated_db_name = f"{base_db_name}_{workspace_suffix}"

for index, prefix, key, separator, raw_value, comment in selected:
    current_value, quote = parse_value(raw_value)
    parsed = urlparse(current_value)
    rewritten = urlunparse(parsed._replace(path=f"/{isolated_db_name}"))
    lines[index] = f"{prefix}{key}{separator}{render_value(rewritten, quote)}{comment}"

target_env.write_text("\n".join(lines) + "\n")
print(isolated_db_name)
PY
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

if [ -n "${CONDUCTOR_WORKSPACE_NAME:-}" ]; then
  SOURCE_BACKEND_ENV="$SOURCE_ROOT/backend/.env"
  TARGET_BACKEND_ENV="$WORKSPACE_ROOT/backend/.env"
  WORKSPACE_SUFFIX="$(sanitize_workspace_name "$CONDUCTOR_WORKSPACE_NAME")"

  if [ -z "$WORKSPACE_SUFFIX" ]; then
    log "CONDUCTOR_WORKSPACE_NAME produced an empty database suffix"
    exit 1
  fi

  if [ ! -f "$SOURCE_BACKEND_ENV" ]; then
    log "Cannot create isolated backend/.env; source file not found at $SOURCE_BACKEND_ENV"
    exit 1
  fi

  ISOLATED_DB_NAME="$(extract_int_db_name "$SOURCE_BACKEND_ENV")_${WORKSPACE_SUFFIX}"
  SHOULD_RESET_ISOLATED_DB="1"

  if [ -f "$TARGET_BACKEND_ENV" ] && [ ! -L "$TARGET_BACKEND_ENV" ]; then
    CURRENT_DB_NAME="$(extract_int_db_name "$TARGET_BACKEND_ENV" 2>/dev/null || true)"
    if [ "$CURRENT_DB_NAME" = "$ISOLATED_DB_NAME" ]; then
      SHOULD_RESET_ISOLATED_DB="0"
      log "Isolated backend/.env already configured for $ISOLATED_DB_NAME"
    else
      mkdir -p "$(dirname "$TARGET_BACKEND_ENV")"
      ISOLATED_DB_NAME="$(write_isolated_backend_env "$SOURCE_BACKEND_ENV" "$TARGET_BACKEND_ENV" "$WORKSPACE_SUFFIX")"
      log "Created isolated DB: $ISOLATED_DB_NAME"
    fi
  else
    rm -f "$TARGET_BACKEND_ENV"
    mkdir -p "$(dirname "$TARGET_BACKEND_ENV")"
    ISOLATED_DB_NAME="$(write_isolated_backend_env "$SOURCE_BACKEND_ENV" "$TARGET_BACKEND_ENV" "$WORKSPACE_SUFFIX")"
    log "Created isolated DB: $ISOLATED_DB_NAME"
  fi

  BACKEND_PYTHON="$WORKSPACE_ROOT/backend/venv/bin/python"
  if [ ! -x "$BACKEND_PYTHON" ]; then
    log "Cannot prepare isolated DB; backend Python not found at $BACKEND_PYTHON"
    exit 1
  fi

  (
    cd "$WORKSPACE_ROOT"
    if [ "$SHOULD_RESET_ISOLATED_DB" = "1" ]; then
      log "Resetting schema for $ISOLATED_DB_NAME"
      "$BACKEND_PYTHON" backend/scripts/reset_schema.py int --force --yes
    fi
    log "Preparing isolated DB: $ISOLATED_DB_NAME"
    "$BACKEND_PYTHON" backend/scripts/prep_db.py int --force --yes --migrate --seed-all
  )
else
  log "Skipping DB isolation; CONDUCTOR_WORKSPACE_NAME is not set"
fi

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
