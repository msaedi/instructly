#!/usr/bin/env bash
set -euo pipefail

: "${TEST_DATABASE_URL:=${test_database_url:-}}"
: "${STG_DATABASE_URL:=${stg_database_url:-}}"

if [[ -z "${TEST_DATABASE_URL}" || -z "${STG_DATABASE_URL}" ]]; then
  echo "ERROR: TEST/STG DB URLs not found. Ensure backend/.env has test_database_url and stg_database_url."
  exit 1
fi

echo "Recreating INT and STG with neutral collation (C) and required extensions..."

for raw_url in "${TEST_DATABASE_URL}" "${STG_DATABASE_URL}"; do
  parsed_output=$(URL="${raw_url}" python - <<'PY'
import os
import urllib.parse

url = os.environ["URL"]
parsed = urllib.parse.urlparse(url)
if not parsed.path or parsed.path == "/":
    raise SystemExit("Database name missing in URL")
database = parsed.path.lstrip('/')
base = parsed._replace(path='/postgres')
print(database)
print(urllib.parse.urlunparse(base))
PY
)

  db_name=$(printf '%s\n' "${parsed_output}" | sed -n '1p')
  postgres_url=$(printf '%s\n' "${parsed_output}" | sed -n '2p')

  if [[ -z "${db_name}" ]]; then
    echo "ERROR: Unable to determine database name from URL '${raw_url}'" >&2
    exit 1
  fi

  echo "Dropping/creating ${db_name} ..."
  psql "${postgres_url}" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"${db_name}\";"
  psql "${postgres_url}" -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${db_name}\" TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C';"

  echo "Installing extensions (postgis, vector) on ${db_name} ..."
  psql "${raw_url}" -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
SQL

done

echo "✅ Local DBs ready."
