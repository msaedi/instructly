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

# ---------- Helpers ----------

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

# Resolve service name for a given logical type and target env
# Types: backend|redis|worker|beat|flower
get_service_name() {
    local typ=$1
    local env=$2  # preview|prod
    local var_name="RENDER_$(echo "$typ" | tr '[:lower:]' '[:upper:]')_SERVICE_NAME_$(echo "$env" | tr '[:lower:]' '[:upper:]')"
    local val="${!var_name}"
    if [ -n "$val" ]; then echo "$val"; return; fi
    # Defaults if env vars not set
    if [ "$env" = "preview" ]; then
        case "$typ" in
            backend) echo "instainstru-api-preview" ;;
            redis)   echo "redis-preview" ;;
            worker)  echo "celery-worker-preview" ;;
            beat)    echo "celery-beat-preview" ;;
            flower)  echo "flower-preview" ;;
        esac
    else
        case "$typ" in
            backend) echo "instructly" ;;
            redis)   echo "instructly-redis" ;;
            worker)  echo "instructly-celery-worker" ;;
            beat)    echo "instructly-celery-beat" ;;
            flower)  echo "instructly-flower" ;;
        esac
    fi
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

# ---------- Target environment ----------

# Accept first arg as env (preview|prod) for non-interactive usage
TARGET_ENV="${1}"
shift || true
if [ -z "$TARGET_ENV" ]; then
  echo ""
  echo "Select environment:"
  echo "1) preview"
  echo "2) prod"
  echo "0) Exit"
  echo ""
  read -p "Enter your choice (0-2): " env_choice
  case $env_choice in
    1) TARGET_ENV="preview" ;;
    2) TARGET_ENV="prod" ;;
    0) echo "Exiting..."; exit 0 ;;
    *) echo "Invalid environment"; exit 1 ;;
  esac
fi

if [ "$TARGET_ENV" != "preview" ] && [ "$TARGET_ENV" != "prod" ]; then
  echo "❌ Invalid TARGET_ENV: $TARGET_ENV (expected 'preview' or 'prod')"
  exit 1
fi

echo "Deploying to environment: $TARGET_ENV"

# ---------- Menu ----------
echo ""
echo "What would you like to deploy? ($TARGET_ENV)"
echo "1) Backend API"
echo "2) Redis"
echo "3) Celery Worker"
echo "4) Celery Beat"
echo "5) Flower"
echo "6) Celery Stack (Worker + Beat + Flower)"
echo "7) All services (including Backend API)"
echo "8) Full Stack (Redis + All services)"
echo "0) Exit"
echo ""
read -p "Enter your choice (0-8): " choice

case $choice in
    1)
        deploy_service "$(get_service_name backend "$TARGET_ENV")"
        ;;
    2)
        deploy_service "$(get_service_name redis "$TARGET_ENV")"
        ;;
    3)
        deploy_service "$(get_service_name worker "$TARGET_ENV")"
        ;;
    4)
        deploy_service "$(get_service_name beat "$TARGET_ENV")"
        ;;
    5)
        deploy_service "$(get_service_name flower "$TARGET_ENV")"
        ;;
    6)
        echo "Deploying Celery Stack..."
        deploy_service "$(get_service_name worker "$TARGET_ENV")"
        deploy_service "$(get_service_name beat "$TARGET_ENV")"
        deploy_service "$(get_service_name flower "$TARGET_ENV")"
        ;;
    7)
        echo "Deploying all services (except Redis)..."
        deploy_service "$(get_service_name backend "$TARGET_ENV")"
        deploy_service "$(get_service_name worker "$TARGET_ENV")"
        deploy_service "$(get_service_name beat "$TARGET_ENV")"
        deploy_service "$(get_service_name flower "$TARGET_ENV")"
        ;;
    8)
        echo "Deploying full stack (including Redis)..."
        echo "⚠️  Note: Redis should be deployed first and allowed to start before other services"
        deploy_service "$(get_service_name redis "$TARGET_ENV")"
        echo ""
        echo "Waiting 10 seconds for Redis to initialize..."
        sleep 10
        deploy_service "$(get_service_name worker "$TARGET_ENV")"
        deploy_service "$(get_service_name beat "$TARGET_ENV")"
        deploy_service "$(get_service_name flower "$TARGET_ENV")"
        deploy_service "$(get_service_name backend "$TARGET_ENV")"
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
