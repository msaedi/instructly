#!/bin/bash

# InstaInstru Monitoring Stack Shutdown Script
# This script gracefully stops the monitoring stack

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
    print_status $BLUE "║    Stopping iNSTAiNSTRU Monitoring       ║"
    print_status $BLUE "╚══════════════════════════════════════════╝"
    echo ""
}

# Get running containers
get_running_containers() {
    local grafana_running=$(docker ps --format "table {{.Names}}" | grep -c "instainstru_grafana" || echo "0")
    local prometheus_running=$(docker ps --format "table {{.Names}}" | grep -c "instainstru_prometheus" || echo "0")

    if [ "$grafana_running" -eq "0" ] && [ "$prometheus_running" -eq "0" ]; then
        print_status $YELLOW "ℹ No monitoring containers are running"
        exit 0
    fi

    print_status $BLUE "Currently running:"
    if [ "$grafana_running" -eq "1" ]; then
        print_status $YELLOW "  • Grafana"
    fi
    if [ "$prometheus_running" -eq "1" ]; then
        print_status $YELLOW "  • Prometheus"
    fi
    echo ""
}

# Stop the monitoring stack
stop_stack() {
    print_status $YELLOW "Stopping monitoring stack..."

    docker-compose -f docker-compose.monitoring.yml stop

    if [ $? -eq 0 ]; then
        print_status $GREEN "✓ Monitoring stack stopped gracefully"
    else
        print_status $RED "✗ Error stopping monitoring stack"
        exit 1
    fi
}

# Show what was stopped
show_stopped() {
    echo ""
    print_status $GREEN "════════════════════════════════════════════"
    print_status $GREEN "    Monitoring Stack Stopped"
    print_status $GREEN "════════════════════════════════════════════"
    echo ""

    print_status $BLUE "What was stopped:"
    print_status $YELLOW "  ✓ Grafana (port 3003)"
    print_status $YELLOW "  ✓ Prometheus (port 9090)"
    echo ""

    print_status $BLUE "📁 Data Preservation:"
    print_status $GREEN "  ✓ All dashboards and settings are preserved"
    print_status $GREEN "  ✓ Metrics data is saved in ./monitoring/prometheus-data"
    print_status $GREEN "  ✓ Grafana data is saved in ./monitoring/grafana-data"
    echo ""

    print_status $YELLOW "To restart: ./monitoring/start-monitoring.sh"
    echo ""
}

# Option to remove containers
remove_containers() {
    if [ "$1" == "--remove" ] || [ "$1" == "-r" ]; then
        echo ""
        print_status $YELLOW "Removing monitoring containers..."
        docker-compose -f docker-compose.monitoring.yml down
        print_status $GREEN "✓ Containers removed (data volumes preserved)"
    fi
}

# Option to remove everything including volumes
remove_all() {
    if [ "$1" == "--remove-all" ] || [ "$1" == "-ra" ]; then
        echo ""
        print_status $RED "⚠️  WARNING: This will delete all monitoring data!"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_status $YELLOW "Removing containers and volumes..."
            docker-compose -f docker-compose.monitoring.yml down -v
            rm -rf ./monitoring/grafana-data ./monitoring/prometheus-data
            print_status $GREEN "✓ All monitoring data removed"
        else
            print_status $YELLOW "Cancelled"
        fi
    fi
}

# Main execution
main() {
    print_header
    get_running_containers
    stop_stack
    show_stopped
    remove_containers $1
    remove_all $1
}

# Show help
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --remove, -r      Remove containers after stopping"
    echo "  --remove-all, -ra Remove containers and all data"
    echo "  --help, -h        Show this help message"
    exit 0
fi

# Run main function
main "$1"
