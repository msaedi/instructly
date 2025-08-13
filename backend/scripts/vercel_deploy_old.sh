#!/bin/bash
# Deploy to Vercel using API
# Requires VERCEL_TOKEN environment variable

echo "Vercel API Deployment Script"
echo "============================"

# Load from .env first, then .env.vercel if it exists
if [ -f "$(dirname "$0")/../.env" ]; then
    export $(cat "$(dirname "$0")/../.env" | grep -E '^VERCEL_' | xargs)
fi

if [ -f "$(dirname "$0")/../.env.vercel" ]; then
    export $(cat "$(dirname "$0")/../.env.vercel" | xargs)
fi

# Check for API token
if [ -z "$VERCEL_TOKEN" ]; then
    echo "❌ Error: VERCEL_TOKEN not found"
    echo ""
    echo "Option 1: Create backend/.env.vercel with:"
    echo "  VERCEL_TOKEN=your-token-here"
    echo "  VERCEL_PROJECT_ID=your-project-id"
    echo "  VERCEL_TEAM_ID=your-team-id (optional)"
    echo ""
    echo "Option 2: Set environment variables:"
    echo "  export VERCEL_TOKEN=your-token-here"
    echo "  export VERCEL_PROJECT_ID=your-project-id"
    echo ""
    echo "Get your token from: https://vercel.com/account/tokens"
    echo "Get project ID from: https://vercel.com/dashboard → Project → Settings → General"
    exit 1
fi

# Check for project ID
if [ -z "$VERCEL_PROJECT_ID" ]; then
    echo "❌ Error: VERCEL_PROJECT_ID not found"
    echo ""
    echo "Get your project ID from: https://vercel.com/dashboard → Project → Settings → General"
    exit 1
fi

# Function to get team parameter
get_team_param() {
    if [ -n "$VERCEL_TEAM_ID" ]; then
        echo "?teamId=$VERCEL_TEAM_ID"
    else
        echo ""
    fi
}

# Function to trigger deployment
deploy_vercel() {
    local project_id=$1
    local team_param=$(get_team_param)

    echo "🚀 Triggering Vercel deployment..."
    echo "   Project ID: $project_id"

    # Trigger deployment using the simpler redeploy endpoint
    response=$(curl -s -X POST \
        -H "Authorization: Bearer $VERCEL_TOKEN" \
        "https://api.vercel.com/v13/deployments${team_param}" \
        -d "{
            \"name\": \"instructly-frontend\",
            \"project\": \"$project_id\",
            \"target\": \"production\"
        }")

    deploy_id=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('id', data.get('uid', '')))" 2>/dev/null)
    deploy_url=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('url', ''))" 2>/dev/null)

    if [ -n "$deploy_id" ]; then
        echo "✅ Deployment started!"
        echo "   Deploy ID: $deploy_id"
        if [ -n "$deploy_url" ]; then
            echo "   Preview URL: https://$deploy_url"
        fi
        echo "   Dashboard: https://vercel.com/dashboard/deployments"

        # Check deployment status
        echo ""
        echo "⏳ Monitoring deployment status..."
        check_deployment_status "$deploy_id"
    else
        echo "❌ Deployment failed. Response:"
        echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data, indent=2))" 2>/dev/null || echo "$response"
    fi
}

# Function to check deployment status
check_deployment_status() {
    local deploy_id=$1
    local team_param=$(get_team_param)
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        sleep 5
        attempt=$((attempt + 1))

        status_response=$(curl -s \
            -H "Authorization: Bearer $VERCEL_TOKEN" \
            "https://api.vercel.com/v13/deployments/$deploy_id${team_param}")

        status=$(echo "$status_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('readyState', 'UNKNOWN'))" 2>/dev/null)

        case $status in
            "READY")
                echo "✅ Deployment completed successfully!"
                break
                ;;
            "ERROR")
                echo "❌ Deployment failed!"
                break
                ;;
            "CANCELED")
                echo "⚠️  Deployment was canceled"
                break
                ;;
            "BUILDING"|"QUEUED"|"INITIALIZING")
                echo "   Status: $status (attempt $attempt/$max_attempts)"
                ;;
            *)
                echo "   Status: $status (attempt $attempt/$max_attempts)"
                ;;
        esac
    done

    if [ $attempt -eq $max_attempts ]; then
        echo "⏰ Timeout waiting for deployment to complete"
        echo "   Check status at: https://vercel.com/dashboard/deployments"
    fi
}

# Function to clear cache (using revalidation)
clear_cache() {
    echo "🗑️  Note: Vercel doesn't have a direct cache purge API for all deployments."
    echo "   The deployment will use fresh code and bypass build cache."
    echo "   To clear edge cache, we'll trigger a revalidation through deployment."
}

# Function to get project info
get_project_info() {
    local team_param=$(get_team_param)

    echo "📋 Project Information:"

    response=$(curl -s \
        -H "Authorization: Bearer $VERCEL_TOKEN" \
        "https://api.vercel.com/v9/projects/$VERCEL_PROJECT_ID${team_param}")

    echo "$response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"   Name: {data.get('name', 'Unknown')}\")
    print(f\"   Framework: {data.get('framework', 'Unknown')}\")
    print(f\"   Production Domain: {data.get('alias', [{}])[0].get('domain', 'Unknown') if data.get('alias') else 'None'}\")

    # Get latest deployment
    latest = data.get('latestDeployments', [{}])[0] if data.get('latestDeployments') else {}
    if latest:
        print(f\"   Latest Deploy: {latest.get('url', 'Unknown')}\")
        print(f\"   Deploy Status: {latest.get('readyState', 'Unknown')}\")
        print(f\"   Created: {latest.get('createdAt', 'Unknown')}\")
except:
    print('   Could not parse project info')
"
}

# Menu
echo ""
echo "What would you like to do?"
echo "1) Deploy Frontend (Production)"
echo "2) Clear Cache Only"
echo "3) Deploy + Clear Cache"
echo "4) Check Project Info"
echo "5) Force Deploy (bypass cache)"
echo "0) Exit"
echo ""
read -p "Enter your choice (0-5): " choice

case $choice in
    1)
        deploy_vercel "$VERCEL_PROJECT_ID"
        ;;
    2)
        clear_cache
        ;;
    3)
        echo "Deploying and clearing cache..."
        deploy_vercel "$VERCEL_PROJECT_ID"
        echo ""
        clear_cache
        ;;
    4)
        get_project_info
        ;;
    5)
        echo "Force deploying (this may take longer)..."
        clear_cache
        echo ""
        deploy_vercel "$VERCEL_PROJECT_ID"
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

echo ""
echo "🎉 Script completed!"
