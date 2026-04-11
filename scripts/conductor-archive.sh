#!/usr/bin/env bash
set -u

log() {
  echo "[conductor-archive] $*"
}

sanitize_workspace_name() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr '-' '_' | tr -c '[:alnum:]_' '_'
}

load_int_db_connection() {
  env_path="$1"

  eval "$(
    python3 - "$env_path" <<'PY'
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import re
import shlex
import sys

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

parsed = urlparse(selected[0][1])
query = parse_qs(parsed.query)
values = {
    "INT_DB_NAME": unquote((parsed.path or "").lstrip("/")),
    "INT_DB_HOST": parsed.hostname or "",
    "INT_DB_PORT": str(parsed.port or ""),
    "INT_DB_USER": unquote(parsed.username or ""),
    "INT_DB_PASSWORD": unquote(parsed.password or ""),
    "INT_DB_SSLMODE": query.get("sslmode", [""])[0],
}

for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
  )"
}

run_psql() {
  if [ -n "${INT_DB_PASSWORD:-}" ] && [ -n "${INT_DB_SSLMODE:-}" ]; then
    PGPASSWORD="$INT_DB_PASSWORD" PGSSLMODE="$INT_DB_SSLMODE" psql "$@"
  elif [ -n "${INT_DB_PASSWORD:-}" ]; then
    PGPASSWORD="$INT_DB_PASSWORD" psql "$@"
  elif [ -n "${INT_DB_SSLMODE:-}" ]; then
    PGSSLMODE="$INT_DB_SSLMODE" psql "$@"
  else
    psql "$@"
  fi
}

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TARGET_BACKEND_ENV="$WORKSPACE_ROOT/backend/.env"

if [ -z "${CONDUCTOR_WORKSPACE_NAME:-}" ]; then
  log "Skipping database cleanup; CONDUCTOR_WORKSPACE_NAME is not set"
  exit 0
fi

if [ ! -f "$TARGET_BACKEND_ENV" ]; then
  log "Skipping database cleanup; backend/.env not found"
  exit 0
fi

WORKSPACE_SUFFIX="$(sanitize_workspace_name "$CONDUCTOR_WORKSPACE_NAME")"
EXPECTED_DB_NAME="instainstru_test_${WORKSPACE_SUFFIX}"

if [ -z "$WORKSPACE_SUFFIX" ]; then
  log "Skipping database cleanup; workspace name produced an empty suffix"
  exit 0
fi

if ! command -v psql >/dev/null 2>&1; then
  log "Skipping database cleanup; psql not found"
  exit 0
fi

if ! load_int_db_connection "$TARGET_BACKEND_ENV"; then
  log "Skipping database cleanup; could not parse backend/.env"
  exit 0
fi

if [ -z "${INT_DB_NAME:-}" ]; then
  log "Skipping database cleanup; no database name found in backend/.env"
  exit 0
fi

if [ "$INT_DB_NAME" != "$EXPECTED_DB_NAME" ]; then
  log "Skipping database cleanup; refusing to drop unexpected database $INT_DB_NAME"
  exit 0
fi

PSQL_ARGS=(-X -v ON_ERROR_STOP=1 -d postgres)

if [ -n "${INT_DB_HOST:-}" ]; then
  PSQL_ARGS+=(-h "$INT_DB_HOST")
fi

if [ -n "${INT_DB_PORT:-}" ]; then
  PSQL_ARGS+=(-p "$INT_DB_PORT")
fi

if [ -n "${INT_DB_USER:-}" ]; then
  PSQL_ARGS+=(-U "$INT_DB_USER")
fi

if run_psql "${PSQL_ARGS[@]}" -c "DROP DATABASE IF EXISTS \"$INT_DB_NAME\""; then
  log "Dropped database $INT_DB_NAME"
else
  log "Failed to drop database $INT_DB_NAME"
fi

exit 0
