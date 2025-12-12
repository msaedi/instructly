## CSRF posture (InstaInstru)

### Auth modes in use

- **Bearer tokens**: Most API calls use `Authorization: Bearer <jwt>` headers.
- **Session cookies (httpOnly)**: Some flows (e.g., SSE/session-based auth) also use a first-party session cookie set by the API.

### Why CSRF matters here

Bearer-token requests are not automatically attached by the browser, so classic CSRF is generally not applicable **when the API only accepts `Authorization` headers**.

Because the backend also supports **cookie-based sessions**, state-changing endpoints must be protected against cross-site requests that automatically include cookies.

### Current protections

- **Origin/Referer enforcement for state-changing methods**: The backend installs `CsrfOriginMiddlewareASGI` (`backend/app/middleware/csrf_asgi.py`) which blocks `POST/PUT/PATCH/DELETE` when neither `Origin` nor `Referer` matches the expected frontend host.
  - **Preview**: allowed host comes from `settings.preview_frontend_domain`.
  - **Prod-like** (`prod|production|beta`): allowed host is derived from the first entry in `settings.prod_frontend_origins_csv`.
  - **Local/dev**: strict CSRF checks are disabled to keep local tooling/simple clients working.
  - **Webhooks**: webhook-style endpoints are exempt (they are not browser-initiated).
- **CORS allowlist (credentials enabled)**: The backend uses `CORSMiddleware` with `allow_credentials=True` and an explicit origin allowlist; broad regex-based origins (e.g., Vercel preview domains) are disabled in prod-like modes.
- **Cookie attributes**: Session cookies are configured with `Secure` and `SameSite` defaults via settings (defense-in-depth, not a replacement for Origin checks).

### Risk level summary

- **Bearer-token API usage**: low CSRF risk (tokens are not auto-sent).
- **Cookie-authenticated endpoints**: protected by Origin/Referer checks + constrained CORS + cookie attributes in prod-like modes.
