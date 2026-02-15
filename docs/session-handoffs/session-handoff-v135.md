# InstaInstru Session Handoff v135
*Generated: February 15, 2026*
*Previous: v134 | Current: v135 | Next: v136*

## 🎯 Session v135 Summary

**Security Hardening Sprint + Refresh Token Rotation**

This session delivered a comprehensive security overhaul across two major PRs plus 6 stabilization hotfixes: JWT token lifecycle management (issue → rotate → revoke → invalidate-all), BotID bot protection, CSP enforcement, SecretStr migration, and refresh token rotation with silent session renewal. Combined: 258 files changed, +8,366/-1,170 lines, 8 commits, 5 independent code reviews, production-verified on preview.

| Objective | Status |
|-----------|--------|
| **PR #266: Security Hardening Sprint** | ✅ Merged — JTI revocation, BotID, CSP, SecretStr, cookie-only auth |
| **6 Hotfix Commits** | ✅ Pushed to main — cookie domain fixes, CSP promotion, BotID perf |
| **PR #267: Refresh Token Rotation** | ✅ Merged — silent 401 recovery, atomic JTI rotation, frontend interceptor |
| **Sentry Fixes (API-1V, API-24)** | ✅ Dead index fix, Redis guard, auto-ANALYZE |
| **Preview Verification** | ✅ Silent refresh confirmed end-to-end |
| **Phase 3: Token Lifetime Flip** | ✅ ACCESS_TOKEN_LIFETIME_MINUTES=15 deployed |
| **5 Independent Code Reviews** | ✅ All findings resolved |

---

## 📦 PR #266 — Security Hardening Sprint

**Title:** `security: JWT invalidation, BotID, CSP, SecretStr, cookie-only auth`
**Merged:** Feb 15 | +5,969 / -885 | ~158 files

Four major workstreams based on initial Shannon security assessment:

### 1. JWT Token Invalidation

- **JTI-based per-token revocation** via Redis blacklist with TTL matching JWT expiry
- **`tokens_valid_after`** DB timestamp for global session invalidation (password change, 2FA toggle, suspension, admin force-logout)
- All 4 auth paths enforce blacklist check (Bearer, cookie, SSE, session)
- Strict JTI gate rejects old-format tokens missing required claims
- **Cookie-only token delivery** — removed `access_token` from response bodies
- **ULID-based `sub` claims** replacing email (eliminates PII from tokens)

### 2. BotID Bot Protection

- Sensitive mutations proxied through Next.js API routes (browser → Vercel edge → Render)
- `checkBotId()` enforcement: bots get 403, errors fail-open with Sentry logging
- Read traffic stays direct-to-backend (no latency penalty)
- Protected: auth, bookings, payments, reviews, referrals, messages, 2FA

### 3. 14-Item Review Fix-Up (from 5-agent code review)

- `get_current_user_optional` returns None on revoked tokens (not 401)
- `deactivate_instructor_account` now invalidates sessions
- `revoke_token` returns bool success indicator
- Narrowed bare `except:pass` blocks to logged/typed handlers
- `secret_or_plain` raises ValueError on failure (was empty string)
- Search history optional auth resolves by ULID, not email

### 4. SecretStr Migration

- 17 credential fields migrated to Pydantic `SecretStr`
- Prevents plain secrets from appearing in logs, repr, or serialization
- `secret_or_plain()` helper for backward-compatible extraction

### 5. CSP Foundation

- Content-Security-Policy headers configured (initially report-only)
- Dev environment fallback to localhost:8000 when API env vars unset

---

## 🔧 6 Hotfix Commits (Post-#266 Stabilization)

Real-world iteration on cookies, CSP, and BotID after production deployment:

| Commit | Category | What |
|--------|----------|------|
| `0b2a8cb` | fix | Remove duplicate `idx_instructor_services_profile_active` index from migration |
| `5cd6293` | perf | Bulk INSERT taxonomy seeding + fix SecretStr crash in `reset_schema` |
| `c925595` | fix(auth) | Replace `__Host-` cookies with parent-domain cookies, fix local BotID crash |
| `93d18b2` | fix(auth) | Finalize cookie cleanup and logout domain deletion |
| `9dabbaf` | security(csp) | Promote CSP from report-only → **enforcing**, update tests |
| `c6605bd` | perf+security | Defer BotID init, widen CSP for Leadsy subdomains |
| `26ea1de` | fix(security) | Add `tag.trovo-tag.com` to CSP `frame-src` for Leadsy iframe |

