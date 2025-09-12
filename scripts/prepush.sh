#!/usr/bin/env bash
set -euo pipefail

run_ruff() {
  if command -v ruff >/dev/null 2>&1; then
    ruff "$@"
  elif [ -x "backend/.venv/bin/ruff" ]; then
    "backend/.venv/bin/ruff" "$@"
  elif command -v python3 >/dev/null 2>&1 && python3 -c 'import ruff' 2>/dev/null; then
    python3 -m ruff "$@"
  else
    echo "[pre-push] ruff not found. Install with 'brew install ruff' or 'pipx install ruff', or ensure backend/.venv has ruff installed (pip install ruff)." >&2
    return 127
  fi
}

if [[ "${SKIP_RUFF:-0}" == "1" ]]; then
  echo "[pre-push] SKIP_RUFF=1 -> skipping ruff"
else
  echo "[pre-push] Backend: ruff F+I"
  (cd backend && run_ruff check app --select F,I)
fi

echo "[pre-push] Backend: mypy schemas + routes/internal.py (fail-gate)"
(cd backend && mypy app/schemas app/routes/internal.py)

echo "[pre-push] Backend: pytest smoke (rate headers)"
(cd backend && \
  if [[ -f tests/integration/test_rate_headers_smoke.py ]]; then \
    TZ=UTC pytest -q tests/integration/test_rate_headers_smoke.py; \
  else \
    echo "[pre-push] (info) smoke test file not found: tests/integration/test_rate_headers_smoke.py — skipping"; \
  fi)

echo "[pre-push] Frontend: typecheck:strict-all"
(cd frontend && npm run --silent typecheck:strict-all)

echo "[pre-push] Frontend: build"
(cd frontend && npm run --silent build)

echo "[pre-push] Frontend: size budget"
(cd frontend && npm run --silent size)
echo "[pre-push] Secrets scan (gitleaks)"
if [[ "${GITLEAKS_ALLOW:-0}" == "1" ]]; then
  echo "[pre-push] GITLEAKS_ALLOW=1 set -> skipping gitleaks"
else
  gitleaks protect --no-banner --redact --verbose --config .gitleaks.toml
fi

echo "[pre-push] Frontend: type:smoke:ci"
(cd frontend && npm run --silent type:smoke:ci)

echo "[pre-push] Frontend: verify:runtime-validation-bundle"
(cd frontend && npm run --silent verify:runtime-validation-bundle)

echo "[pre-push] Frontend: audit:contract:ci"
(cd frontend && npm run --silent audit:contract:ci)

if [[ "${FAST_HOOKS:-0}" != "1" ]]; then
  echo "[pre-push] Frontend: dep-cruiser (fail)"
  (cd frontend && npx --yes dependency-cruiser --config dependency-cruiser.config.cjs --ts-config tsconfig.json app components features hooks lib --output-type err)

  echo "[pre-push] Frontend: ts-prune (warn)"
  (cd frontend && mkdir -p .artifacts && npx --yes ts-prune -p tsconfig.json | grep -v -f ts-prune-allowlist.txt | tee .artifacts/ts-prune.prepush.txt) || true
  echo "[pre-push] Frontend warn-mode: audit:deadcode:ci"
  (cd frontend && npm run --silent audit:deadcode:ci) || true

  # Removed audit:lhci from pre-push (still runs in CI)

  echo "[pre-push] Frontend warn-mode: audit:typecov"
  (cd frontend && npm run --silent audit:typecov) || true
else
  echo "[pre-push] FAST_HOOKS=1 set -> skipping warn-mode audits"
fi

echo "[pre-push] ✅ All fail-gates passed"
