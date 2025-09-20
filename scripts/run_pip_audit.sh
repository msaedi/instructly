#!/usr/bin/env bash
set -euo pipefail

AUDIT_ARTIFACT=".artifacts/pip-audit.json"
ALLOWLIST="backend/pip-audit-allowlist.txt"
mkdir -p .artifacts

tmpfile=$(mktemp)
status=0
if ! python -m pip_audit -r backend/requirements.txt -r backend/requirements-dev.txt -f json -o "$tmpfile"; then
  status=$?
fi

export PIP_AUDIT_RESULTS_FILE="$tmpfile"
export PIP_AUDIT_ARTIFACT="$AUDIT_ARTIFACT"
export PIP_AUDIT_ALLOWLIST="$ALLOWLIST"
export PIP_AUDIT_EXIT_STATUS="$status"
python - <<'PY'
import json
import os
from pathlib import Path
import sys

exit_status = int(os.environ.get("PIP_AUDIT_EXIT_STATUS", "0"))
audit_path = Path(os.environ["PIP_AUDIT_RESULTS_FILE"])
if not audit_path.exists() or audit_path.stat().st_size == 0:
    if exit_status != 0:
        print(f"pip-audit: failed to produce output (exit status {exit_status})")
        sys.exit(exit_status)
    print("pip-audit: no output (likely no vulnerabilities)")
    sys.exit(0)

data = json.loads(audit_path.read_text())
if not isinstance(data, dict):
    data = {"dependencies": data}

allow_path = Path(os.environ["PIP_AUDIT_ALLOWLIST"])
allow = set()
if allow_path.exists():
    for line in allow_path.read_text().splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith('#'):
            allow.add(cleaned)

violations = []
for dep in data.get("dependencies", []):
    for vuln in dep.get("vulns", []) or []:
        vuln_id = vuln.get("id") or vuln.get("name")
        if vuln_id and vuln_id in allow:
            continue
        violations.append((dep.get("name"), vuln_id, vuln.get("description", "")))

artifact_path = Path(os.environ["PIP_AUDIT_ARTIFACT"])
artifact_path.write_text(json.dumps(data, indent=2))

if violations:
    print("pip-audit: vulnerabilities detected (fail)")
    for name, vid, desc in violations[:10]:
        print(f"- {name} {vid or 'UNKNOWN'}: {desc[:120]}")
    sys.exit(1)

print("pip-audit: OK")
PY
result=$?
rm -f "$tmpfile"

if [ $result -ne 0 ]; then
  exit $result
fi

exit 0