**Key lessons:** `__Host-` cookie prefix doesn't work across subdomains (preview.instainstru.com ↔ preview-api.instainstru.com) — switched to parent-domain `.instainstru.com` cookies. CSP required iterative widening for third-party scripts (Leadsy).

---

## 📦 PR #267 — Refresh Token Rotation

**Title:** `feat(auth): refresh token rotation with silent session renewal`
**Merged:** Feb 15 | +2,397 / -285 | ~100 files | 8 commits

### Backend

- **Refresh token issuance** with `typ=refresh` claim, 7-day TTL, minimal payload (no email)
- **`POST /api/v1/auth/refresh`** endpoint with atomic JTI rotation via Redis SETNX
- **Strict token type enforcement** across all 4 auth paths — access-only, no fallback
- **`set_auth_cookies()`** helper sets both access + refresh cookies on login/2FA/refresh
- **`auth_refresh` rate limit** bucket (10/min, enforced not shadow)
- **`tokens_valid_after`** check during refresh for server-side revocation

### Frontend

- **Single-flight refresh interceptor** with request queuing (`sessionRefresh.ts`)
- ~30 raw `fetch()` calls migrated to `fetchWithSessionRefresh`
- SSE reconnect calls refresh before re-establishing EventSource stream
- **No redirect on public pages** — unauthenticated users stay as guests
- Best-effort logout on refresh failure (clean cookies, return original 401)

### Infrastructure (Sentry Fixes)

| Sentry Issue | Problem | Fix |
|--------------|---------|-----|
| **API-1V** | 3055ms `background_jobs` query, dead partial index | Renamed index `pending` → `queued`, added daily ANALYZE |
| **API-24** | Redis [Errno 111] Connection refused in alert dispatch | `_is_redis_available()` guard before Celery dispatch |

Additional:
- Daily `ANALYZE background_jobs` via Celery Beat (4 AM UTC)
- Task registered in `celery_app.py` imports

### Test Coverage

- 408+ lines added to auth route tests alone
- New E2E mock utilities: `authenticatedPageMocks.ts`, `publicPageMocks.ts`
- Refresh interceptor unit tests with queue/dedup scenarios

### Security Reviews (5 total)

| Review | Reviewer | Key Findings |
|--------|----------|--------------|
| Manual security review #1 | Human + Claude | 8 findings fixed (atomic JTI, fetch coverage) |
| Manual code review #2 | Human + Claude | 3 findings fixed (rate limit shadow, logout cookie, deleted user) |
| CI: Claude bot | Automated | 3 minor suggestions — all addressed |
| CI: Codex | Automated | 1 P2 bug (task registration) — fixed |
| CI: External reviewer | Automated | Shared signing key noted (future hardening), decode naming (cosmetic) |

### Cookie Architecture

| Cookie | Path | Lifetime | Purpose |
|--------|------|----------|---------|
| `sid` / `sid_preview` | `/` | Matches access token TTL | Access token — sent on all requests |
| `rid` / `rid_preview` | `/api/v1/auth/refresh` | 7 days | Refresh token — scoped to refresh endpoint only |

Both cookies: `HttpOnly`, `Secure`, `SameSite=lax`, `Domain=.instainstru.com`

---

## 📊 Platform Health (Post-v135)

| Metric | Value | Change from v134 |
|--------|-------|-------------------|
| **Total Tests** | ~10,500+ | +minor |
| **Backend Coverage** | 95%+ | Maintained |
| **Frontend Coverage** | 95%+ | Maintained |
| **MCP Coverage** | 100% | — |
| **API Endpoints** | 365+ | +2 (refresh, proxy routes) |
| **MCP Tools** | 89 | — |
| **Access Token Lifetime** | 15 min (was 720) | Changed |
| **Refresh Token Lifetime** | 7 days | New |
| **Auth Cookie Count** | 2 (was 1) | +1 (refresh) |
| **SecretStr Fields** | 17 | New |
| **CSP Mode** | Enforcing | Was report-only |

---

## 🔑 Key Files Created/Modified

### PR #266 — Security Hardening
```
backend/app/services/token_blacklist_service.py    # NEW — Redis JTI blacklist
backend/app/utils/cookies.py                       # NEW — set_auth_cookies, delete_refresh_cookie
backend/app/auth/auth.py                           # Modified — ULID sub, typ claims, create_refresh_token
backend/app/auth/auth_session.py                   # Modified — strict token type enforcement
backend/app/auth/auth_sse.py                       # Modified — blacklist check, type enforcement
backend/app/core/config.py                         # Modified — SecretStr migration (17 fields)
frontend/app/api/v1/[...path]/route.ts             # NEW — BotID proxy route
frontend/lib/botid/                                # NEW — BotID client integration
frontend/next.config.ts                            # Modified — CSP headers
```

