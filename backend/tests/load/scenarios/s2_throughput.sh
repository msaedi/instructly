#!/bin/bash
# S2 — Throughput vs Latency Test
# Purpose: Measure e2e_full_latency at different message rates
# Users: 100 (adjust based on S1 results)
# Approach: Vary message rate by adjusting SSE hold time
# Watch: P95 latency growth, CPU correlation

set -e

# Configuration defaults (can be overridden by environment variables)
LOADTEST_BASE_URL="${LOADTEST_BASE_URL:-https://preview-api.instainstru.com}"
LOADTEST_USERS="${LOADTEST_USERS:-sarah.chen@example.com,emma.johnson@example.com}"
LOADTEST_PASSWORD="${LOADTEST_PASSWORD:-Test1234}"

# Scenario parameters
USERS="${S2_USERS:-100}"
SPAWN_RATE=10
DURATION="5m"
COOLDOWN=30
SCENARIO_NAME="s2_throughput"

# SSE hold times to test (lower = more messages/sec)
# 30s = ~2 msgs/min per user, 15s = ~4 msgs/min, 10s = ~6 msgs/min, 5s = ~12 msgs/min
SSE_HOLD_TIMES="${SSE_HOLD_TIMES:-30 20 15 10 5}"

# Create timestamped output base directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BASE_OUTPUT_DIR="${SCRIPT_DIR}/../results/${SCENARIO_NAME}_${TIMESTAMP}"
mkdir -p "$BASE_OUTPUT_DIR"

echo "=============================================="
echo "  S2: Throughput vs Latency Test"
echo "=============================================="
echo "Target:          $LOADTEST_BASE_URL"
echo "Users:           $USERS (steady state)"
echo "Duration:        $DURATION per step"
echo "SSE hold times:  $SSE_HOLD_TIMES seconds"
echo "Output:          $BASE_OUTPUT_DIR"
echo "=============================================="
echo ""
echo "This test varies message rate by adjusting wait time between"
echo "message send cycles. Lower hold time = higher message throughput."
echo ""
echo "Expected message rates (per user, approximate):"
echo "  30s hold -> ~2 messages/min"
echo "  20s hold -> ~3 messages/min"
echo "  15s hold -> ~4 messages/min"
echo "  10s hold -> ~6 messages/min"
echo "   5s hold -> ~12 messages/min"
echo ""

# Export environment variables for locust
export LOADTEST_BASE_URL
export LOADTEST_USERS
export LOADTEST_PASSWORD

cd "$SCRIPT_DIR/.."

# Loop through SSE hold times (message rates)
for HOLD_TIME in $SSE_HOLD_TIMES; do
    OUTPUT_DIR="${BASE_OUTPUT_DIR}/hold_${HOLD_TIME}s"
    mkdir -p "$OUTPUT_DIR"

    # Calculate approximate messages per minute per user
    MSGS_PER_MIN=$(echo "scale=1; 60 / $HOLD_TIME" | bc)

    echo "=============================================="
    echo "  Step: ${HOLD_TIME}s SSE hold (~${MSGS_PER_MIN} msgs/min/user)"
    echo "=============================================="
    echo "Starting at: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Output: $OUTPUT_DIR"
    echo ""

    # Set the SSE hold time for this step
    export LOADTEST_SSE_HOLD_SECONDS="$HOLD_TIME"

    locust -f locustfile.py \
        --headless \
        -u "$USERS" \
        -r "$SPAWN_RATE" \
        -t "$DURATION" \
        --csv="$OUTPUT_DIR/results" \
        --html="$OUTPUT_DIR/report.html"

    echo ""
    echo "Step complete for ${HOLD_TIME}s hold time."
    echo ""

    # Check if we should continue
    if [ "$HOLD_TIME" != "$(echo $SSE_HOLD_TIMES | awk '{print $NF}')" ]; then
        echo "Cooling down for ${COOLDOWN}s before next step..."
        echo "(Press Ctrl+C to stop here)"
        sleep "$COOLDOWN"
        echo ""
    fi
done

echo ""
echo "=============================================="
echo "  S2: Throughput Test Complete"
echo "=============================================="
echo "Results saved to: $BASE_OUTPUT_DIR"
echo ""
echo "Subdirectories (one per message rate):"
for HOLD_TIME in $SSE_HOLD_TIMES; do
    if [ -d "${BASE_OUTPUT_DIR}/hold_${HOLD_TIME}s" ]; then
        MSGS_PER_MIN=$(echo "scale=1; 60 / $HOLD_TIME" | bc)
        echo "  - hold_${HOLD_TIME}s/ (~${MSGS_PER_MIN} msgs/min/user)"
    fi
done
echo ""
echo "Analysis tips:"
echo "  1. Compare e2e_full_latency P95 across runs"
echo "  2. Note the message rate where latency exceeds 500ms"
echo "  3. Graph latency vs message rate to find the knee"
echo ""
echo "Compare results:"
echo "  open ${BASE_OUTPUT_DIR}/*/report.html"
echo "=============================================="
