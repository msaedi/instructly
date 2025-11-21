#!/bin/bash

# InstaInstru Automated Slack Routing Configuration
# This script configures notification routing via Grafana API

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

# Load environment variables
if [ ! -f ".env.monitoring" ]; then
    print_status $RED "✗ .env.monitoring file not found!"
    exit 1
fi

source .env.monitoring

# Configuration
GRAFANA_URL="http://localhost:3003"
GRAFANA_USER="${GRAFANA_ADMIN_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}"

# Wait for Grafana to be ready
print_status $YELLOW "Waiting for Grafana to be ready..."
for i in {1..30}; do
    if curl -s "${GRAFANA_URL}/api/health" | grep -q "ok"; then
        print_status $GREEN "✓ Grafana is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        print_status $RED "✗ Grafana is not responding"
        exit 1
    fi
    sleep 2
done

# First, create Slack contact point if it doesn't exist
print_status $YELLOW "Checking for Slack contact point..."

# Check if slack-notifications exists
CONTACT_POINTS=$(curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
    "${GRAFANA_URL}/api/v1/provisioning/contact-points")

if ! echo "$CONTACT_POINTS" | grep -q "slack-notifications"; then
    print_status $YELLOW "Creating Slack contact point..."

    if [ -z "$SLACK_WEBHOOK_URL" ]; then
        print_status $RED "✗ SLACK_WEBHOOK_URL not set in .env.monitoring"
        exit 1
    fi

    SLACK_CONTACT='{
      "name": "slack-notifications",
      "type": "slack",
      "settings": {
        "url": "'${SLACK_WEBHOOK_URL}'",
        "title": "iNSTAiNSTRU Alert",
        "text": "{{ template \"slack.default.text\" . }}"
      },
      "disableResolveMessage": false
    }'

    CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
        -d "${SLACK_CONTACT}" \
        "${GRAFANA_URL}/api/v1/provisioning/contact-points")

    CREATE_CODE=$(echo "$CREATE_RESPONSE" | tail -n 1)

    if [ "$CREATE_CODE" = "202" ]; then
        print_status $GREEN "✓ Slack contact point created"
    else
        print_status $RED "✗ Failed to create Slack contact point"
        echo "$CREATE_RESPONSE"
        exit 1
    fi
else
    print_status $GREEN "✓ Slack contact point already exists"
fi

# Configure notification policy via API
print_status $YELLOW "Configuring notification routing..."

# Simple notification policy that routes everything to slack-notifications
POLICY_CONFIG='{
  "receiver": "slack-notifications",
  "group_wait": "10s",
  "group_interval": "10s",
  "repeat_interval": "1h"
}'

# Update notification policy using the provisioning API
RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT \
    -H "Content-Type: application/json" \
    -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
    -d "${POLICY_CONFIG}" \
    "${GRAFANA_URL}/api/v1/provisioning/policies")

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "202" ] || [ "$HTTP_CODE" = "200" ]; then
    print_status $GREEN "✓ Notification routing configured successfully!"
    print_status $GREEN "  - ALL alerts will now go to Slack"
elif [ "$HTTP_CODE" = "401" ]; then
    print_status $RED "✗ Authentication failed. Check your Grafana credentials in .env.monitoring"
    exit 1
else
    print_status $RED "✗ Failed to configure routing (HTTP $HTTP_CODE)"
    print_status $YELLOW "Response: $BODY"
    exit 1
fi

# Verify configuration
print_status $YELLOW "Verifying configuration..."
sleep 2

VERIFY_RESPONSE=$(curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
    "${GRAFANA_URL}/api/v1/provisioning/policies")

if echo "$VERIFY_RESPONSE" | grep -q "slack-notifications"; then
    print_status $GREEN "✓ Slack routing is active!"
    print_status $GREEN ""
    print_status $GREEN "Slack notifications are now fully automated:"
    print_status $GREEN "  • High Error Rate → Slack"
    print_status $GREEN "  • Service Degradation → Slack"
    print_status $GREEN "  • High Response Time → Slack"
    print_status $GREEN "  • High Load → Slack"
    print_status $GREEN "  • Low Cache Hit Rate → Slack"
else
    print_status $YELLOW "⚠ Could not verify routing configuration"
fi

print_status $YELLOW ""
print_status $YELLOW "To test alerts: ./monitoring/test-alerts.sh"
