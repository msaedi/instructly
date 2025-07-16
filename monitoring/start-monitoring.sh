#!/bin/bash

# InstaInstru Monitoring Stack Startup Script
# This script starts the monitoring stack with health checks and user-friendly output

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# ASCII art header
print_header() {
    echo ""
    print_status $BLUE "╔══════════════════════════════════════════╗"
    print_status $BLUE "║    InstaInstru Monitoring Stack          ║"
    print_status $BLUE "║    Prometheus + Grafana                  ║"
    print_status $BLUE "╚══════════════════════════════════════════╝"
    echo ""
}

# Check if Docker is running
check_docker() {
    print_status $YELLOW "Checking Docker..."
    if ! docker info > /dev/null 2>&1; then
        print_status $RED "✗ Docker is not running!"
        print_status $RED "Please start Docker Desktop and try again."
        exit 1
    fi
    print_status $GREEN "✓ Docker is running"
}

# Check if .env.monitoring exists
check_env_file() {
    print_status $YELLOW "Checking configuration..."
    if [ ! -f ".env.monitoring" ]; then
        print_status $RED "✗ .env.monitoring file not found!"
        print_status $YELLOW "Creating from example..."
        if [ -f ".env.monitoring.example" ]; then
            cp .env.monitoring.example .env.monitoring
            print_status $GREEN "✓ Created .env.monitoring from example"
            print_status $YELLOW "⚠ Please edit .env.monitoring with your credentials and webhook URLs"
        else
            print_status $RED "✗ .env.monitoring.example not found either!"
            exit 1
        fi
    else
        print_status $GREEN "✓ Configuration file found"
    fi
}

# Start the monitoring stack
start_stack() {
    print_status $YELLOW "Starting monitoring stack..."
    docker-compose -f docker-compose.monitoring.yml up -d

    if [ $? -eq 0 ]; then
        print_status $GREEN "✓ Monitoring stack started"
    else
        print_status $RED "✗ Failed to start monitoring stack"
        exit 1
    fi
}

# Wait for Grafana to be healthy
wait_for_grafana() {
    print_status $YELLOW "Waiting for Grafana to be ready..."

    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s -o /dev/null -w "%{http_code}" "http://localhost:3003/api/health" | grep -q "200"; then
            print_status $GREEN "✓ Grafana is ready!"
            return 0
        fi

        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    echo ""
    print_status $YELLOW "⚠ Grafana is taking longer than expected to start"
    print_status $YELLOW "Check logs with: docker-compose -f docker-compose.monitoring.yml logs grafana"
}

# Print success message
print_success() {
    echo ""
    print_status $GREEN "════════════════════════════════════════════"
    print_status $GREEN "    Monitoring Stack Started Successfully!"
    print_status $GREEN "════════════════════════════════════════════"
    echo ""
    print_status $BLUE "Access Points:"
    print_status $YELLOW "  📊 Grafana:    http://localhost:3003"
    print_status $YELLOW "  📈 Prometheus: http://localhost:9090"
    echo ""
    print_status $BLUE "Credentials:"
    print_status $YELLOW "  Check .env.monitoring for login details"
    echo ""
    print_status $BLUE "What's being monitored:"
    print_status $YELLOW "  • 98 service operations with @measure_operation"
    print_status $YELLOW "  • 5 production alert rules"
    print_status $YELLOW "  • 3 pre-configured dashboards"
    echo ""
}

# Optionally open Grafana in browser
open_browser() {
    if [ "$1" == "--open" ] || [ "$1" == "-o" ]; then
        print_status $YELLOW "Opening Grafana in browser..."

        # Detect OS and open browser
        if [[ "$OSTYPE" == "darwin"* ]]; then
            open "http://localhost:3003"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            xdg-open "http://localhost:3003" 2>/dev/null || print_status $YELLOW "Could not open browser automatically"
        elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
            start "http://localhost:3003"
        fi
    fi
}

# Main execution
main() {
    print_header
    check_docker
    check_env_file
    start_stack
    wait_for_grafana
    print_success
    open_browser $1
}

# Run main function with all arguments
main "$@"
