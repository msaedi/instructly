#!/bin/bash

# InstaInstru Alert Testing Script
# This script simulates various conditions to trigger alerts

echo "InstaInstru Alert Testing Script"
echo "================================"
echo ""

# Configuration
BACKEND_URL="http://localhost:8000"
DURATION=300  # 5 minutes
PARALLEL_REQUESTS=50

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Check if backend is running
check_backend() {
    print_status $YELLOW "Checking backend availability..."
    if curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" | grep -q "200"; then
        print_status $GREEN "✓ Backend is running"
        return 0
    else
        print_status $RED "✗ Backend is not running at $BACKEND_URL"
        exit 1
    fi
}

# Test 1: High Response Time (P95 > 500ms)
test_high_latency() {
    print_status $YELLOW "\n[Test 1] Simulating high latency requests..."
    print_status $YELLOW "This will trigger: High Response Time (P95 > 500ms)"

    for i in {1..100}; do
        # Add artificial delay using a slow endpoint
        curl -s "$BACKEND_URL/api/public/instructors?delay=800" &
        if [ $((i % 10)) -eq 0 ]; then
            echo -n "."
        fi
    done
    wait
    print_status $GREEN "\n✓ High latency test completed"
}

# Test 2: High Error Rate (> 1%)
test_high_error_rate() {
    print_status $YELLOW "\n[Test 2] Simulating high error rate..."
    print_status $YELLOW "This will trigger: High Error Rate (> 1%)"

    for i in {1..200}; do
        # 5% of requests will be errors
        if [ $((i % 20)) -eq 0 ]; then
            # Invalid request to trigger 400 error
            curl -s -X POST "$BACKEND_URL/api/auth/login" \
                -H "Content-Type: application/json" \
                -d '{"invalid": "data"}' &
        else
            # Normal request
            curl -s "$BACKEND_URL/api/public/instructors" &
        fi

        if [ $((i % 20)) -eq 0 ]; then
            echo -n "."
        fi
    done
    wait
    print_status $GREEN "\n✓ High error rate test completed"
}

# Test 3: Service Degradation (P99 > 1s)
test_service_degradation() {
    print_status $YELLOW "\n[Test 3] Simulating service degradation..."
    print_status $YELLOW "This will trigger: Service Degradation (P99 > 1s)"

    for i in {1..50}; do
        # 2% of requests will be very slow
        if [ $((i % 50)) -eq 0 ]; then
            curl -s "$BACKEND_URL/api/public/instructors?delay=2000" &
        else
            curl -s "$BACKEND_URL/api/public/instructors?delay=100" &
        fi

        if [ $((i % 10)) -eq 0 ]; then
            echo -n "."
        fi
    done
    wait
    print_status $GREEN "\n✓ Service degradation test completed"
}

# Test 4: High Load (> 1000 req/s)
test_high_load() {
    print_status $YELLOW "\n[Test 4] Simulating high load..."
    print_status $YELLOW "This will trigger: High Request Load (> 1000 req/s)"
    print_status $YELLOW "Running high load test for 10 minutes..."

    # Use Apache Bench if available, otherwise use curl in parallel
    if command -v ab &> /dev/null; then
        ab -n 100000 -c 100 -t 600 "$BACKEND_URL/api/public/instructors" > /dev/null 2>&1 &
        AB_PID=$!

        # Show progress
        for i in {1..60}; do
            sleep 10
            echo -n "."
        done

        kill $AB_PID 2>/dev/null
    else
        print_status $YELLOW "Apache Bench not found, using curl instead..."
        END=$((SECONDS+600))
        while [ $SECONDS -lt $END ]; do
            for j in {1..50}; do
                curl -s "$BACKEND_URL/api/public/instructors" &
            done
            echo -n "."
            sleep 0.5
        done
    fi
    wait
    print_status $GREEN "\n✓ High load test completed"
}

# Test 5: Low Cache Hit Rate
test_low_cache_hit() {
    print_status $YELLOW "\n[Test 5] Simulating low cache hit rate..."
    print_status $YELLOW "This will trigger: Low Cache Hit Rate (< 60%)"

    # Generate requests with unique parameters to bypass cache
    for i in {1..100}; do
        RANDOM_ID=$((RANDOM % 10000))
        curl -s "$BACKEND_URL/api/public/instructors/$RANDOM_ID/availability" &

        if [ $((i % 10)) -eq 0 ]; then
            echo -n "."
        fi
    done
    wait
    print_status $GREEN "\n✓ Low cache hit rate test completed"
}

# Main execution
main() {
    print_status $GREEN "Starting InstaInstru Alert Testing"
    print_status $YELLOW "This will take approximately 15-20 minutes to complete"
    print_status $YELLOW "Alerts should start firing within 3-10 minutes depending on the test\n"

    check_backend

    # Run tests
    test_high_latency
    sleep 10

    test_high_error_rate
    sleep 10

    test_service_degradation
    sleep 10

    test_high_load
    sleep 10

    test_low_cache_hit

    print_status $GREEN "\n\nAll tests completed!"
    print_status $YELLOW "Check your alert channels (Slack, Email, PagerDuty) for notifications"
    print_status $YELLOW "View alert status in Grafana: http://localhost:3003"
}

# Handle Ctrl+C
trap 'print_status $RED "\nTest interrupted"; exit 1' INT

# Run main function
main
