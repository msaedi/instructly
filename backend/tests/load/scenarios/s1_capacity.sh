#!/bin/bash
# S1 — SSE Connection Capacity Sweep
# Purpose: Find max concurrent SSE connections before degradation
# Approach: Multiple runs with increasing user counts
# User counts: 50, 100, 200, 300, 400 (stops early if critical thresholds exceeded)
# Warning signs: CPU > 70%, memory > 1.6GB, connection errors, latency spikes

set -e

# Configuration defaults (can be overridden by environment variables)
LOADTEST_BASE_URL="${LOADTEST_BASE_URL:-https://preview-api.instainstru.com}"
LOADTEST_USERS="${LOADTEST_USERS:-sarah.chen@example.com,emma.johnson@example.com}"
LOADTEST_PASSWORD="${LOADTEST_PASSWORD:-Test1234}"
LOADTEST_SSE_HOLD_SECONDS="${LOADTEST_SSE_HOLD_SECONDS:-25}"
# Rate limit bypass token - must match RATE_LIMIT_BYPASS_TOKEN on server
LOADTEST_BYPASS_TOKEN="${LOADTEST_BYPASS_TOKEN:-}"

# Scenario parameters
USER_COUNTS="${USER_COUNTS:-50 100 200 300 400}"
SPAWN_RATE=20
DURATION="5m"
COOLDOWN=30
SCENARIO_NAME="s1_capacity"

# Create timestamped output base directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BASE_OUTPUT_DIR="${SCRIPT_DIR}/../results/${SCENARIO_NAME}_${TIMESTAMP}"
mkdir -p "$BASE_OUTPUT_DIR"

echo "=============================================="
echo "  S1: SSE Connection Capacity Sweep"
echo "=============================================="
echo "Target:     $LOADTEST_BASE_URL"
echo "User steps: $USER_COUNTS"
echo "Duration:   $DURATION per step"
echo "Spawn rate: $SPAWN_RATE users/sec"
echo "Cooldown:   ${COOLDOWN}s between steps"
echo "Output:     $BASE_OUTPUT_DIR"
echo "=============================================="
echo ""
echo "IMPORTANT: Monitor Render dashboard during test for:"
echo "  - FastAPI CPU > 70% (warning) / 80% (stop)"
echo "  - FastAPI Memory > 1.6GB (warning) / 1.8GB (stop)"
echo "  - Redis CPU > 65% (warning) / 80% (stop)"
echo ""

# Export environment variables for locust
export LOADTEST_BASE_URL
export LOADTEST_USERS
export LOADTEST_PASSWORD
export LOADTEST_SSE_HOLD_SECONDS
export LOADTEST_BYPASS_TOKEN

cd "$SCRIPT_DIR/.."

# Loop through user counts
for USERS in $USER_COUNTS; do
    OUTPUT_DIR="${BASE_OUTPUT_DIR}/${USERS}_users"
    mkdir -p "$OUTPUT_DIR"

    echo "=============================================="
    echo "  Step: $USERS concurrent users"
    echo "=============================================="
    echo "Starting at: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Output: $OUTPUT_DIR"
    echo ""

    locust -f locustfile.py \
        --headless \
        -u "$USERS" \
        -r "$SPAWN_RATE" \
        -t "$DURATION" \
        --csv="$OUTPUT_DIR/results" \
        --html="$OUTPUT_DIR/report.html"

    echo ""
    echo "Step complete for $USERS users."
    echo ""

    # Check if we should continue (user can Ctrl+C during cooldown)
    if [ "$USERS" != "$(echo $USER_COUNTS | awk '{print $NF}')" ]; then
        echo "Cooling down for ${COOLDOWN}s before next step..."
        echo "(Press Ctrl+C to stop the sweep here)"
        sleep "$COOLDOWN"
        echo ""
    fi
done

echo ""
echo "=============================================="
echo "  S1: Capacity Sweep Complete"
echo "=============================================="
echo "Results saved to: $BASE_OUTPUT_DIR"
echo ""
echo "Subdirectories (one per user count):"
for USERS in $USER_COUNTS; do
    if [ -d "${BASE_OUTPUT_DIR}/${USERS}_users" ]; then
        echo "  - ${USERS}_users/"
    fi
done
echo ""
echo "Next steps:"
echo "  1. Review HTML reports for each user count"
echo "  2. Note the user count where issues first appeared"
echo "  3. That count minus ~20% is your safe operational ceiling"
echo ""
echo "Compare results:"
echo "  open ${BASE_OUTPUT_DIR}/*/report.html"
echo "=============================================="
