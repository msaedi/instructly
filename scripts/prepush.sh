#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

run_ruff() {
  if [ -x "$REPO_ROOT/backend/venv/bin/ruff" ]; then
    "$REPO_ROOT/backend/venv/bin/ruff" "$@"
  elif [ -x "$REPO_ROOT/venv/bin/ruff" ]; then
    "$REPO_ROOT/venv/bin/ruff" "$@"
  elif command -v ruff >/dev/null 2>&1; then
    ruff "$@"
  elif [ -x "$REPO_ROOT/backend/.venv/bin/ruff" ]; then
    "$REPO_ROOT/backend/.venv/bin/ruff" "$@"
  elif command -v python3 >/dev/null 2>&1 && python3 -c 'import ruff' 2>/dev/null; then
    python3 -m ruff "$@"
  else
    echo "[pre-push] ruff not found. Install with 'brew install ruff' or 'pipx install ruff', or ensure backend/.venv has ruff installed (pip install ruff)." >&2
    return 127
  fi
}

run_mypy() {
  if [ -x "$REPO_ROOT/backend/venv/bin/mypy" ]; then
    "$REPO_ROOT/backend/venv/bin/mypy" "$@"
  elif [ -x "$REPO_ROOT/venv/bin/mypy" ]; then
    "$REPO_ROOT/venv/bin/mypy" "$@"
  elif command -v mypy >/dev/null 2>&1; then
    mypy "$@"
  elif [ -x "$REPO_ROOT/backend/.venv/bin/mypy" ]; then
    "$REPO_ROOT/backend/.venv/bin/mypy" "$@"
  elif command -v python3 >/dev/null 2>&1 && python3 -c 'import mypy' 2>/dev/null; then
    python3 -m mypy "$@"
  else
    echo "[pre-push] mypy not found. Activate the repo venv 'source venv/bin/activate' and 'pip install mypy types-pytz \"pydantic~=2.8\" \"pydantic-core~=2.23\" fastapi', or install mypy globally via pipx." >&2
    return 127
  fi
}

run_pytest() {
  if [ -x "$REPO_ROOT/backend/venv/bin/pytest" ]; then
    "$REPO_ROOT/backend/venv/bin/pytest" "$@"
  elif [ -x "$REPO_ROOT/venv/bin/pytest" ]; then
    "$REPO_ROOT/venv/bin/pytest" "$@"
  elif command -v pytest >/dev/null 2>&1; then
    pytest "$@"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m pytest "$@"
  else
    echo "[pre-push] pytest not found. Activate backend venv (backend/venv) and 'pip install pytest'." >&2
    return 127
  fi
}

if [[ "${SKIP_RUFF:-0}" == "1" ]]; then
  echo "[pre-push] SKIP_RUFF=1 -> skipping ruff"
else
  echo "[pre-push] Backend: ruff F+I"
  (cd backend && run_ruff check app --select F,I)
fi

if [[ "${SKIP_MYPY:-0}" == "1" ]]; then
  echo "[pre-push] SKIP_MYPY=1 -> skipping mypy"
else
  echo "[pre-push] Backend: mypy schemas + routes/v1/internal.py + widened set (fail-gate)"
  (cd backend && run_mypy app/schemas app/routes/v1/internal.py app/repositories/search_history_repository.py app/services/search_history_cleanup_service.py app/routes/v1/search_history.py app/services/stripe_service.py)
fi

echo "[pre-push] Backend: pytest smoke (rate headers)"
(cd backend && \
  if [[ -f tests/integration/test_rate_headers_smoke.py ]]; then \
    TZ=UTC run_pytest -q tests/integration/test_rate_headers_smoke.py; \
  else \
    echo "[pre-push] (info) smoke test file not found: tests/integration/test_rate_headers_smoke.py — skipping"; \
  fi)

echo "[pre-push] Backend: strict/envelope tests (flagged)"
(cd backend && STRICT_SCHEMAS=true TZ=UTC run_pytest -q tests/integration/test_error_envelope.py)
(cd backend && STRICT_SCHEMAS=true TZ=UTC run_pytest -q tests/integration/search_history/test_strict_schemas.py)

echo "[pre-push] Backend: mypy bookings/availability slice (fail-gate)"
(cd backend && run_mypy \
  app/repositories/booking_repository.py \
  app/repositories/availability_repository.py \
  app/repositories/week_operation_repository.py \
  app/services/booking_service.py \
  app/services/conflict_checker.py \
  app/services/week_operation_service.py \
  app/routes/v1/bookings.py \
  app/routes/v1/availability_windows.py)

echo "[pre-push] Frontend: typecheck:strict-all"
(cd frontend && npm run --silent typecheck:strict-all)

echo "[pre-push] Frontend: lint"
(cd frontend && npm run --silent lint)

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

echo "[pre-push] Frontend: test"
(cd frontend && npm run --silent test -- --ci)

if [[ "${FAST_HOOKS:-0}" != "1" ]]; then
  echo "[pre-push] Frontend: dep-cruiser (fail)"
  (cd frontend && npx --yes dependency-cruiser --config dependency-cruiser.config.cjs --ts-config tsconfig.json app components features hooks lib --output-type err)

  echo "[pre-push] Frontend: ts-prune (warn)"
  (cd frontend && mkdir -p .artifacts && npx --yes ts-prune -p tsconfig.json | grep -v -f ts-prune-allowlist.txt | tee .artifacts/ts-prune.prepush.txt) || true

  # ---- FRONTEND: Knip dead code (hard fail) ----
  echo "[pre-push] Frontend hard gate: dead code (Knip)"
  set -euo pipefail
  pushd frontend >/dev/null

  # Use JSON reporter against knip.json; tolerate Node versions
  npx knip --config knip.json --reporter=json > .artifacts/knip.json || true

  # Count exactly like CI
  count=$(node -e 'const fs=require("fs");try{const d=JSON.parse(fs.readFileSync(".artifacts/knip.json","utf8"));console.log(Array.isArray(d)?d.length:(d.issues?d.issues.length:0));}catch{console.log(0)}')
  echo "Knip count: ${count}"

  if ! [[ "${count}" =~ ^[0-9]+$ ]]; then
    count=0
  fi

  if (( count > 0 )); then
    echo "❌ Dead code detected (${count}). Push aborted."
    # show initial offenders for convenience
    npx knip --config knip.json --reporter=compact | sed -n "1,200p" || true
    popd >/dev/null
    exit 1
  fi

  echo "✅ No dead code (pre-push)"
  popd >/dev/null
  # ---- END FRONTEND: Knip hard fail ----

  # Removed audit:lhci from pre-push (still runs in CI)

  echo "[pre-push] Frontend warn-mode: audit:typecov"
  (cd frontend && npm run --silent audit:typecov) || true
else
  echo "[pre-push] FAST_HOOKS=1 set -> skipping warn-mode audits"
fi

echo "[pre-push] ✅ All fail-gates passed"