### PR #267 — Refresh Token
```
backend/app/routes/v1/auth.py                      # Modified — refresh endpoint, set_auth_cookies
backend/app/routes/v1/account.py                   # Modified — logout-all-devices cookie cleanup
backend/app/ratelimit/config.py                    # Modified — auth_refresh bucket
backend/app/tasks/db_maintenance.py                # NEW — daily ANALYZE task
backend/app/tasks/beat_schedule.py                 # Modified — db-maintenance-analyze entry
backend/app/tasks/production_monitor.py            # Modified — Redis health guard
backend/alembic/versions/006_platform_features.py  # Modified — dead index fix
frontend/lib/auth/sessionRefresh.ts                # NEW — single-flight 401 interceptor
frontend/lib/api/http.ts                           # Modified — fetchWithSessionRefresh wired
frontend/src/api/services/*                        # Modified — ~30 files migrated to interceptor
frontend/e2e/fixtures/*                            # Modified — auth mock utilities
frontend/e2e/fixtures/authenticatedPageMocks.ts    # NEW — authenticated page test helpers
frontend/e2e/fixtures/publicPageMocks.ts           # NEW — public page test helpers
```

### Hotfix Commits
```
backend/app/utils/cookies.py                       # Modified — parent-domain cookies
frontend/next.config.ts                            # Modified — CSP enforcing, Leadsy domains
frontend/lib/botid/                                # Modified — deferred init
```

---

## 🔐 Security Checklist (Post-v135)

| Item | Status |
|------|--------|
| JWT removed from response body | ✅ Cookie-only delivery |
| Token lifetime reduced (720→15 min) | ✅ Deployed |
| Refresh token rotation | ✅ Atomic JTI via SETNX |
| Per-token revocation (JTI blacklist) | ✅ Redis-backed |
| Global session invalidation (tokens_valid_after) | ✅ DB timestamp |
| Bot protection (BotID) | ✅ Sensitive mutations proxied |
| CSP enforcing | ✅ Promoted from report-only |
| SecretStr for credentials | ✅ 17 fields migrated |
| Strict token type enforcement | ✅ All 4 auth paths |
| Fail-closed on Redis errors | ✅ Refresh denied if blacklist unavailable |
| Rate limiting on refresh | ✅ 10/min, enforced |

---

## 📋 Remaining Work

| Item | Priority | Notes |
|------|----------|-------|
| Shannon instructor scan | Medium | Independent — run anytime |
| Monitor Sentry 24hrs post-deploy | High | Watch for 401 spikes, CSP violations |
| Separate signing key for refresh tokens | Low | Defense-in-depth hardening, not blocking |
| Rename `decode_access_token` → `decode_jwt_token` | Low | Cosmetic, touches all auth paths |
| Decompose 600-line `search()` method | Low | Structural refactor |
| Decompose 1100-line skill-selection page | Low | Component extraction |
| usePublicAvailability → React Query | Low | Legacy cleanup |

---

## 📝 Architecture Decision Updates

### New ADRs from this session:
- **Cookie-Only Auth** — No tokens in response bodies. Access + refresh delivered exclusively via HttpOnly cookies with parent-domain `.instainstru.com` scoping for cross-subdomain SSO.
- **Atomic JTI Rotation** — Redis `SET NX EX` for refresh token rotation eliminates TOCTOU race conditions. Only one concurrent caller can claim a JTI.
- **Fail-Closed Token Blacklist** — If Redis is unavailable, all blacklist checks deny access (refresh denied, tokens treated as revoked). Security over availability.
- **Path-Scoped Refresh Cookie** — `rid` cookie scoped to `Path=/api/v1/auth/refresh` so browsers never send it to other endpoints. Minimizes exposure surface.
- **Single-Flight Refresh Interceptor** — Frontend deduplicates concurrent 401 recovery into a single refresh call. Prevents thundering-herd refresh storms.
- **Parent-Domain Cookies** — `__Host-` prefix doesn't work across subdomains. Switched to `Domain=.instainstru.com` for preview/beta/production cookie sharing.

---

*Session v135 — Security Hardening + Refresh Tokens: 2 PRs + 6 hotfixes, ~258 files, 5 reviews, production-verified* 🎉

**STATUS: Auth token lifecycle complete. Cookie-only delivery, 15-min access tokens, 7-day rotating refresh tokens, JTI blacklist, BotID, CSP enforcing. Monitoring 24hrs.**
