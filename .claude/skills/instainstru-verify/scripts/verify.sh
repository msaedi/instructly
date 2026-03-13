#!/usr/bin/env bash
# iNSTAiNSTRU Verification Suite
# Usage: bash verify.sh [backend|frontend|all]
#
# Runs the full quality gate sequence and reports pass/fail per step.
# Exit code 0 = all passed. Non-zero = at least one failure.

set -euo pipefail

SCOPE="${1:-all}"
FAILURES=0
RESULTS=""

# Find repo root (look for backend/ and frontend/ directories)
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
# Walk up until we find the repo root
while [[ ! -d "$REPO_ROOT/backend" || ! -d "$REPO_ROOT/frontend" ]]; do
    REPO_ROOT="$(dirname "$REPO_ROOT")"
    if [[ "$REPO_ROOT" == "/" ]]; then
        echo "ERROR: Could not find repo root (looking for backend/ and frontend/ directories)"
        exit 1
    fi
done

record() {
    local step="$1"
    local status="$2"
    local detail="${3:-}"
    if [[ "$status" == "PASS" ]]; then
        RESULTS="${RESULTS}\n  ✅ ${step}: ${detail}"
    else
        RESULTS="${RESULTS}\n  ❌ ${step}: ${detail}"
        FAILURES=$((FAILURES + 1))
    fi
}

# ─── BACKEND ───────────────────────────────────────────────────────

run_backend() {
    echo ""
    echo "═══════════════════════════════════════════"
    echo "  BACKEND VERIFICATION"
    echo "═══════════════════════════════════════════"
    echo ""

    cd "$REPO_ROOT/backend"

    # 1. Tests
    echo "→ Running pytest..."
    if TEST_OUTPUT=$(python -m pytest tests/ --tb=short -q 2>&1); then
        PASS_LINE=$(echo "$TEST_OUTPUT" | tail -1)
        record "Backend tests" "PASS" "$PASS_LINE"
    else
        PASS_LINE=$(echo "$TEST_OUTPUT" | tail -3)
        record "Backend tests" "FAIL" "$PASS_LINE"
    fi

    # 2. mypy
    echo "→ Running mypy..."
    if MYPY_OUTPUT=$(./venv/bin/mypy --no-incremental app 2>&1); then
        record "mypy" "PASS" "clean"
    else
        ERROR_COUNT=$(echo "$MYPY_OUTPUT" | tail -1)
        record "mypy" "FAIL" "$ERROR_COUNT"
    fi

    # 3. Pre-commit
    echo "→ Running pre-commit..."
    if PRECOMMIT_OUTPUT=$(python ../venv/bin/pre-commit run --all-files 2>&1); then
        record "Pre-commit" "PASS" "all hooks passed"
    else
        FAILED_HOOKS=$(echo "$PRECOMMIT_OUTPUT" | grep -c "Failed" || true)
        record "Pre-commit" "FAIL" "${FAILED_HOOKS} hook(s) failed"
    fi

    cd "$REPO_ROOT"
}

# ─── FRONTEND ──────────────────────────────────────────────────────

run_frontend() {
    echo ""
    echo "═══════════════════════════════════════════"
    echo "  FRONTEND VERIFICATION"
    echo "═══════════════════════════════════════════"
    echo ""

    cd "$REPO_ROOT/frontend"

    # 1. Tests
    echo "→ Running jest..."
    if TEST_OUTPUT=$(npm test -- --coverage 2>&1); then
        SUMMARY=$(echo "$TEST_OUTPUT" | grep -E "Tests:|Test Suites:" | tail -2)
        record "Frontend tests" "PASS" "$SUMMARY"
    else
        SUMMARY=$(echo "$TEST_OUTPUT" | grep -E "Tests:|Test Suites:|FAIL" | tail -5)
        record "Frontend tests" "FAIL" "$SUMMARY"
    fi

    # 2. Lint
    echo "→ Running eslint..."
    if LINT_OUTPUT=$(npm run lint 2>&1); then
        record "ESLint" "PASS" "clean"
    else
        record "ESLint" "FAIL" "lint errors found"
    fi

    # 3. TypeScript (all levels)
    echo "→ Running typecheck..."
    if npm run typecheck 2>&1 > /dev/null; then
        record "typecheck" "PASS" "0 errors"
    else
        record "typecheck" "FAIL" "type errors found"
    fi

    echo "→ Running typecheck:strict..."
    if npm run typecheck:strict 2>&1 > /dev/null; then
        record "typecheck:strict" "PASS" "0 errors"
    else
        record "typecheck:strict" "FAIL" "strict type errors found"
    fi

    echo "→ Running typecheck:strict-all..."
    if npm run typecheck:strict-all 2>&1 > /dev/null; then
        record "typecheck:strict-all" "PASS" "0 errors"
    else
        record "typecheck:strict-all" "FAIL" "strict-all type errors found"
    fi

    # 4. Type coverage
    echo "→ Running type coverage audit..."
    if TYPECOV_OUTPUT=$(npm run --silent audit:typecov 2>&1); then
        record "Type coverage" "PASS" "100%"
    else
        record "Type coverage" "FAIL" "below 100% — any introduced"
    fi

    # 5. npm audit
    echo "→ Running npm audit..."
    if AUDIT_OUTPUT=$(npm audit --omit=dev 2>&1); then
        record "npm audit" "PASS" "0 vulnerabilities"
    else
        VULN_LINE=$(echo "$AUDIT_OUTPUT" | grep -E "vulnerabilities" | tail -1)
        record "npm audit" "FAIL" "$VULN_LINE"
    fi

    cd "$REPO_ROOT"
}

# ─── MAIN ──────────────────────────────────────────────────────────

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║  iNSTAiNSTRU VERIFICATION SUITE           ║"
echo "║  Scope: ${SCOPE}                          ║"
echo "╚═══════════════════════════════════════════╝"

case "$SCOPE" in
    backend)
        run_backend
        ;;
    frontend)
        run_frontend
        ;;
    all)
        run_backend
        run_frontend
        ;;
    *)
        echo "Usage: verify.sh [backend|frontend|all]"
        exit 1
        ;;
esac

# ─── REPORT ────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════"
echo "  VERIFICATION REPORT"
echo "═══════════════════════════════════════════"
echo -e "$RESULTS"
echo ""

if [[ $FAILURES -gt 0 ]]; then
    echo "❌ FAILED: ${FAILURES} check(s) did not pass."
    echo "   Fix all failures before reporting task as complete."
    exit 1
else
    echo "✅ ALL CHECKS PASSED"
    exit 0
fi
