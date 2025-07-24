# Redis Setup Guide for Render

## Quick Setup (5 minutes)

### 1. Create Upstash Redis Account
1. Go to https://upstash.com
2. Sign up (free tier is sufficient)
3. Click "Create Database"
4. Settings:
   - Name: `instainstru-cache`
   - Region: `us-east-1` (same as Render)
   - Type: `Regional`
   - Enable: `TLS/SSL` ✓
   - Enable: `Eviction` ✓

### 2. Get Redis URL
1. In Upstash dashboard, click your database
2. Under "REST API" section, find "REDIS_URL"
3. Copy the URL (format: `rediss://default:PASSWORD@ENDPOINT.upstash.io:6379`)

### 3. Add to Render
1. Go to Render dashboard
2. Click your web service
3. Go to "Environment" tab
4. Click "Add Environment Variable"
5. Add:
   ```
   Key: REDIS_URL
   Value: rediss://default:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379
   ```
6. Click "Save Changes"
7. Render will automatically redeploy

### 4. Verify It's Working

After deployment completes (2-3 minutes):

```bash
# Test catalog endpoint performance
curl -w "\nTime: %{time_total}s\n" https://instainstru.onrender.com/api/services/catalog

# First request: ~1.5s (cache miss)
# Second request: <0.1s (cache hit) 🚀
```

## What This Fixes

1. **Catalog Endpoint**: 1.5s → 100ms (15x faster)
2. **Cache Hit Rate**: 0% → 80%+
3. **Reduced Database Load**: Fewer queries to Supabase
4. **Better User Experience**: Instant responses

## Cache Configuration

The app is already configured to cache:
- Service catalog (5 minutes)
- Categories (10 minutes)
- Instructor profiles (5 minutes)
- Search results (2 minutes)

## Monitoring Cache Performance

Check cache stats at:
```
GET https://instainstru.onrender.com/monitoring/performance
X-API-Key: your-monitoring-api-key
```

Look for:
```json
{
  "cache": {
    "type": "UpstashCache",
    "hits": 1234,
    "misses": 56,
    "hit_rate": "95.7%"
  }
}
```

## Troubleshooting

If cache isn't working:
1. Check Render logs for "REDIS_URL not configured"
2. Verify Upstash shows commands in dashboard
3. Run `python scripts/verify_cache_configuration.py`

## Cost

- Upstash Free Tier: 10,000 commands/day
- InstaInstru usage: ~5,000 commands/day
- Cost: $0 (free tier sufficient)

## Next Steps After Redis

1. Monitor performance improvement
2. Adjust cache TTLs if needed
3. Add more cache points as traffic grows
