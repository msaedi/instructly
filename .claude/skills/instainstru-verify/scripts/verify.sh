#!/usr/bin/env bash
# iNSTAiNSTRU Verification Suite
# Usage: bash verify.sh [backend|frontend|all]
#
# Runs the quality gate sequence in fail-fast mode between steps.
# Each individual step is allowed to finish naturally; the script never
# interrupts an in-flight command just because it has started failing.
# Exit code 0 = all passed. Non-zero = the first failing scope/step failed.

set -euo pipefail

SCOPE="${1:-all}"
FAILURES=0
RESULTS=""
BACKEND_STATUS="NOT_RUN"
FRONTEND_STATUS="NOT_RUN"

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

    # 1. Ruff
    echo "→ Running ruff..."
    if RUFF_OUTPUT=$(cd "$REPO_ROOT" && backend/venv/bin/ruff check backend/ 2>&1); then
        record "ruff" "PASS" "clean"
    else
        ERROR_COUNT=$(echo "$RUFF_OUTPUT" | tail -1)
        record "ruff" "FAIL" "$ERROR_COUNT"
        BACKEND_STATUS="FAIL"
        return 1
    fi

    # 2. mypy
    echo "→ Running mypy..."
    if MYPY_OUTPUT=$(cd "$REPO_ROOT/backend" && venv/bin/mypy --no-incremental app 2>&1); then
        record "mypy" "PASS" "clean"
    else
        ERROR_COUNT=$(echo "$MYPY_OUTPUT" | tail -1)
        record "mypy" "FAIL" "$ERROR_COUNT"
        BACKEND_STATUS="FAIL"
        return 1
    fi

    # 3. Pre-commit
    echo "→ Running pre-commit..."
    if PRECOMMIT_OUTPUT=$(cd "$REPO_ROOT" && backend/venv/bin/pre-commit run --all-files 2>&1); then
        record "Pre-commit" "PASS" "all hooks passed"
    else
        PRECOMMIT_STATUS=$?
        FAILED_HOOKS=$(echo "$PRECOMMIT_OUTPUT" | grep -c "Failed" || true)
        if [[ "$FAILED_HOOKS" -gt 0 ]]; then
            PRECOMMIT_DETAIL="${FAILED_HOOKS} hook(s) failed"
        else
            PRECOMMIT_DETAIL=$(echo "$PRECOMMIT_OUTPUT" | tail -1)
            if [[ -z "$PRECOMMIT_DETAIL" ]]; then
                PRECOMMIT_DETAIL="pre-commit exited with status ${PRECOMMIT_STATUS}"
            fi
        fi
        record "Pre-commit" "FAIL" "$PRECOMMIT_DETAIL"
        BACKEND_STATUS="FAIL"
        return 1
    fi

    # 4. Tests
    echo "→ Running pytest..."
    if TEST_OUTPUT=$(cd "$REPO_ROOT/backend" && venv/bin/pytest tests/ --tb=short -q 2>&1); then
        PASS_LINE=$(echo "$TEST_OUTPUT" | tail -1)
        record "Backend tests" "PASS" "$PASS_LINE"
    else
        PASS_LINE=$(echo "$TEST_OUTPUT" | tail -3)
        record "Backend tests" "FAIL" "$PASS_LINE"
        BACKEND_STATUS="FAIL"
        return 1
    fi

    BACKEND_STATUS="PASS"
    return 0
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
        FRONTEND_STATUS="FAIL"
        cd "$REPO_ROOT"
        return 1
    fi

    # 2. Lint
    echo "→ Running eslint..."
    if LINT_OUTPUT=$(npm run lint 2>&1); then
        record "ESLint" "PASS" "clean"
    else
        record "ESLint" "FAIL" "lint errors or warnings found"
        FRONTEND_STATUS="FAIL"
        cd "$REPO_ROOT"
        return 1
    fi

    # 3. TypeScript (strict-all is the strictest superset — covers typecheck and typecheck:strict)
    echo "→ Running typecheck:strict-all..."
    if npm run typecheck:strict-all 2>&1 > /dev/null; then
        record "typecheck:strict-all" "PASS" "0 errors"
    else
        record "typecheck:strict-all" "FAIL" "strict-all type errors found"
        FRONTEND_STATUS="FAIL"
        cd "$REPO_ROOT"
        return 1
    fi

    # 4. Type coverage
    echo "→ Running type coverage audit..."
    if TYPECOV_OUTPUT=$(npm run --silent audit:typecov 2>&1); then
        record "Type coverage" "PASS" "100%"
    else
        record "Type coverage" "FAIL" "below 100% — any introduced"
        FRONTEND_STATUS="FAIL"
        cd "$REPO_ROOT"
        return 1
    fi

    # 5. npm audit
    echo "→ Running npm audit..."
    if AUDIT_OUTPUT=$(npm audit --omit=dev 2>&1); then
        record "npm audit" "PASS" "0 vulnerabilities"
    else
        VULN_LINE=$(echo "$AUDIT_OUTPUT" | grep -E "vulnerabilities" | tail -1)
        record "npm audit" "FAIL" "$VULN_LINE"
        FRONTEND_STATUS="FAIL"
        cd "$REPO_ROOT"
        return 1
    fi

    FRONTEND_STATUS="PASS"
    cd "$REPO_ROOT"
    return 0
}

# ─── MAIN ──────────────────────────────────────────────────────────

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║  iNSTAiNSTRU VERIFICATION SUITE           ║"
echo "║  Scope: ${SCOPE}                          ║"
echo "╚═══════════════════════════════════════════╝"

case "$SCOPE" in
    backend)
        if ! run_backend; then
            :
        fi
        ;;
    frontend)
        if ! run_frontend; then
            :
        fi
        ;;
    all)
        if ! run_backend; then
            :
        elif ! run_frontend; then
            :
        fi
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
    if [[ "$SCOPE" == "all" && "$BACKEND_STATUS" == "PASS" && "$FRONTEND_STATUS" == "FAIL" ]]; then
        echo "   Backend is already green. Fix frontend failures, then rerun: bash scripts/verify.sh frontend"
    elif [[ "$SCOPE" == "all" && "$BACKEND_STATUS" == "FAIL" ]]; then
        echo "   Stop here. Fix backend failures, then rerun: bash scripts/verify.sh backend"
    else
        echo "   Stop here. Fix the failing step, then rerun: bash scripts/verify.sh ${SCOPE}"
    fi
    exit 1
else
    echo "✅ ALL CHECKS PASSED"
    exit 0
fi
