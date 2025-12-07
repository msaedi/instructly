#!/bin/bash
# S4 — Soak / Long-Running Stability Test
# Purpose: Detect memory leaks, connection leaks, stability over time
# Users: 100-200 (steady-state load)
# Duration: 1-4 hours (configurable)
# Watch: Memory growth trend, reconnection rate, latency drift

set -e

# Configuration defaults (can be overridden by environment variables)
LOADTEST_BASE_URL="${LOADTEST_BASE_URL:-https://preview-api.instainstru.com}"
LOADTEST_USERS="${LOADTEST_USERS:-sarah.chen@example.com,emma.johnson@example.com}"
LOADTEST_PASSWORD="${LOADTEST_PASSWORD:-Test1234}"
LOADTEST_SSE_HOLD_SECONDS="${LOADTEST_SSE_HOLD_SECONDS:-25}"

# Scenario parameters - moderate sustained load
USERS="${S4_USERS:-150}"
SPAWN_RATE=5
DURATION="${S4_DURATION:-1h}"
SCENARIO_NAME="s4_soak"

# Create timestamped output directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="${SCRIPT_DIR}/../results/${SCENARIO_NAME}_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

echo "=============================================="
echo "  S4: Soak / Long-Running Stability Test"
echo "=============================================="
echo "Target:     $LOADTEST_BASE_URL"
echo "Users:      $USERS (ramp: $SPAWN_RATE/sec)"
echo "Duration:   $DURATION"
echo "SSE hold:   ${LOADTEST_SSE_HOLD_SECONDS}s"
echo "Output:     $OUTPUT_DIR"
echo "=============================================="
echo ""
echo "This is a LONG-RUNNING test designed to detect:"
echo "  - Memory leaks (gradual increase over time)"
echo "  - Connection leaks (SSE reconnection failures)"
echo "  - Latency drift (P95 increasing over time)"
echo "  - Resource exhaustion (file descriptors, etc.)"
echo ""
echo "Recommended monitoring during test:"
echo "  1. Keep Render dashboard open"
echo "  2. Note memory usage at start, 30min, 1hr, etc."
echo "  3. Watch for increasing error rates over time"
echo ""
echo "To customize duration, set S4_DURATION:"
echo "  S4_DURATION=4h ./s4_soak.sh"
echo ""
echo "Starting in 10 seconds... (Ctrl+C to abort)"
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
sleep 10

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

END_TIME=$(date '+%Y-%m-%d %H:%M:%S')

echo ""
echo "=============================================="
echo "  S4: Soak Test Complete"
echo "=============================================="
echo "End time: $END_TIME"
echo "Results saved to: $OUTPUT_DIR"
echo ""
echo "Stability indicators to analyze:"
echo ""
echo "  Memory leak detection:"
echo "    - Compare Render memory at start vs end"
echo "    - Flat trend = healthy"
echo "    - Upward trend = potential leak"
echo ""
echo "  Latency stability:"
echo "    - Review results_stats_history.csv"
echo "    - P95 should remain stable over duration"
echo "    - Increasing P95 = degradation"
echo ""
echo "  Connection health:"
echo "    - sse_stream error rate over time"
echo "    - Should remain near 0%"
echo ""
echo "View report: open $OUTPUT_DIR/report.html"
echo ""
echo "For time-series analysis, check:"
echo "  $OUTPUT_DIR/results_stats_history.csv"
echo "=============================================="
