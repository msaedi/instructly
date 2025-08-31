# Flip PHASE=beta → open (Prod API)

Prechecks
- Liquidity metrics met; smoke tests green on beta.
- Comms ready; emails updated to app.* URLs.

Steps
1) Set PHASE=open on prod API; deploy.
2) Smoke:
   - /health shows X-Phase: open
   - Gated endpoint now 200 for public users
   - Webhooks/auth unaffected
3) Remove noindex headers from app.* (keep on beta.*).
4) Update transactional emails/deep links to app.instainstru.com.
5) Monitor: bookings p50/p95, errors, CSRF/CORS blocks, auth failures.

Rollback
- Set PHASE=beta; redeploy; re-run smoke.

Notes
- No DNS or data migration; API host stays api.instainstru.com.
