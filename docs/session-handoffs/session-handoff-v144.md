# InstaInstru Session Handoff v144
*Generated: March 23, 2026*
*Previous: v143 | Current: v144 | Next: v145*

## 🎯 Session v144 Summary

**Security Sprint + Data/Performance Sprint + Architecture Cleanup Sprint — 38 of 44 Deferred Issues Resolved**

This session triaged 44 deferred issues from 7 independent PR reviews, investigated 8 Sentry issue categories, then executed three focused sprints: security hardening (server-side trusted devices, X-Trusted-Bypass removal), data/performance fixes (N+1 queries, React Query mutations, cache invalidation, Stripe contract), and architecture cleanup (auth login dedup, EmailVerificationService extraction, catalog N+1 batch fix). Each sprint followed the pattern: investigation → implementation → multi-agent audit → CI review → merge.

| Objective | Status |
|-----------|--------|
| **Deferred Issues Triage (44 items from 7 reviews)** | ✅ All triaged |
| **Sentry Issue Triage (8 categories, 27 issues)** | ✅ All investigated |
| **Security Sprint (12 items audited, 4 fixed, 8 dismissed)** | ✅ PR merged |
| **Data/Performance Sprint (8 items fixed)** | ✅ PR merged |
| **Cleanup Sprint (13 items: 8 fixed, 5 dismissed)** | ✅ PR merged |
| **Deferred Issues Resolved** | **38 of 44** |

---

## 🔐 Security Sprint — PR: fix/security-sprint-deferred

### Server-Side Trusted Devices (replaced #1: tfa_trusted cookie)

Full redesign of the trusted device mechanism. The old `tfa_trusted=1` plain cookie (forgeable by any client) was replaced with a server-side device trust system following the Google/GitHub industry pattern.

**New infrastructure:**
- `trusted_devices` table: id, user_id, device_token_hash (SHA-256), device_name, user_agent, created_at, last_used_at, expires_at (30 days)
- `TrustedDeviceRepository` + `TrustedDeviceService` following repository pattern
- Device name derived from User-Agent via simple substring parsing (e.g., "Chrome on macOS", "Safari on iPhone")

**Trust lifecycle:**
- Created after successful TOTP with explicit opt-in ("Trust this browser" checkbox, unchecked by default)
- Validated server-side on login: cookie → SHA-256 hash → DB lookup → user binding + UA match → skip 2FA
- Revoked on: password change, 2FA disable, 2FA setup/verify, manual single/all revoke
- 30-day fixed expiry (no sliding), daily cleanup via Celery beat at 05:30 UTC

**Validation branches (all tested with dedicated integration tests):**
- No cookie → 2FA required
- Cookie hash not in DB → 2FA required, cookie cleared
- Wrong user_id → 2FA required, cookie cleared, other user's row preserved
- Expired → 2FA required, row deleted, cookie cleared
- UA mismatch → 2FA required, row deleted, cookie cleared
- Valid → skip 2FA, update last_used_at

**Frontend:** Trusted devices section in instructor Security settings — device list with name/last used/expiry, per-device Revoke, and Revoke All. Conditionally shown only when 2FA is enabled.

### X-Trusted-Bypass Removed (#2)

Removed entirely from the codebase. No replacement, no environment check, no backdoors. 2FA is tested with a real authenticator app. Regression test (`test_x_trusted_bypass_header_has_no_effect`) ensures it can never be reintroduced.

### Additional Auth Hardening

