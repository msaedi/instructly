#!/bin/bash

# InstaInstru Monitoring Stack Restart Script
# This script properly restarts the monitoring stack to load alert configurations

echo "InstaInstru Monitoring Stack Restart"
echo "===================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Stop the monitoring stack
print_status $YELLOW "Stopping monitoring stack..."
docker-compose -f docker-compose.monitoring.yml down

# Remove old Grafana data to ensure clean provisioning
print_status $YELLOW "Cleaning up old Grafana data..."
docker volume rm instructly_monitoring_grafana-data 2>/dev/null || true
rm -rf ./monitoring/grafana-data

# Start the monitoring stack
print_status $YELLOW "Starting monitoring stack..."
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for services to be ready
print_status $YELLOW "Waiting for services to start..."
sleep 10

# Check if services are running
print_status $YELLOW "Checking service status..."

if curl -s -o /dev/null -w "%{http_code}" "http://localhost:9090/-/healthy" | grep -q "200"; then
    print_status $GREEN "✓ Prometheus is running"
else
    print_status $RED "✗ Prometheus is not responding"
fi

if curl -s -o /dev/null -w "%{http_code}" "http://localhost:3003/api/health" | grep -q "200"; then
    print_status $GREEN "✓ Grafana is running"
else
    print_status $YELLOW "⚠ Grafana is still starting up..."
fi

echo ""
print_status $GREEN "Monitoring stack restarted!"
print_status $YELLOW "Access Grafana at: http://localhost:3003"
print_status $YELLOW "Default credentials are in .env.monitoring"

echo ""
print_status $YELLOW "To verify alerts are loaded:"
print_status $YELLOW "1. Log into Grafana"
print_status $YELLOW "2. Navigate to Alerting → Alert rules"
print_status $YELLOW "3. You should see 5 alert rules under 'InstaInstru Production Alerts'"

echo ""
print_status $YELLOW "To view logs:"
print_status $YELLOW "docker-compose -f docker-compose.monitoring.yml logs -f grafana"
