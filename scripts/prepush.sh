#!/usr/bin/env bash
set -euo pipefail

echo "[pre-push] Backend: ruff F+I"
(cd backend && ruff check app --select F,I)

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
  echo "[pre-push] Frontend warn-mode: audit:deadcode:ci"
  (cd frontend && npm run --silent audit:deadcode:ci) || true

  # Removed audit:lhci from pre-push (still runs in CI)

  echo "[pre-push] Frontend warn-mode: audit:typecov"
  (cd frontend && npm run --silent audit:typecov) || true
else
  echo "[pre-push] FAST_HOOKS=1 set -> skipping warn-mode audits"
fi

echo "[pre-push] ✅ All fail-gates passed"
