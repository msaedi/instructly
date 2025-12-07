#!/bin/bash
# S3 — Redis Fan-out / Burst Test
# Purpose: Test behavior under sudden message spikes
# Users: 200-300 SSE listeners + aggressive send rate
# Duration: 5 minutes
# Watch: Redis CPU spike, delivery delays, connection drops

set -e

# Configuration defaults (can be overridden by environment variables)
LOADTEST_BASE_URL="${LOADTEST_BASE_URL:-https://preview-api.instainstru.com}"
LOADTEST_USERS="${LOADTEST_USERS:-sarah.chen@example.com,emma.johnson@example.com}"
LOADTEST_PASSWORD="${LOADTEST_PASSWORD:-Test1234}"

# Scenario parameters - aggressive settings for burst testing
USERS="${S3_USERS:-250}"
SPAWN_RATE=25
DURATION="5m"
# Very short SSE hold = high message frequency (burst behavior)
LOADTEST_SSE_HOLD_SECONDS="${LOADTEST_SSE_HOLD_SECONDS:-5}"
SCENARIO_NAME="s3_burst"

# Create timestamped output directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="${SCRIPT_DIR}/../results/${SCENARIO_NAME}_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

echo "=============================================="
echo "  S3: Redis Fan-out / Burst Test"
echo "=============================================="
echo "Target:       $LOADTEST_BASE_URL"
echo "Users:        $USERS (ramp: $SPAWN_RATE/sec)"
echo "Duration:     $DURATION"
echo "SSE hold:     ${LOADTEST_SSE_HOLD_SECONDS}s (aggressive)"
echo "Output:       $OUTPUT_DIR"
echo "=============================================="
echo ""
echo "WARNING: This test creates high Redis Pub/Sub load!"
echo ""
echo "Monitor closely for:"
echo "  - Redis CPU spike > 80%"
echo "  - Redis memory surge"
echo "  - SSE connection drops"
echo "  - Message delivery delays (e2e_full_latency > 1s)"
echo "  - Backend connection pool exhaustion"
echo ""
echo "Starting in 5 seconds... (Ctrl+C to abort)"
sleep 5

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
echo "  S3: Burst Test Complete"
echo "=============================================="
echo "Results saved to: $OUTPUT_DIR"
echo ""
echo "Key metrics to check:"
echo "  - e2e_full_latency: Any > 1s indicates delivery lag"
echo "  - sse_stream errors: Connection drops during burst"
echo "  - send_message errors: Backend overwhelmed"
echo ""
echo "Redis health indicators:"
echo "  - CPU stayed < 80%: Good"
echo "  - Memory stable: Good"
echo "  - No evictions: Good"
echo ""
echo "View report: open $OUTPUT_DIR/report.html"
echo "=============================================="
