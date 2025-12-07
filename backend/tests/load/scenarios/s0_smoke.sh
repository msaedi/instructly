#!/bin/bash
# S0 — Smoke / Baseline Test
# Purpose: Sanity check; establish baseline metrics
# Users: 10 | Ramp: 2/sec | Duration: 5 minutes
# Success criteria: 0 errors, e2e_full_latency P95 < 500ms

set -e

# Configuration defaults (can be overridden by environment variables)
LOADTEST_BASE_URL="${LOADTEST_BASE_URL:-https://preview-api.instainstru.com}"
LOADTEST_USERS="${LOADTEST_USERS:-sarah.chen@example.com,emma.johnson@example.com}"
LOADTEST_PASSWORD="${LOADTEST_PASSWORD:-Test1234}"
LOADTEST_SSE_HOLD_SECONDS="${LOADTEST_SSE_HOLD_SECONDS:-25}"

# Scenario parameters
USERS=10
SPAWN_RATE=2
DURATION="5m"
SCENARIO_NAME="s0_smoke"

# Create timestamped output directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="${SCRIPT_DIR}/../results/${SCENARIO_NAME}_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

echo "=============================================="
echo "  S0: Smoke / Baseline Test"
echo "=============================================="
echo "Target:     $LOADTEST_BASE_URL"
echo "Users:      $USERS (ramp: $SPAWN_RATE/sec)"
echo "Duration:   $DURATION"
echo "Output:     $OUTPUT_DIR"
echo "=============================================="
echo ""

# Export environment variables for locust
export LOADTEST_BASE_URL
export LOADTEST_USERS
export LOADTEST_PASSWORD
export LOADTEST_SSE_HOLD_SECONDS

# Run locust
cd "$SCRIPT_DIR/.."
locust -f locustfile.py \
    --headless \
    -u "$USERS" \
    -r "$SPAWN_RATE" \
    -t "$DURATION" \
    --csv="$OUTPUT_DIR/results" \
    --html="$OUTPUT_DIR/report.html"

echo ""
echo "=============================================="
echo "  S0: Test Complete"
echo "=============================================="
echo "Results saved to: $OUTPUT_DIR"
echo ""
echo "Key files:"
echo "  - HTML Report: $OUTPUT_DIR/report.html"
echo "  - Stats CSV:   $OUTPUT_DIR/results_stats.csv"
echo "  - History CSV: $OUTPUT_DIR/results_stats_history.csv"
echo ""
echo "Quick view: open $OUTPUT_DIR/report.html"
echo ""
echo "Success criteria:"
echo "  - 0% error rate"
echo "  - e2e_full_latency P95 < 500ms"
echo "  - send_message P95 < 300ms"
echo "=============================================="
