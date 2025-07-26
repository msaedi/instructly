# Save as check-monitoring.sh
#!/bin/bash
API_KEY="JVLJzfK6kkVNZGTNoyjdkcwVSBxV5TZr"
BASE_URL="https://api.instainstru.com"

echo "🔍 Checking InstaInstru Monitoring..."
curl -s -H "X-Monitoring-API-Key: $API_KEY" \
     "$BASE_URL/api/monitoring/dashboard" | python -m json.tool
