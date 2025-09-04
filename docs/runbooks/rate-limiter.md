# Rate Limiter Runbook

## Quick toggles
- Global kill switch: `RATE_LIMIT_ENABLED=false`
- Global shadow (observe-only): `RATE_LIMIT_SHADOW=true`
- Per-bucket shadow:
  - Financial: `RATE_LIMIT_SHADOW_FINANCIAL=true`
  - Write: `RATE_LIMIT_SHADOW_WRITE=true`

## Raising limits
- Update `backend/app/ratelimit/config.py` BUCKETS and redeploy.
- Prefer raising burst first to smooth spikes.

## Clearing locks
- Redis key format: `{namespace}:lock:{user_id}:{route}`
- Use `DEL` to clear a stuck lock (beware of races).

## Idempotency troubleshooting
- Key format: `{namespace}:idem:{sha256(raw)}` where raw includes method/route/user/body hash.
- Cached payload stored for 24h. Use `GET` to inspect, `DEL` to clear.

## Observability
- Metrics:
  - `instainstru_rl_decisions_total{bucket,action,shadow}`
  - `instainstru_rl_retry_after_seconds_bucket`
- Dashboards: `ops/grafana/ratelimit-dashboard.json`
- Alerts: `ops/alerts/ratelimit.yml`

## CI Smoke
- Test `backend/tests/integration/test_rate_headers_smoke.py` asserts headers present on health/read/write.

## Login flow window (future)
- Optionally set a 10s relaxed policy after successful login.
