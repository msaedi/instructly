#!/bin/bash
# Deploy to Render using API
# Requires RENDER_API_KEY environment variable

echo "Render API Deployment Script"
echo "============================"

# Load from .env.render if it exists
if [ -f "$(dirname "$0")/../.env.render" ]; then
    export $(cat "$(dirname "$0")/../.env.render" | xargs)
fi

# Check for API key
if [ -z "$RENDER_API_KEY" ]; then
    echo "❌ Error: RENDER_API_KEY not found"
    echo ""
    echo "Option 1: Create backend/.env.render with:"
    echo "  RENDER_API_KEY=your-key-here"
    echo ""
    echo "Option 2: Set environment variable:"
    echo "  export RENDER_API_KEY=your-key-here"
    echo ""
    echo "Get your API key from: https://dashboard.render.com/account/api-keys"
    exit 1
fi

# Function to get service ID by name
get_service_id() {
    local service_name=$1
    curl -s -H "Authorization: Bearer $RENDER_API_KEY" \
        "https://api.render.com/v1/services?limit=100" | \
        python3 -c "
import sys, json
data = json.load(sys.stdin)
for service in data:
    if service['service']['name'] == '$service_name':
        print(service['service']['id'])
        break
"
}

# Function to trigger deploy
deploy_service() {
    local service_name=$1
    local service_id=$(get_service_id "$service_name")

    if [ -z "$service_id" ]; then
        echo "❌ Service '$service_name' not found"
        return 1
    fi

    echo "🚀 Deploying $service_name (ID: $service_id)..."

    response=$(curl -s -X POST \
        -H "Authorization: Bearer $RENDER_API_KEY" \
        -H "Content-Type: application/json" \
        "https://api.render.com/v1/services/$service_id/deploys" \
        -d '{"clearCache": "do_not_clear"}')

    deploy_id=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))")

    if [ -n "$deploy_id" ]; then
        echo "✅ Deploy started with ID: $deploy_id"
        echo "   View progress: https://dashboard.render.com/web/$service_id/deploys/$deploy_id"
    else
        echo "❌ Deploy failed. Response:"
        echo "$response"
    fi
}

# Menu
echo ""
echo "What would you like to deploy?"
echo "1) Backend API (instructly)"
echo "2) Celery Worker"
echo "3) Celery Beat"
echo "4) Flower"
echo "5) Celery Stack (Worker + Beat + Flower)"
echo "6) All services (including Backend API)"
echo "0) Exit"
echo ""
read -p "Enter your choice (0-6): " choice

case $choice in
    1)
        deploy_service "instructly"
        ;;
    2)
        deploy_service "instructly-celery-worker"
        ;;
    3)
        deploy_service "instructly-celery-beat"
        ;;
    4)
        deploy_service "instructly-flower"
        ;;
    5)
        echo "Deploying Celery Stack..."
        deploy_service "instructly-celery-worker"
        deploy_service "instructly-celery-beat"
        deploy_service "instructly-flower"
        ;;
    6)
        echo "Deploying all services..."
        deploy_service "instructly"
        deploy_service "instructly-celery-worker"
        deploy_service "instructly-celery-beat"
        deploy_service "instructly-flower"
        ;;
    0)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac
