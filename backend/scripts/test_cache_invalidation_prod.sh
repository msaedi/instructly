#!/bin/bash

# Test Cache Invalidation in Production
# This simulates what happens when analytics run

PROD_URL="https://instructly.onrender.com"

echo "=== Testing Cache Invalidation ==="
echo

# 1. Warm up the cache
echo "1. Warming up cache..."
curl -s "$PROD_URL/services/catalog" > /dev/null
echo "   ✓ Cache warmed"

# 2. Check it's cached (should be fast)
time1=$(curl -w "%{time_total}" -o /dev/null -s "$PROD_URL/services/catalog")
echo "2. Cached response time: ${time1}s"

# 3. Trigger analytics calculation (if you have an admin endpoint)
# Or wait for scheduled analytics at 2 AM EST
echo "3. Analytics will run at 2 AM EST daily via GitHub Actions"
echo "   This will invalidate the cache automatically"

# 4. Monitor after analytics run
echo "4. After analytics run, the next request will rebuild cache"
echo "   Then subsequent requests will be fast again"
