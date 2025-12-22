## Security Headers

### Frontend (Next.js)

The Next.js app sets baseline browser security headers from `frontend/next.config.ts` for all routes:

- `Strict-Transport-Security` (HSTS)
- `X-DNS-Prefetch-Control`
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Referrer-Policy`
- `Permissions-Policy`

Notes:
- Some headers may also be set/overridden by the hosting provider (e.g., Vercel).
- `X-Frame-Options: SAMEORIGIN` prevents clickjacking by default.

### Backend (FastAPI)

The backend API sets security headers via `HTTPSRedirectMiddleware` (`backend/app/middleware/https_redirect.py`):

- `Strict-Transport-Security`: `max-age=31536000; includeSubDomains; preload` (1 year HSTS with preload)
- `X-Content-Type-Options`: `nosniff` (prevents MIME-type sniffing)
- `Content-Security-Policy`: `default-src 'none'; frame-ancestors 'none'` (minimal CSP for API)

Notes:
- HSTS only applied to HTTPS responses
- CSP is minimal since API returns JSON, not HTML
- Headers set for defense-in-depth
