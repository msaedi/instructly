# Rate Limiter Runbook

## Quick toggles
- Global kill switch: `RATE_LIMIT_ENABLED=false`
- Global shadow (observe-only): `RATE_LIMIT_SHADOW=true`
- Per-bucket shadow:
  - Financial: `RATE_LIMIT_SHADOW_FINANCIAL=true`
  - Write: `RATE_LIMIT_SHADOW_WRITE=true`
  - Read: `RATE_LIMIT_SHADOW_READ=true`
  - Auth: `RATE_LIMIT_SHADOW_AUTH=true`

## Raising limits
- Update `backend/app/ratelimit/config.py` BUCKETS and redeploy.
- Prefer raising burst first to smooth spikes.
 - For hotfix without redeploy, use Redis overrides key `{namespace}:rl:overrides` and POST `/internal/config/reload`.

## Clearing locks
- Redis key format: `{namespace}:lock:{user_id}:{route}`
- Use `DEL` to clear a stuck lock (beware of races).
 - Example: `DEL instainstru:lock:user_01ABCDEF:/api/payments/checkout`

## Idempotency troubleshooting
- Key format: `{namespace}:idem:{sha256(raw)}` where raw includes method/route/user/body hash.
- Cached payload stored for 24h. Use `GET` to inspect, `DEL` to clear.
 - Example inspect: `GET instainstru:idem:01ABCDEF...`
 - Example clear: `DEL instainstru:idem:01ABCDEF...`

## Observability
- Metrics:
  - `instainstru_rl_decisions_total{bucket,action,shadow}`
  - `instainstru_rl_retry_after_seconds_bucket`
  - `instainstru_rl_eval_errors_total{bucket}`
  - `instainstru_rl_eval_duration_seconds_bucket{bucket}`
  - `instainstru_rl_config_reload_total`
  - `instainstru_rl_active_overrides`
- Dashboards: `ops/grafana/ratelimit-dashboard.json`
- Alerts: `ops/alerts/ratelimit.yml`

## CI Smoke
- Test `backend/tests/integration/test_rate_headers_smoke.py` asserts headers present on health/read/write.
 - E2E: search page shows friendly 429 copy with or without Retry-After.

## Login flow window (future)
- Optionally set a 10s relaxed policy after successful login.
