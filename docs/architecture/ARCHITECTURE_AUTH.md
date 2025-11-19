# Auth & Session Architecture

## Dual-surface authentication
- **Sessions (cookies)** – `/auth/login-with-session` and 2FA flows issue a host-only cookie (`__Host-sid_preview`/`__Host-sid_prod`) that the SPA uses for browser-originated requests. Cookies are `HttpOnly`, `Secure`, `SameSite=lax`, and `Path=/`.
- **Bearer tokens** – The same endpoints return the raw JWT so mobile clients and scripts can send `Authorization: Bearer …`.
- `public_guard` now resolves the current user from *either* surface and caches the `User` object in `request.state.current_user`. Downstream dependencies reuse that state to avoid re-decoding tokens.

## Session cookie configuration
- `app/core/config.py` exposes `session_cookie_{name,secure,samesite,domain}` so hosted environments always emit hardened cookies while local/dev can opt out of `Secure`.
- `app/utils/cookies.set_session_cookie()` and `/api/public/logout` both read those settings, guaranteeing the same attributes during login and logout.
- Preview/production issue host-only cookies (no `Domain`), so browsers automatically scope them to `https://preview-api.instainstru.com`. Stage/local environments can override attributes through env vars if cross-site testing requires `SameSite=None`.

## Route policy
- Mutating endpoints **must** live under `/api/*` unless explicitly whitelisted (auth bootstrap, webhooks, ops tooling). `tests/integration/test_route_policy.py` enforces this to keep the API surface predictable.
- Read-only legacy instructor routes (`/instructors/*`) remain during migration, but the policy prevents new POST/PATCH additions outside `/api/…`.

## Verification
- `tests/integration/test_auth_guard_cookie_fallback.py` logs in with the seeded QA account and asserts that `/api/addresses/me` succeeds via cookie-only auth while anonymous requests still 401.
- `tests/integration/test_route_policy.py` fails CI if a new mutating route is added outside `/api/*` without updating the allow list.
- `backend/scripts/route_inventory.py` + `PATH_AND_GUARD_AUDIT.md` summarize router/dependency assignments, making it easy to audit future changes.
