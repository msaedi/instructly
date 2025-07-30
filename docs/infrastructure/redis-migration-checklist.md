# Redis Migration Deployment Checklist

## Pre-Deployment Verification

- [ ] Ensure all changes are committed and pushed
- [ ] Review Celery configuration changes in `app/core/celery_config.py`
- [ ] Verify Redis Docker configuration in `redis/` directory
- [ ] Check `render.yaml` has all services updated with new Redis URL

## Deployment Steps

### 1. Deploy Redis Service First
```bash
# Deploy only the Redis service
render deploy --service instainstru-redis
```

Wait for Redis to be fully running before proceeding.

### 2. Update Environment Variables
Ensure all services have:
- `REDIS_URL=redis://instainstru-redis:6379`
- Remove any `UPSTASH_REDIS_REST_URL` references

### 3. Deploy Services in Order

```bash
# 1. Deploy Celery worker first (highest Redis usage)
render deploy --service instainstru-celery

# 2. Deploy Celery beat
render deploy --service instainstru-celery-beat

# 3. Deploy Flower
render deploy --service instructly-flower

# 4. Finally deploy API
render deploy --service instainstru-backend
```

## Post-Deployment Verification

### 1. Basic Health Check
```bash
# Check Redis connectivity
curl https://api.instainstru.com/api/redis/health
```

Expected response:
```json
{"status": "healthy", "connected": true}
```

### 2. Verify Celery Queues
```bash
# Check queue status (requires admin auth)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.instainstru.com/api/redis/celery-queues
```

### 3. Run Verification Script
```bash
# From local environment
python scripts/verify_redis_migration.py \
  --api-url https://api.instainstru.com \
  --auth-token YOUR_ADMIN_TOKEN \
  --wait 30
```

### 4. Monitor Redis Operations
```bash
# Check Redis stats (requires admin auth)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.instainstru.com/api/redis/stats
```

Look for:
- `estimated_daily_ops` < 100,000 (target is ~50K)
- `connected_clients` matching your service count
- Memory usage within limits

### 5. Check Flower Dashboard
- Navigate to your Flower URL
- Verify all workers are connected
- Check task execution is working

## Monitoring for 24 Hours

After deployment, monitor for the first 24 hours:

1. **Redis Operations**: Should stay under 100K/day
2. **Memory Usage**: Should remain stable
3. **Celery Tasks**: Should execute on schedule
4. **Error Logs**: Check for connection errors

## Rollback Plan

If issues occur:

1. **Revert render.yaml** to use Upstash URLs
2. **Redeploy all services** with old configuration
3. **Investigate logs** for root cause

## Success Criteria

- [ ] All health checks pass
- [ ] Redis operations < 100K/day
- [ ] All scheduled tasks running
- [ ] No connection errors in logs
- [ ] Flower shows all workers active

## Configuration Summary

### What Changed:
1. **Single Redis URL**: All services use `redis://instainstru-redis:6379`
2. **Heartbeat Interval**: Increased from 2s to 30s
3. **Polling Interval**: Increased from 1s to 10s
4. **Result Backend**: Disabled (saves 50% operations)
5. **Task Events**: Kept enabled for monitoring

### Expected Improvements:
- Redis operations: ~450K/day → ~50K/day (89% reduction)
- Cost: Variable → Fixed $7/month
- Latency: Lower (local Redis vs remote Upstash)
- Reliability: No operation limits

## Notes

- The Redis service uses persistence (RDB + AOF) for data safety
- Memory limit is set to 256MB (sufficient for current usage)
- Dangerous commands (FLUSHDB, FLUSHALL) are disabled for safety
- Health checks run every 30 seconds

---

*Remember: Building for MEGAWATTS means getting the infrastructure right!*
