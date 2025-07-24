# Production Setup Guide - Fixing Cache and Monitoring Issues

This guide addresses the two critical production issues:
1. Cache not being used (catalog endpoint taking 1.5s every time)
2. Monitoring alerts only going to logs instead of triggering notifications

## Issue 1: Cache Not Being Used

### Root Cause
The REDIS_URL environment variable is not set in Render, causing the application to fall back to in-memory cache. In-memory cache doesn't persist between requests in production.

### Solution: Set Up Upstash Redis

1. **Sign up for Upstash** (if you haven't already):
   - Go to https://upstash.com
   - Create a free account (free tier includes 10,000 commands/day)

2. **Create a Redis Database**:
   - Click "Create Database"
   - Choose a region close to your Render deployment (e.g., US-East-1)
   - Select "Regional" (not Global)
   - Enable "TLS/SSL" and "Eviction"
   - Click "Create"

3. **Get the Redis URL**:
   - In your Upstash dashboard, click on your database
   - Look for "REST API" section
   - Copy the "REDIS_URL" (it should look like: `rediss://default:YOUR_PASSWORD@YOUR_ENDPOINT.upstash.io:6379`)

4. **Add to Render**:
   - Go to your Render dashboard
   - Click on your web service
   - Go to "Environment" tab
   - Click "Add Environment Variable"
   - Add:
     - Key: `REDIS_URL`
     - Value: The URL you copied from Upstash
   - Click "Save Changes"
   - Render will automatically redeploy

5. **Verify Cache is Working**:
   ```bash
   # SSH into your Render instance or run locally with production env
   cd backend
   python scripts/verify_cache_configuration.py
   ```

   You should see:
   ```
   Cache Type: UpstashCacheAdapter
   ✅ Cache SET operation successful
   ✅ Cache GET operation successful
   ```

6. **Test the Catalog Endpoint**:
   - First request: ~1.5s (cache miss, loads from DB)
   - Subsequent requests: <50ms (cache hit)
   - Cache TTL is set to 5 minutes for catalog data

## Issue 2: Monitoring Alerts Not Triggering

### Root Cause
Monitoring alerts were only logging to console instead of dispatching to Celery tasks.

### Solution: Already Implemented

The code has been updated to:
1. Create AlertHistory model to track sent alerts
2. Implement Celery tasks for processing alerts
3. Update production monitor to dispatch alerts to Celery

### Steps to Activate

1. **Run the Migration**:
   ```bash
   cd backend
   alembic upgrade head
   ```
   This creates the `alert_history` table.

2. **Configure Email Settings** (for alert notifications):
   Add these environment variables in Render:
   ```
   SMTP_HOST=smtp.gmail.com  # or your SMTP server
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   FROM_EMAIL=alerts@instainstru.com
   ALERT_EMAIL_RECIPIENTS=admin@instainstru.com,dev@instainstru.com
   ```

3. **Configure GitHub Integration** (optional, for issue creation):
   ```
   GITHUB_TOKEN=your-github-personal-access-token
   GITHUB_REPO=your-username/your-repo
   ```

4. **Restart Celery Workers**:
   Ensure your Celery workers are running with the new tasks:
   ```bash
   celery -A app.tasks worker --loglevel=info
   ```

### Alert Types and Behavior

The monitoring system now handles these alerts:

| Alert Type | Severity | Email? | GitHub Issue? | Trigger |
|------------|----------|---------|---------------|---------|
| extremely_slow_query | critical | Yes | After 3 occurrences | Query >1s |
| extremely_slow_request | critical | Yes | After 3 occurrences | Request >5s |
| high_db_pool_usage | warning | No | No | Pool >80% |
| high_memory_usage | warning | No | No | Memory >80% |
| low_cache_hit_rate | warning | No | No | Hit rate <70% |

Alerts have a 15-minute cooldown to prevent spam.

## Verification Steps

### 1. Check Cache Performance
```bash
# Watch the monitoring endpoint
curl -H "X-API-Key: your-monitoring-api-key" https://your-app.onrender.com/monitoring/performance

# Look for:
# - cache.hit_rate > 0%
# - cache.hits increasing
# - catalog endpoint response time < 100ms (after first request)
```

### 2. Test Alert System
```bash
# Trigger a test alert by making a slow request
# Or wait for natural slow queries

# Check alert history
curl -H "X-API-Key: your-monitoring-api-key" https://your-app.onrender.com/monitoring/alerts/history

# Check Celery logs for:
# - "Alert dispatched to Celery: extremely_slow_query"
# - "Sending alert email..."
# - "Alert saved to database"
```

### 3. Monitor Catalog Endpoint
```bash
# First request (cache miss)
time curl https://your-app.onrender.com/api/services/catalog

# Subsequent requests (cache hit)
time curl https://your-app.onrender.com/api/services/catalog
```

## Troubleshooting

### Cache Still Not Working?
1. Check logs for "REDIS_URL not configured for production!"
2. Verify Upstash connection in their dashboard (see "Commands" counter)
3. Run `verify_cache_configuration.py` script
4. Check for Redis connection errors in logs

### Alerts Not Being Sent?
1. Check Celery workers are running
2. Verify email configuration with test email
3. Check `alert_history` table for records
4. Look for "CELERY_AVAILABLE = False" in logs

### Performance Issues?
1. Check `/monitoring/performance` endpoint
2. Look for slow queries in logs
3. Verify database indexes are created
4. Check connection pool usage

## Production Checklist

- [ ] REDIS_URL set in Render environment
- [ ] Migration run to create alert_history table
- [ ] Email configuration added (if using email alerts)
- [ ] Celery workers restarted
- [ ] Monitoring API key set
- [ ] Verified cache is working (hit rate > 0%)
- [ ] Verified alerts are being dispatched to Celery
- [ ] Catalog endpoint responds in <100ms (after cache warm)

## Key Endpoints

- **Health Check**: `GET /health`
- **Performance Metrics**: `GET /monitoring/performance` (requires API key)
- **Alert History**: `GET /monitoring/alerts/history` (requires API key)
- **Catalog (cached)**: `GET /api/services/catalog`

## Environment Variables Summary

Required for fixes:
```
# Cache (CRITICAL - fixes issue #1)
REDIS_URL=rediss://default:PASSWORD@ENDPOINT.upstash.io:6379

# Monitoring
MONITORING_API_KEY=your-secure-api-key-here

# Email Alerts (optional but recommended)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=alerts@instainstru.com
ALERT_EMAIL_RECIPIENTS=admin@instainstru.com

# GitHub Integration (optional)
GITHUB_TOKEN=your-token
GITHUB_REPO=username/repo
```

## Next Steps

1. **Immediate**: Set REDIS_URL in Render to fix cache issue
2. **Today**: Run migration and restart services
3. **This Week**: Configure email alerts
4. **Monitor**: Watch performance metrics for improvements

The catalog endpoint should go from 1.5s → <100ms after cache is enabled!
