## Security headers (Frontend)

The Next.js app sets baseline browser security headers from `frontend/next.config.ts` for all routes:

- `Strict-Transport-Security` (HSTS)
- `X-DNS-Prefetch-Control`
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Referrer-Policy`
- `Permissions-Policy`

Notes:

- Some headers may also be set/overridden by the hosting provider (e.g., Vercel).
- `X-Frame-Options: SAMEORIGIN` prevents clickjacking by default. If the app ever needs to be embedded, switch to a CSP `frame-ancestors` policy for finer control.
