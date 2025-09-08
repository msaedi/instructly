#!/usr/bin/env bash
set -euo pipefail

min="8.18.0"

version_ge() {
  # Compare semantic versions using Python. Fallback to tuple int compare if packaging not installed.
  python - "$1" "$2" <<'PY'
import sys
v1, v2 = sys.argv[1].lstrip('v'), sys.argv[2].lstrip('v')
try:
    from packaging.version import Version
    sys.exit(0 if Version(v1) >= Version(v2) else 1)
except Exception:
    def to_tuple(v):
        parts = [int(p) for p in v.split('.') if p.isdigit()]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    sys.exit(0 if to_tuple(v1) >= to_tuple(v2) else 1)
PY
}

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "[gitleaks] missing binary. install via 'brew install gitleaks'." >&2
  exit 2
fi

ver="$(gitleaks version 2>/dev/null | awk '{print $NF}')"
if ! version_ge "${ver#v}" "$min"; then
  echo "[gitleaks] version $ver < $min. Please update: brew upgrade gitleaks" >&2
  exit 2
fi

config_flag=()
[[ -f .gitleaks.toml ]] && config_flag=(--config=.gitleaks.toml)

exec gitleaks detect --no-git --redact "${config_flag[@]}" --source .