- **change-password rate limited** (#11): `write` rate limit bucket added
- **2FA /disable rate limited**: Was the only unprotected 2FA endpoint — now uses same IP-based pattern as other 2FA endpoints
- **Celery task enqueue ordering** (#36): Both referral retry tasks now enqueue after DB session commits
- **Cross-user cookie clearing**: `validate_request_trust` now clears cookie on user_id mismatch for consistent hygiene
- **Session rollback on trust failure**: Login succeeds gracefully if trust persistence fails (no 500)

### Security Audit Results (12 items investigated)

| # | Item | Result |
|---|------|--------|
| 1 | tfa_trusted cookie bypass | ✅ FIXED — server-side trusted devices |
| 2 | X-Trusted-Bypass header | ✅ FIXED — removed entirely |
| 3 | Sync authenticate_user timing | DISMISSED — not called in any production path |
| 11 | change-password rate limit | ✅ FIXED |
| 20 | Referral reward race condition | DISMISSED — FOR UPDATE + unique constraints + enqueue-after-commit |
| 26 | Stripe payout idempotency key | DISMISSED — already deterministic (`instructor_referral_bonus_{payout_id}`) |
| 27 | Open redirect via sessionStorage | DISMISSED — Next.js `router.push` only handles internal routes |
| 28 | Global stripe.api_key mutation | DISMISSED — single Stripe account per deployment |
| 34 | Celery task never commits | DISMISSED — `get_db_session()` auto-commits on context exit |
| 35 | Missing destination validation | DISMISSED — nullable=False + onboarding guard + max_retries=3 |
| 36 | Task enqueue before commit | ✅ FIXED |
| 37 | Email enumeration via login | DISMISSED — lockout keys based on email string, not DB existence |

**PR reviews:** 6 independent audits (4 agent audits + Claude bot + Codex). All findings resolved. Manual testing passed 9 of 10 test steps (10th verified via regression test + curl).

### Key Files
```
backend/app/models/trusted_device.py (NEW)
backend/app/repositories/trusted_device_repository.py (NEW)
backend/app/services/trusted_device_service.py (NEW)
backend/app/routes/v1/auth.py
backend/app/routes/v1/two_factor_auth.py
backend/app/schemas/security.py
backend/app/tasks/db_maintenance.py
backend/app/tasks/referral_tasks.py
frontend/app/(shared)/login/LoginClient.tsx
frontend/app/(auth)/instructor/settings/SettingsImpl.tsx
frontend/hooks/queries/useTrustedDevices.ts (NEW)
```

---

## ⚡ Data/Performance Sprint — PR: fix/data-performance-sprint

Eight fixes identified across 7 independent PR reviews, all confirmed real issues via investigation.

### N+1 Booking Fetch (#7)
Created `BookingRepository.get_by_ids()` — single `WHERE id IN (...)` with same eager loading as `get_by_id`. Replaced per-booking loop in `get_messages_with_details` with batch fetch + dict lookup.

### React Query Mutations (#9)
- **Settings save**: `useMutation` with cache invalidation (auth.me, instructors.me, addresses)
- **Earnings export**: `useMutation` with blob download in `onSuccess`
- Both use `isPending` from mutation, eliminating local state variables

### Partial Success Toast (#10)
Settings save surfaces address sync failures: "Profile updated, but address failed to save. Please try again." Old silent catch-and-ignore pattern eliminated.

### Single Query for Referral Rewards (#14)
Three sequential status queries → single bounded query (`LIMIT limit*3`), grouped in Python, per-status limit preserved.

### Review Cache Invalidation (#15)
`_invalidate_instructor_caches` now deletes: overall rating key + `:all` search key + per-service search keys (dynamically fetched). Unconditional keys deleted FIRST before service-specific DB query — DB failure only affects service-specific cache.

### Conversation Sender Restoration (#21)
Both `send_message` and `send_message_with_context` now restore BOTH sender and recipient to active. `send_message` wrapped in explicit `with self.transaction():` for atomicity.

### Stripe Transfer Contract (#38)
Standardized to TypedDict-based return:
- Success: `ReferralBonusTransferSuccessResult` — `{"status": "success", "transfer_id": str, "amount_cents": int}`
- Skipped: `ReferralBonusTransferSkippedResult` — `{"status": "skipped", "reason": "zero_amount", ...}`
- Caller uses direct key access, raises on unexpected status

### Review Filter Memoization (#42)
`reviewFilters` wrapped in `useMemo([selectedRating, withCommentsOnly])`.

**PR reviews:** 2 agent audits + Claude bot + Codex + CodeRabbit. All findings resolved (cache invalidation ordering, SQL LIMIT, Stripe contract enforcement, send_message transaction).

### Key Files
```
backend/app/repositories/booking_repository.py
backend/app/repositories/referral_repository.py
backend/app/services/conversation_service.py
backend/app/services/referral_service.py
backend/app/services/review_service.py
backend/app/services/stripe_service.py
backend/app/tasks/referral_tasks.py
frontend/app/(auth)/instructor/settings/SettingsImpl.tsx
frontend/app/(auth)/instructor/earnings/page.tsx
frontend/app/(auth)/instructor/reviews/page.tsx
```

---

## 🏗️ Cleanup Sprint — PR: fix/cleanup-sprint

13 items across 3 waves. 8 fixed, 5 dismissed as non-issues after investigation.

### Wave 1 — Quick Wins (8 XS fixes)

| # | Item | Fix |
|---|------|-----|
| 5 | setattr(service.db) anti-pattern | Explicit `student_id` parameter to service method, removed setattr/getattr |
| 16 | Conversation user enumeration | Both missing-user cases → same generic 404: "Cannot create conversation with this user." |
| 22 | 2FA input type="text" | Added explicit `type="text"` alongside `inputMode="numeric"` |
| 23 | Midnight booking message | "Bookings cannot span multiple days (end time at midnight is allowed)." |
| 24 | Missing logger.error × 3 | Added to all booking detail catch blocks (handleMarkComplete, handleMarkNoShow, handleMessageStudent) |
| 33 | Logger in component body × 2 | Moved into `useEffect(() => {...}, [])` — mount-only logging |
| 43 | display_name space fallback | Conditional suffix: `f"{first} {last_init}." if last_init else first` — no "FirstName ." |
| 44 | PII in login+signup logs | Email masked to domain only via `email.split('@')[1]` in all log payloads |

### Wave 2 — Small Refactors (4 S fixes)

**Auth Login Deduplication (#8)**
Extracted 155-line `_authenticate_and_respond()` private helper. Handles: lockout, CAPTCHA, rate limiting, user fetch, timing-safe password verification, 2FA challenge, token generation, cookies, device notification, audit logging.
- `login()`: 193 → 48 lines
- `login_with_session()`: 200 → 35 lines
- Response contracts preserved (structured dicts vs. string details)
- No FastAPI/Starlette imports in AuthService — clean separation

**_user_obj Eliminated (#12)**
`fetch_user_for_auth` returns `AuthUserSnapshot` TypedDict with primitives only (id, email, hashed_password, totp_enabled, account_status, first_name, last_name, is_active, beta_claims). Zero ORM objects cross service→route boundary. DB connection released before Argon2id verification.

**Timezone-Safe isPastLesson (#17)**
Primary path uses `booking.booking_end_utc` (ISO 8601 UTC comparison). Fallback uses timezone-aware `resolveBookingDateTimes()`. No raw browser-local `new Date(\`${date}T${time}\`)` parsing.

**N+1 Catalog + Availability Fix (S2+S6)**
- Catalog: single bulk `get_active_services_with_categories(limit=None)` + `get_or_create_bulk(service_ids)` → ~3 queries (was ~100-200)
- Availability: `get_days_in_range()` + `get_bookings_for_date_range()` → 2 queries (was ~60-90)
- New repository methods: `ConflictCheckerRepository.get_bookings_for_date_range()`, `ServiceAnalyticsRepository.get_or_create_bulk()`

### Wave 3 — Email Verification Extraction (#18)

Extracted 173 lines + 13 helper functions from `auth.py` into new `EmailVerificationService`. auth.py reduced from 1,695 → 1,291 lines (-404).

**Service interface:**
- `check_send_rate_limit(email, client_ip)` — per-email + per-IP throttling
- `generate_and_store_code(email)` — 6-digit code, Redis-backed
- `send_verification_email(email, code)` — via Resend
- `verify_code(email, code)` — timing-safe comparison, lockout protection
- `validate_registration_token(email, token)` — JWT signature + expiry + email match
- `consume_token_jti(claims)` — single-use enforcement via Redis

Routes are thin delegation: create service → call method → return response.

### Dismissed Items (5)

| # | Item | Why |
|---|------|-----|
| 13 | Lazy NotificationService init | DI already works, lazy init is just fallback |
| 19 | Frontend hardcoded referral amounts | Already dynamic — uses API response |
| 39 | Silent notification skip for non-booking messages | Intentional design, logged |
| 40 | SQL interpolation in migration helpers | Safe, hardcoded inputs, runs once |
| 41 | sessionStorage SSR safety | Already guarded, inside event handlers |

**PR reviews:** 4 agent audits + Claude bot + Codex. Signup PII masking caught and fixed before merge. All findings resolved.

### Key Files
```
backend/app/services/email_verification_service.py (NEW)
backend/app/routes/v1/auth.py
backend/app/routes/v1/reviews.py
backend/app/routes/v1/conversations.py
backend/app/services/auth_service.py
backend/app/services/booking_service.py
backend/app/services/instructor_service.py
backend/app/services/availability_service.py
backend/app/services/trusted_device_service.py
backend/app/repositories/conflict_checker_repository.py
frontend/app/(auth)/instructor/bookings/[id]/page.tsx
frontend/app/(shared)/login/LoginClient.tsx
frontend/app/(shared)/signup/page.tsx
```

---

## 🔍 Sentry Investigation

| Category | Verdict | Action Taken |
|----------|---------|-------------|
| Missing DB tables (228 events/week) | ✅ RESOLVED | Ran migrations on preview + beta at session start |
| S1: Stripe Connect transfers capability (3 users) | DISMISSED | Not a code issue — preview seed accounts never completed Stripe onboarding. Code correctly requests `transfers` capability. |
| S2+S6: N+1 queries (6.4s catalog) | ✅ FIXED | Bulk fetch + batch analytics in cleanup sprint |
| S3: Email rate limiting | DEFERRED | Add retry-with-backoff to email Celery task |
| S4: Kombu/Redis KeyError: 29 | DEFERRED | Already on latest celery 5.6.2/kombu 5.6.2. Not a simple upgrade fix. |
| S5: Login cold start 6.7s | DEFERRED | Infrastructure decision (Render min_instances). Code warming already exists. |
| S7: MCP server 422 | LOW | Single occurrence, admin tool |
| S8: Worker timeout | LOW | Likely resolved by catalog N+1 fix |

---

## 🏛️ Architecture Decisions (v144)

- **Server-side device trust** — DB-backed with hashed tokens. Cookie holds plain token (lookup key), DB stores SHA-256 hash. Same pattern as password hashing but without salt (token is already random).
- **No developer 2FA bypasses** — removed entirely, not tightened. Test with real authenticator apps.
- **Route-private auth helper** — `_authenticate_and_respond` stays in auth.py. Login orchestration involves cookies, Response objects, audit logging — route-level concerns that don't belong in AuthService.
- **Primitives-only auth payload** — `AuthUserSnapshot` TypedDict. No ORM objects cross the service→route boundary.
- **EmailVerificationService as standalone** — instantiated in routes from request-scoped DB session. Not a DI provider.
- **Typed Stripe transfer contract** — discriminated TypedDict union on `status` field. Direct key access, fails loudly on shape mismatch.
- **Unconditional cache clears first** — review invalidation deletes guaranteed keys before attempting DB lookup for service-specific keys.
- **Bounded single-query rewards** — `LIMIT limit*3` in SQL, grouped + sliced in Python.

---

## 📊 Platform Health (Post-v144)

| Metric | Value | Change from v143 |
|--------|-------|-------------------|
| **Backend Tests** | 13,296+ | +90 |
| **Frontend Tests** | 8,321+ | +18 |
| **Frontend Suites** | 417 | +2 |
| **E2E Tests** | 225 passing | Maintained |
| **Backend Coverage** | 98%+ | Maintained |
| **Frontend Coverage** | 97%+ | Maintained |
| **Frontend Type Coverage** | 100% | Maintained |
| **auth.py Lines** | 1,291 | Was: 1,695 (-404) |
| **login() Lines** | 48 | Was: 193 |
| **login_with_session() Lines** | 35 | Was: 200 |
| **PRs Merged** | 3 | Security + Data/Perf + Cleanup |
| **Independent Audits** | 12+ | Across all 3 sprints |
| **Deferred Items Resolved** | 38/44 | 20 fixed, 13 dismissed, 5 non-issues |
| **Catalog Queries** | ~3 | Was: ~100-200 |
| **Availability Queries** | ~2 | Was: ~60-90 |

---

## 📋 Remaining Work

### Deferred Items (6 remaining)

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 6 | Route handlers creating repositories directly (32 instances) | Low | L effort. Tackle per-feature as routes are touched. |
| S3 | Email rate limiting (Resend 5 req/s) | Low | Add retry-with-backoff to email Celery task |
| S4 | Kombu/Redis KeyError: 29 | Medium | Already on latest versions. Needs deeper investigation. |
| S5 | Login cold start 6.7s | Medium | Infrastructure: Render min_instances +$15/mo |
| S7 | MCP server 422 on instructors_list | Low | Single occurrence, check param validation |
| S8 | Worker timeout | Low | Likely resolved by catalog N+1 fix |

### Platform Backlog

| Item | Priority | Notes |
|------|----------|-------|
| #18 — Push notification verification | Medium | Verify toggle behavior with/without device permission |
| SEO programmatic pages | Low | 7 categories × 77 subcategories × 224 services × neighborhoods |

---

## 🔑 Git History (main, post-v144)

```
HEAD     fix(cleanup): auth dedup, email verification extraction, N+1 catalog fix, 13 deferred items
         fix(perf): batch queries, React Query mutations, cache invalidation, conversation restore, Stripe contract
         fix(auth): server-side trusted devices, remove X-Trusted-Bypass, auth hardening
         [v143 commits below]
```

---

**STATUS: 38 of 44 deferred issues resolved across 3 sprints. Server-side trusted devices live. X-Trusted-Bypass eliminated. Auth deduplicated (login 193→48 lines). EmailVerificationService extracted (auth.py -404 lines). Catalog N+1 fixed (3 queries vs ~200). 12+ independent audits passed. 13,296 backend + 8,321 frontend + 225 e2e tests passing. Type coverage 100%.**
