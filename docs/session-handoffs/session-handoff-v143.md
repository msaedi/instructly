# InstaInstru Session Handoff v143
*Generated: March 22, 2026*
*Previous: v142 | Current: v143 | Next: v144*

## 🎯 Session v143 Summary

**Stripe PaymentElement + Dashboard Beast (41/41 COMPLETE) + Commission Tier Auto-Update + Booking Flow Hardening + Email Verification + Invite Enforcement**

Two massive work phases: Phase 1 delivered 5 PRs (PaymentElement, commission tiers, availability redesign, 25 dashboard quick wins, booking flow hardening). Phase 2 completed all remaining 14 Dashboard Beast items, closed the server-side registration security gap, implemented pre-registration email verification, fixed overnight booking protection, and cataloged 44 deferred issues from 7 independent PR reviews.

| Objective | Status |
|-----------|--------|
| **Stripe CardElement → PaymentElement Migration** | ✅ PR #337 merged |
| **Apple Pay / Google Pay / Link** | ✅ Enabled — Apple Pay confirmed on Safari |
| **Availability Page Redesign (A-Team #33)** | ✅ PR #339 merged |
| **Commission Tier Display + Auto-Update (A-Team #39)** | ✅ PR #338 merged |
| **Dashboard Quick Wins (25 items)** | ✅ PR #340 merged |
| **Booking Flow Hardening (B1/B2/B3)** | ✅ PR #341 merged |
| **Booking List Card + Detail Redesign (#24/25/26)** | ✅ PR #342 merged |
| **Referral Cleanup + Page Redesign (#2/4/11/32)** | ✅ PR #342 merged |
| **Settings + Earnings Polish (#13/16/30/31)** | ✅ PR #342 merged |
| **Reviews Redesign (#34)** | ✅ PR #342 merged |
| **Messages Standard Layout (#35)** | ✅ PR #342 merged |
| **Notification Navigation (#41)** | ✅ PR #342 merged |
| **Email Verification + Invite Enforcement + Phone Go-Live (#40 + Security)** | ✅ PR #342 merged |
| **Overnight Booking Protection Fix** | ✅ PR #342 merged |
| **Auth Hardening (PR review findings)** | ✅ PR #342 merged |
| **A-Team Dashboard Beast** | ✅ **41/41 complete** |
| **Platform Launch State Audit** | ✅ Beta system + STG DB audited |

---

## 💳 Stripe CardElement → PaymentElement Migration (PR #337)

### What Changed

Full migration from CardElement to PaymentElement, unlocking Apple Pay, Google Pay, and Link (one-click checkout).

**Backend:**
- New `POST /api/v1/payments/setup-intent` with student role validation
- `automatic_payment_methods` + `allow_redirects: "never"` on ALL 4 PaymentIntent + 2 SetupIntent creation paths
- `_advance_booking_on_capture` webhook handler: confirms booking on `requires_capture`, atomic `UPDATE WHERE status=PENDING`
- `_check_stripe_configured()` guard + `except HTTPException: raise` on setup-intent route

**Frontend:**
- PaymentMethods, PaymentMethodSelection, CheckoutFlow all use PaymentElement + `confirmSetup`/`confirmPayment`
- Tip payment: don't navigate on tip failure (retry enabled)
- PI cached across tab toggles (`hasFetchedIntentRef` + reset on error)
- `saveCard` checkbox removed (always saves, users manage from billing)

**Zero legacy patterns:** 0 CardElement, 0 `confirmCardPayment`, 0 `payment_method_types`

**Rate limit:** `/setup-intent` uses `"write"` not `"financial"` — SetupIntent is preparatory, React StrictMode double-mount would hit financial bucket's 0 burst.

**Wallet payments:** Apple Pay confirmed on Safari. Google Pay requires card in Google Wallet. Domain registration complete for instainstru.com, www, beta, preview.

### Key Files
```
backend/app/routes/v1/payments.py
backend/app/services/stripe_service.py
frontend/components/booking/CheckoutFlow.tsx
frontend/features/student/payment/components/PaymentMethods.tsx
frontend/features/student/payment/components/PaymentMethodSelection.tsx
frontend/features/shared/payment/utils/stripe.ts
```

---

## 📅 Availability Page Redesign — A-Team #33 (PR #339)

Controls moved above calendar, compact inline format pills, side-by-side buffer cards with NYC-specific copy, simplified overnight protection. Buffer minimums changed: non-travel 0→10min, travel 15→30min.

---

## 📊 Commission Tier Display + Auto-Update — A-Team #39 (PR #338)

### New Endpoint

`GET /api/v1/instructors/me/commission-status` — returns tier name, rate, completed lessons in configurable window, tier ladder with progress.

### Tier Auto-Update (was never automatic before)

**Problem found:** `current_tier_pct` was NEVER updated automatically. Set at seed time, only changed by admin. The pricing calculation `_resolve_instructor_tier_pct()` dynamically computed correct rates at transaction time but never persisted.

**Fix:**
- `_maybe_refresh_instructor_tier()` at end of both `complete_booking()` and `instructor_mark_complete()`
- Also wired into `_auto_complete_booking()` in payment tasks
- Daily Celery beat at **3:15am** evaluates all active non-founding instructors
- Founding instructors excluded from sweep query
- Bulk completion stats query (eliminates 2N individual queries)
- Respects `tier_stepdown_max`, `tier_inactivity_reset_days`, founding immunity
- `count_instructor_completed_in_window` (renamed from `_last_30d`) accepts configurable window
- `activity_window_days` returned in API response

### Frontend — CommissionTierCard

Founding view: Star icon, "8% · locked" badge, availability commitment text.
Standard view: tier ladder with progress bars. Entry never has a bar. Completed non-Entry tiers get full bars. Next tier gets partial bar with helper text. Platform brand purple on bars and checkmarks.

### Key Files
```
backend/app/routes/v1/instructors.py
backend/app/services/pricing_service.py
backend/app/tasks/beat_schedule.py
backend/app/repositories/booking_repository.py
frontend/components/earnings/CommissionTierCard.tsx
frontend/hooks/queries/useCommissionStatus.ts
```

---

## 🎨 Dashboard Quick Wins — 25 Items (PR #340)

### Part 1 — Icons, Settings, Profile (13 items)

| # | Item |
|---|------|
| 1 | Confetti emoji → Lucide Rocket on Go Live |
| 6+7 | Phosphor Star, proportional fill, inline `4.5★ (3)` on Reviews card |
| 10 | Phone formatted `(212) 555-1001`, shared `formatPhoneDisplay` helper |
| 12 | 2FA state refreshes immediately after enable/disable |
| 14 | Single-open accordion: 7 booleans → 1 `OpenSection` union type |
| 15 | 2FA modal: "Connect your authenticator app", Step 1/Step 2, "Verify" |
| 17 | Phone management block removed from Preferences |
| 19 | Per-toggle `pendingPreferences` map, no column flash |
| 20 | Remove Acknowledgments, Info icon, "Support" label |
| 21 | Distinct icons: UserRoundPen, SlidersHorizontal, Info |
| 22 | Personal Information removed from Instructor Profile |
| 23 | Skills & Pricing → Phosphor Tag |

### Part 2 — Bookings, Nav, Messages, Launch Gate (8 items)

| # | Item |
|---|------|
| 5 | Public Profile: environment-aware (beta=gated, preview=always enabled) |
| 27 | Text-width tab indicators via shared `textWidthTabs` helper |
| 28 | Completed badge blue everywhere (shared `bookingStatus` helper) |
| 29 | Two-line empty states: bold heading + muted subtitle in dashed card |
| 36 | Template timestamp: actual date or hidden |
| 37 | Messages dropdown: sentence case, green badge, clickable cards |
| 38 | Left nav reorder + Messages route link (text-only) |

### Additional Fixes

| Item | What changed |
|------|-------------|
| Account Details (#8,9) | Split Name → First + Last (locked/verified). ZIP editable. |
| Phone verification | Inline 3-state: Verified (green) → Verify (purple) → Pending (amber + code) |
| 2FA redirect | Disable: immediate `/login`. Enable: backup codes → acknowledge → `/login`. |
| `student_launch_enabled` | Platform config flag, default `false`, read-only |
| `@phosphor-icons/react` | New dependency |

### Key Files
```
frontend/app/(auth)/instructor/settings/SettingsImpl.tsx
frontend/app/(auth)/instructor/dashboard/page.tsx
frontend/components/security/TfaModal.tsx
frontend/features/instructor-profile/InstructorProfileForm.tsx
frontend/lib/phone.ts
frontend/lib/bookingStatus.ts
frontend/lib/textWidthTabs.ts
frontend/lib/publicProfileLaunch.ts
frontend/lib/instructorDashboardNav.ts
backend/app/services/config_service.py
```

---

## 🔧 Booking Flow Hardening (PR #341)

### Three Pre-Launch Bugs Fixed

**B1: Stale booked slots shown as available.**
Public availability was Redis-cached. Booking creation didn't invalidate. Fixed: `_invalidate_booking_caches()` on BOTH `create_booking()` AND `create_booking_with_payment_setup()`. Search cache invalidation works in sync/thread contexts via `asyncio.run()` fallback.

**B2: Format tags not filtered on checkout edit.**
`confirm/page.tsx` overwrote metadata with only `{ serviceId }`. Fixed: merge instead of replace. Format locked on checkout.

**B3: No pre-flight availability check.**
Checkout only checked student-side conflicts. Backend had `check-availability` endpoint but nobody called it. Fixed: wired into post-time-edit and pre-submit paths.

### Checkout UX Redesign

Format toggle removed. Format decided in time modal, read-only on checkout. "Edit lesson" reopens modal with `lockLocationType=false`.

**Format badges:** Online (green), At instructor's (purple), At your location (amber), At a meeting point (amber).

**Address handling:** No UI for online. No input for instructor_location. Picker for student/neutral_location. Placeholder strings sanitized.

### Key Files
```
backend/app/services/booking_service.py
backend/app/services/search/cache_invalidation.py
backend/app/routes/v1/bookings.py
frontend/app/(auth)/student/booking/confirm/page.tsx
frontend/features/student/payment/components/PaymentConfirmation.tsx
frontend/features/student/payment/components/PaymentSection.tsx
frontend/features/student/payment/utils/locationUtils.ts
frontend/features/student/payment/utils/buildAvailabilityCheckRequest.ts
frontend/components/InstructorCard.tsx
```

---

## 📋 Booking List Card + Detail Page Redesign (#24/25/26) — PR #342

**List card:** Badge-only header row (no duplicate subject), student first + last initial via `formatStudentDisplayName`, 2×2 detail grid with Lucide icons (date, time, duration·subject, location), keyboard-accessible card link, "View lesson ›" footer. Same layout for Upcoming and Past tabs.

**Detail page:** Shortened human-friendly ID (`shortenBookingId` → `#KWD-3124`), created date, privacy-safe student name, Message pill via resolve-first conversation flow, muted uppercase labels (DATE, TIME, LOCATION) with icons, three pricing metric tiles with 2-decimal formatting, optional payout status row for completed bookings. Standard dashboard shell with consistent header. Join Lesson button restored for online bookings within join window.

**Conversation API clean break:** Renamed `instructor_id` → `other_user_id`, symmetric role-pair validation (student↔instructor both directions), get-or-create semantics preserved. All callers updated in one pass. No backward compatibility.

**Shared utilities:** `shortenBookingId`, `formatStudentDisplayName`, `formatPrice`, `bookingLocation` formatter, `BookingStatusBadge`.

**Fixes:** React Query cache-key collision between upcoming/past queries (both had `status: undefined` → identical keys), removed all `istanbul ignore` suppression comments from PaymentConfirmation, post-lesson return link fixed to dashboard route.

### Key Files
```
frontend/lib/bookingId.ts, studentName.ts, price.ts, bookingLocation.ts
frontend/features/bookings/components/InstructorBookingCard.tsx
frontend/features/bookings/components/InstructorBookingDetailView.tsx
frontend/features/bookings/components/BookingStatusBadge.tsx
frontend/src/api/queryKeys.ts
frontend/src/api/services/instructor-bookings.ts
backend/app/schemas/conversation.py
backend/app/routes/v1/conversations.py
backend/app/services/conversation_service.py
```

---

## 🎁 Referral Cleanup + Page Redesign (#2/4/11/32) — PR #342

**Page redesign:** Two reward cards ($50 instructor / $20 student cash), referral link with copy/share, invite by email, three stat tiles (Total Referred / Pending Payouts / Total Earned), tabbed rewards (Pending / Unlocked / Redeemed), "How it works" section with iNSTAiNSTRU branding.

**New payout flow:** Instructor-refers-student $20 cash via Stripe Transfer. Referred student keeps $20 credit. Reuses existing instructor payout pipeline. Idempotency keys scoped to booking_id.

**New endpoint:** `GET /api/v1/instructor-referrals/dashboard` — page-ready response with stats, reward rows, and referral link. Query bounded to 500 rows.

**Fixed /r/ route:** Frontend `/r/[slug]` handler + backend redirect to `/signup?ref=CODE` using configured frontend origin (not request host). Signup preserves and claims ref param.

**Removed:** Founding referral popup, founding bonus UI ($75 dead), referral section from Account Settings, old instructor referral service shim.

### Key Files
```
frontend/app/(auth)/instructor/referrals/page.tsx
frontend/hooks/queries/useInstructorReferrals.ts
backend/app/routes/v1/instructor_referrals.py
backend/app/routes/v1/referrals.py
backend/app/services/referral_service.py
backend/app/repositories/referral_repository.py
```

---

## ⚙️ Settings + Earnings Polish (#13/16/30/31) — PR #342

**Settings:** Merged "Account Security" + "Password" into single "Security" section. 2FA uses shared ToggleSwitch with contextual labels. Standalone `/instructor/settings` at parity with dashboard panel.

**Earnings:** 4 stat cards → 3 (Gross Earnings, Net Earnings, Lessons with hours subtitle). `PLATFORM_LAUNCH_YEAR` constant. `SimpleDropdown` extracted to module scope. Export modal: dynamic year dropdown (2026+ only), toast feedback on success/failure.

---

## ⭐ Reviews Redesign (#34) — PR #342

Partial-fill Phosphor star, one-decimal rating, inline count, right-aligned filters. Review cards: stars + privacy-safe name + relative/absolute timestamps. Instructor reply action with inline display. Backend returns reviewer name parts and existing responses (single DB fetch, not double). Centralized review query keys.

Seed data: Sarah Chen 5 deterministic reviews [5,4,4,4,3], mixed comments, varied students and timestamps.

---

## 💬 Messages + 🔔 Notifications (#35/41) — PR #342

**Messages:** Dashboard panel layout via embedded pattern. `/instructor/messages` redirects to `/instructor/dashboard?panel=messages`. `DashboardNavKey` union type for route-based nav highlighting. Full consistent header on all dashboard pages.

**Notifications:** Click navigates to specific booking detail (`/instructor/bookings/{booking_id}`) AND marks as read. Message notifications → conversation deep link. Role-aware routing (instructor vs student messages).

**Student messages:** New `/student/messages` page for role-aware conversation navigation from `MessageInstructorButton`.

---

## 🔐 Email Verification + Invite Enforcement + Phone Go-Live (#40 + Security) — PR #342

### Email Verification

Two pre-registration endpoints:
- `POST /api/v1/auth/send-email-verification` — 6-digit code via Resend, Redis-backed (5-min TTL), stored BEFORE send, per-email limit (3/10min), per-IP limit (20/hour)
- `POST /api/v1/auth/verify-email-code` — constant-time comparison, 5-attempt lockout, returns signed JWT with unique jti (15-min TTL, single-use via Redis)

### Invite Enforcement

`POST /api/v1/auth/register` now requires:
1. Valid email verification token (signed JWT, jti unconsumed)
2. Token email = registration email
3. Valid invite code when `beta_phase` requires it (`invite_required_for_registration(role, phase)` helper)
4. Invite email = registration email

All checks BEFORE user row creation. `allow_signup_without_invite` is dormant. Password min_length=8 enforced on UserCreate.

### Phone Go-Live Gate

`phone_verified` required for go-live. Inline verification in onboarding Account Setup under Personal Information.

### Frontend Flow

Signup → send verification → `/verify-email` page (6-digit input, resend cooldown, wrong-email back link) → register with token. Both student and instructor flows. Form data in sessionStorage, cleared after registration.

### Key Files
```
backend/app/routes/v1/auth.py
backend/app/auth.py
backend/app/services/auth_service.py
frontend/app/(shared)/verify-email/page.tsx
frontend/app/(shared)/signup/page.tsx
frontend/features/shared/auth/pendingSignup.ts
```

---

## 🌙 Overnight Booking Protection Fix — PR #342

**Bug:** Protection only blocked "tomorrow" early slots, missing post-midnight case (same sleep cycle).

**Fix:** Sleep-cycle-aware guard — before midnight: protect tomorrow. After midnight: protect today. Day-after-tomorrow+ never protected. Fixed in both `public.py` and `booking_service.py`. 37 tests covering both sides of midnight.

---

## 🔧 Auth Hardening (PR Review Fixes) — PR #342

Applied after 7 independent reviews: single-use JWT via jti, per-IP rate limit (20/hr), 503 on delivery failure, code stored before send, ValidationException passthrough, generic errors (no internal leaks), PII masked in auth logs, reviews exception tightening, MCP CORS fix, brand casing fixes, centralized API constants, no-show modal ARIA, onboarding name-mismatch link fix, booked availability slots now clickable.

---

## 🔍 Platform Launch State Audit

### STG Database State

| Item | Value |
|------|-------|
| Beta phase | `instructor_only` |
| Total users | 75 (1 real, 74 seed) |
| Instructor profiles | 68 total, 65 live, **0 founding** |
| Beta invites generated | **0** |
| `student_launch_enabled` | `false` |
| Founding cap | 100 (0 used, 100 remaining) |
| Registration security | **CLOSED** — requires email verification + invite |

---

## 🏛️ Architecture Decisions (v143)

- **PaymentElement over CardElement** — `automatic_payment_methods` + `allow_redirects: "never"`
- **Tier auto-update on booking completion** — persisted at completion + daily sweep
- **Format locked on checkout** — decided in time modal, read-only on checkout
- **Cache invalidation on booking creation** — both create paths invalidate
- **`student_launch_enabled` as platform config** — environment-aware on frontend
- **Email verification before account creation** — verify email, then create account
- **Signed JWT verification token with jti** — stateless validation, single-use via Redis
- **`beta_phase` as single invite control** — no hostname checks, no env bypasses
- **`invite_required_for_registration(role, phase)`** — extensible policy helper
- **Code stored before email send** — prevents race condition
- **`other_user_id` over `instructor_id`** — role-agnostic conversation creation, clean break
- **Messages as dashboard panel** — redirects to `/instructor/dashboard?panel=messages`
- **`DashboardNavKey`** — union type for panel + route nav items
- **Sleep-cycle overnight protection** — midnight-crossing-aware date guard
- **Availability independent of bookings** — booked slots remain interactive

---

## 📊 Platform Health (Post-v143)

| Metric | Value | Change from v142 |
|--------|-------|-------------------|
| **Backend Tests** | 13,206+ | +40 |
| **Frontend Tests** | 8,303+ | +41 |
| **Frontend Suites** | 415 | — |
| **E2E Tests** | 225 passing | New |
| **Backend Coverage** | 98%+ | Maintained |
| **Frontend Coverage** | 97%+ | Maintained |
| **Frontend Type Coverage** | 100% | Maintained |
| **API Endpoints** | 378+ | +6 |
| **PRs Merged** | 6 (#337–#342) | — |
| **Celery Beat Tasks** | 28+ | +1 |
| **Payment Methods** | Card + Apple Pay + Google Pay + Link | Was: Card only |
| **A-Team Items Done** | **41/41** | Was: 0/41 |
| **Registration Security** | Email verification + invite enforcement | Was: open |

---

## 📋 Remaining Work

### Deferred Issues (44 items — full list in `deferred-issues-post-pr.md`)

**Security sprint (URGENT):**
- tfa_trusted cookie bypass (2FA forgeable)
- X-Trusted-Bypass header too broad
- Sync authenticate_user timing leak
- Celery referral payout task never commits DB (#34-36)
- Referral reward race condition
- Stripe payout idempotency key (uuid4 defeats retry)
- Open redirect via sessionStorage
- Global stripe.api_key mutation

**Architecture cleanup:** send_message transaction, setattr anti-pattern, direct repo access in routes, login duplication, auth route extraction, Stripe return types

**Performance:** N+1 queries (confirmed by Sentry — 6.4s catalog), Kombu/Redis KeyError, cold start latency

### Sentry Active Issues

| Priority | Issue | Action |
|----------|-------|--------|
| **HIGH** | Stripe Connect transfers capability — 3 users blocked | Enable on connected accounts |
| MEDIUM | N+1 queries (catalog, availability, bookings) | Add joinedload |
| MEDIUM | Kombu/Redis KeyError: 29 (6 fatal) | Upgrade celery/kombu |
| LOW | Email rate limiting (Resend 5 req/s) | Retry-with-backoff |

### Platform Backlog

| Item | Priority | Notes |
|------|----------|-------|
| **Founding instructor activation** | **CRITICAL** | 0 invites sent. System ready. Registration secured. |
| #18 — Push notification verification | Medium | Verify toggle behavior with/without device permission |
| SEO programmatic pages | Low | 7 categories × 77 subcategories × 224 services × neighborhoods |
| Student acquisition launch | Blocked | Post founding activation |

---

## 🔑 Git History (main, post-v143)

```
HEAD     feat(dashboard): complete A-Team Dashboard Beast (41/41) + email verification + invite enforcement (#342)
         fix(booking): harden booking flow — format lock, cache invalidation, pre-flight checks (#341)
         feat(dashboard): A-Team quick wins — 25 UI fixes + account details redesign (#340)
         fix(earnings): address PR review findings on commission tier
         feat(earnings): commission tier display with auto-update (#338)
         feat(availability): reorganize availability page per A-Team design (#339)
         feat(payments): migrate CardElement → PaymentElement (#337)
         [v142 commits below]
```

---

**STATUS: Dashboard Beast 41/41 COMPLETE. Registration security gap CLOSED. Email verification + invite enforcement live. 7 PR reviews received, all critical findings resolved, 44 deferred items cataloged. Founding instructor activation is THE critical path to launch. 13,206 backend + 8,303 frontend + 225 e2e tests passing. Type coverage 100%.**
