#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
REPORT_DIR="${ROOT_DIR}/docs/tech"
OUTPUT_FILE="${REPORT_DIR}/coverage_snapshot.md"

mkdir -p "${REPORT_DIR}"

cd "${BACKEND_DIR}"

pytest --cov=app --cov-report=term-missing -q "$@"

if command -v coverage >/dev/null 2>&1; then
  coverage json -o coverage.json >/dev/null 2>&1 || true
fi

BACKEND_DIR="${BACKEND_DIR}" OUTPUT_FILE="${OUTPUT_FILE}" python - <<'PY'
import json
import os
from datetime import datetime, timezone

backend_dir = os.environ["BACKEND_DIR"]
output_file = os.environ["OUTPUT_FILE"]
coverage_json = os.path.join(backend_dir, "coverage.json")

timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
percent = "N/A"

if os.path.exists(coverage_json):
    with open(coverage_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    totals = data.get("totals", {})
    display = totals.get("percent_covered_display")
    if display:
        percent = display
    else:
        covered = totals.get("percent_covered")
        if covered is not None:
            percent = f"{covered:.1f}"

with open(output_file, "w", encoding="utf-8") as fh:
    fh.write("# Coverage Snapshot\n\n")
    fh.write(f"- Generated: {timestamp}\n")
    fh.write(f"- Total Coverage: {percent}%\n")
PY

rm -f coverage.json >/dev/null 2>&1 || true
