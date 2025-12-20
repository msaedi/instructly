#!/bin/bash
# Load test wrapper script - handles setup and execution
#
# Usage:
#   ./run_loadtest.sh -u 50 -r 5 -t 2m
#   ./run_loadtest.sh --users 150 --spawn-rate 10 --run-time 3m
#
# Environment variables (optional):
#   LOADTEST_BASE_URL          - API URL (default: https://preview-api.instainstru.com)
#   LOADTEST_USERS             - Comma-separated emails
#   LOADTEST_PASSWORD          - Password for test users
#   LOADTEST_SSE_HOLD_SECONDS  - SSE connection duration
#   LOADTEST_BYPASS_TOKEN      - Rate limit bypass token
#   SKIP_SETUP                 - Set to "1" to skip conversation discovery

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== InstaInstru Load Test ===${NC}"
echo ""

# Step 1: Setup (discover conversation IDs)
if [ "${SKIP_SETUP}" != "1" ]; then
    echo -e "${YELLOW}Step 1: Discovering conversation IDs...${NC}"
    if ! python setup_conversations.py; then
        echo -e "${RED}Setup failed! Cannot proceed with load test.${NC}"
        exit 1
    fi
    echo ""
else
    echo -e "${YELLOW}Skipping setup (SKIP_SETUP=1)${NC}"
    echo ""
fi

# Step 2: Run locust
echo -e "${YELLOW}Step 2: Running load test...${NC}"
echo ""

# Pass all arguments to locust
exec locust -f locustfile.py "$@"
