# Rate Limiter Rollout Checklist

This document outlines the safe rollout and rollback steps for rate limiting across buckets.

## Preconditions
- Dashboards and alerts imported (see `ops/grafana/ratelimit-dashboard.json`, `ops/alerts/ratelimit.yml`).
- CI smoke passes (headers present on health/read/write).
- Frontend 429 handling is deployed (backoff + dedupe; financial no auto-retry).

## Global toggles
- Global enable/disable: `RATE_LIMIT_ENABLED` (default true)
- Global shadow (observe-only):
  - Defaults to true in non-prod and false in prod unless explicitly set via `RATE_LIMIT_SHADOW`.
- Per-bucket shadow:
  - `RATE_LIMIT_SHADOW_AUTH`, `RATE_LIMIT_SHADOW_READ`, `RATE_LIMIT_SHADOW_WRITE`, `RATE_LIMIT_SHADOW_FINANCIAL`

## Runtime Overrides (no redeploy)
- POST `/internal/config/reload` with header `X-Config-Reload-Signature` HMAC (sha256 over empty body) using `CONFIG_RELOAD_SECRET`.
- Example (local):
  - Compute signature: `SIG=$(python - <<'PY'\nimport hmac,hashlib,os\nprint(hmac.new(os.environ.get('CONFIG_RELOAD_SECRET','').encode(), b'', hashlib.sha256).hexdigest())\nPY\n)`
  - Reload: `curl -s -X POST http://localhost:8000/internal/config/reload -H "X-Config-Reload-Signature: $SIG" | jq`
- Env overrides:
  - `RATE_LIMIT_POLICY_OVERRIDES_JSON` (JSON map routePrefix → {rate, burst, window, shadow})
- Redis overrides (preferred):
  - Key: `{namespace}:rl:overrides` (JSON map routePrefix → {rate, burst, window, shadow})
- Example JSON:
  ```json
  {
    "/api/search": { "rate": 120, "burst": 30, "shadow": true },
    "/api/payments/checkout": { "rate": 3, "burst": 0, "shadow": false }
  }
  ```
  - Set override (redis-cli): `SET instainstru:rl:overrides '{"/api/search": {"rate": 120, "burst": 30, "shadow": true}}'`
  - Then call reload endpoint.
- Check effective policy:
  - GET `/internal/rate-limit/policy?route=/api/search/instructors&method=GET&bucket=read`
  - Example: `curl -s 'http://localhost:8000/internal/rate-limit/policy?route=/api/search/instructors&method=GET&bucket=read' | jq`

## Rollout Steps
1) Shadow-only verification (all buckets shadow)
   - Set `RATE_LIMIT_SHADOW=true` (or per-bucket) and reload.
   - Verify in dashboards:
     - `instainstru_rl_decisions_total{action="shadow_block"}` rises only in abusive scenarios.
     - Retry-After p95 is low (< 1s) except load tests.
2) Enable financial enforcement
   - Ensure `RATE_LIMIT_SHADOW_FINANCIAL=false`.
   - Monitor alerts: any financial 429 for verified users triggers immediate page.
3) Enable write enforcement
   - Ensure `RATE_LIMIT_SHADOW_WRITE=false` (generous limits kept).
   - Monitor block % and Retry-After p95.
4) (Optional) Tune read/auth in shadow
   - Keep read/auth shadowed initially; monitor impact before considering enforcement.

## Emergency Rollback
- Global: `RATE_LIMIT_ENABLED=false` and reload.
- Per-bucket: set `RATE_LIMIT_SHADOW_<BUCKET>=true` and reload.
- Per-route: add override with `shadow:true` for the route prefix and reload.
- Verify rollback:
  - Metrics: blocks drop to zero, only `shadow_block` counts increase.
  - Headers: `X-RateLimit-Shadow: true` present.

## Expected Impact
- Shadow-only: headers + metrics only; no user impact.
- Financial enforcement: protects against duplicate payments and concurrency; UI shows friendly 429 for in-flight duplicates.
- Write enforcement: throttles abusive POST/PATCH/DELETE; UI backoff/dedupe smooths reads; no retry for financial writes.

## Validation
- Dashboards: blocks/limited % under SLO thresholds; Retry-After p95 stable.
- CI smoke test: headers present on health/read/write.
- Policy introspection returns merged effective policy as changed.
 - Prometheus counters:
   - `instainstru_rl_config_reload_total` increments after each reload
   - `instainstru_rl_active_overrides` reflects current overrides count
