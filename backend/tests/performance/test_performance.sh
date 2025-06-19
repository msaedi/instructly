# Complete performance test script
#!/bin/bash

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcm9maWxpbmdAaW5zdGFpbnN0cnUuY29tIiwiZXhwIjoxNzUwMzA3Mjc0fQ.Kxs4vT2uZTEXi5iR2qmx56zSJlSh9aJQiWvGZZFvEsw"

echo "🧹 Clearing cache..."
redis-cli FLUSHALL > /dev/null

echo "🔄 Warming up API..."
curl -s "http://localhost:8000/health" -o /dev/null

echo "📊 Resetting cache stats..."
curl -X POST "http://localhost:8000/metrics/cache/reset-stats" \
  -H "Authorization: Bearer $TOKEN" -s -o /dev/null

echo -e "\n⚡ Performance Test Results:\n"

echo "1️⃣ First request (cache MISS):"
time curl -s "http://localhost:8000/instructors/availability-windows/week?start_date=2025-06-16" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept-Encoding: gzip" \
  -o /dev/null -w "   Response time: %{time_total}s\n   Compressed size: %{size_download} bytes\n   HTTP status: %{http_code}\n"

echo -e "\n2️⃣ Cache HIT performance (10 requests):"
total_time=0
for i in {1..10}; do
  response_time=$(curl -s "http://localhost:8000/instructors/availability-windows/week?start_date=2025-06-16" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept-Encoding: gzip" \
    -o /dev/null -w "%{time_total}")
  echo "   Request $i: ${response_time}s"
  total_time=$(echo "$total_time + $response_time" | bc)
done

avg_time=$(echo "scale=3; $total_time / 10" | bc)
echo "   Average: ${avg_time}s"

echo -e "\n3️⃣ Cache Statistics:"
curl -s "http://localhost:8000/metrics/cache" \
  -H "Authorization: Bearer $TOKEN" | jq '.cache | {hit_rate, total_requests, hits, misses, circuit_breaker}'

echo -e "\n4️⃣ Database Pool Status:"
curl -s "http://localhost:8000/metrics/performance" \
  -H "Authorization: Bearer $TOKEN" | jq '.database.pool_status'
