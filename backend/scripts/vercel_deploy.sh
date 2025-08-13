#!/bin/bash
# Simple Vercel deployment script using Vercel CLI
# This is more reliable than using the API directly

echo "Vercel CLI Deployment Script"
echo "============================"

# Check if vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "❌ Vercel CLI not found. Installing..."
    npm i -g vercel
fi

# Change to frontend directory
cd "$(dirname "$0")/../../frontend" || {
    echo "❌ Could not find frontend directory"
    exit 1
}

echo "📂 Working directory: $(pwd)"
echo ""

# Menu
echo "What would you like to do?"
echo "1) Deploy to Production"
echo "2) Deploy to Production (Force - bypass cache)"
echo "3) List Recent Deployments"
echo "4) Check Project Info"
echo "0) Exit"
echo ""
read -p "Enter your choice (0-4): " choice

case $choice in
    1)
        echo "🚀 Deploying to production..."
        npx vercel --prod
        ;;
    2)
        echo "🚀 Force deploying to production (bypassing cache)..."
        npx vercel --prod --force
        ;;
    3)
        echo "📋 Recent deployments:"
        npx vercel list
        ;;
    4)
        echo "📋 Project info:"
        npx vercel inspect
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
echo "🎉 Done!"
