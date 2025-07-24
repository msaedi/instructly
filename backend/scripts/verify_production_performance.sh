#!/bin/bash

# Production Performance Verification Script
# Run this after deploying to Render to verify improvements

PROD_URL="https://instructly.onrender.com"

echo "=== Catalog Performance Verification ==="
echo

# Test 1: Cold cache (first request after deploy)
echo "1. Testing cold cache performance..."
time1=$(curl -w "%{time_total}" -o /dev/null -s "$PROD_URL/services/catalog")
echo "   Cold cache response time: ${time1}s"

# Test 2: Warm cache (should be much faster)
echo "2. Testing warm cache performance..."
time2=$(curl -w "%{time_total}" -o /dev/null -s "$PROD_URL/services/catalog")
echo "   Warm cache response time: ${time2}s"

# Calculate improvement
improvement=$(echo "scale=1; $time1 / $time2" | bc)
echo "   Cache speedup: ${improvement}x"

# Test 3: New endpoint
echo "3. Testing top-per-category endpoint..."
response=$(curl -s -w "\n%{time_total}" "$PROD_URL/services/catalog/top-per-category")
time3=$(echo "$response" | tail -1)
data=$(echo "$response" | head -n -1)
services=$(echo "$data" | jq '[.categories[].services | length] | add')
echo "   Response time: ${time3}s"
echo "   Total services returned: $services"

# Test 4: Category filter
echo "4. Testing category filter..."
time4=$(curl -w "%{time_total}" -o /dev/null -s "$PROD_URL/services/catalog?category=music")
echo "   Music category response time: ${time4}s"

echo
echo "=== Performance Summary ==="
echo "Previous baseline: ~3.6s"
echo "New performance:"
echo "  - Cold cache: ${time1}s"
echo "  - Warm cache: ${time2}s"
echo "  - Top services: ${time3}s"

# Check if performance improved
if (( $(echo "$time1 < 1.0" | bc -l) )); then
    echo "✅ SUCCESS: Performance significantly improved!"
else
    echo "⚠️  WARNING: Performance may need investigation"
fi
