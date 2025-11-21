#!/bin/bash

# InstaInstru Slack Notification Test Script
# Tests if Slack webhook is properly configured

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

# Check if .env.monitoring exists
if [ ! -f ".env.monitoring" ]; then
    print_status $RED "✗ .env.monitoring file not found!"
    print_status $YELLOW "Please create it from .env.monitoring.example"
    exit 1
fi

# Source the environment file
source .env.monitoring

# Check if SLACK_WEBHOOK_URL is set
if [ -z "$SLACK_WEBHOOK_URL" ] || [ "$SLACK_WEBHOOK_URL" = "" ]; then
    print_status $YELLOW "⚠ SLACK_WEBHOOK_URL is not set in .env.monitoring"
    print_status $YELLOW "Slack notifications are optional. Alerts will appear in Grafana UI only."
    exit 0
fi

print_status $YELLOW "Testing Slack webhook..."

# Send test message
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H 'Content-type: application/json' \
    --data '{
        "text": "🚀 iNSTAiNSTRU Monitoring Test",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "iNSTAiNSTRU Monitoring Test"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Test successful!* Your Slack integration is working correctly."
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": "*Status:* ✅ Connected"
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Time:* '"$(date)"'"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Alerts will be sent to this channel when triggered in Grafana"
                    }
                ]
            }
        ]
    }' \
    "$SLACK_WEBHOOK_URL")

# Check response
if [ "$RESPONSE" = "200" ]; then
    print_status $GREEN "✓ Slack webhook test successful!"
    print_status $GREEN "Check your Slack channel for the test message."
else
    print_status $RED "✗ Slack webhook test failed (HTTP $RESPONSE)"
    print_status $YELLOW "Please check:"
    print_status $YELLOW "  - Webhook URL is correct"
    print_status $YELLOW "  - No extra spaces in the URL"
    print_status $YELLOW "  - Webhook hasn't been revoked"
fi
