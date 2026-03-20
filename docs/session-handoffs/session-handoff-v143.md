# InstaInstru Session Handoff v143
*Generated: March 20, 2026*
*Previous: v142 | Current: v143 | Next: v144*

## 🎯 Session v143 Summary

**Stripe PaymentElement Migration + A-Team Dashboard Beast (2 of 41 items) + Commission Tier Auto-Update System**

This session delivered three major PRs: a full Stripe CardElement → PaymentElement migration unlocking Apple Pay/Google Pay/Link, the first two items from the A-Team's 41-item Dashboard Beast backlog (availability page redesign and commission tier display), and a complete tier auto-evaluation system with Celery beat scheduling. The A-Team Dashboard Beast document was received and triaged with effort estimates for all 41 items.

| Objective | Status |
|-----------|--------|
| **Stripe CardElement → PaymentElement Migration** | ✅ PR #337 merged |
| **Apple Pay / Google Pay / Link** | ✅ Enabled via PaymentElement — Apple Pay confirmed on Safari |
| **Availability Page Redesign (A-Team #33)** | ✅ PR #339 merged |
| **Commission Tier Display (A-Team #39)** | ✅ PR #338 merged |
| **Commission Tier Auto-Update on Booking Completion** | ✅ Included in PR #338 |
| **Nightly Tier Evaluation Celery Task** | ✅ Included in PR #338 |
| **A-Team Dashboard Beast Triage** | ✅ 41 items estimated and batched |

---

## 💳 Stripe CardElement → PaymentElement Migration (PR #337)

### Problem Solved

CardElement only supports manual card entry. PaymentElement supports all Stripe payment methods via a single component — Apple Pay, Google Pay, Link (one-click checkout), and future methods. This was the last prerequisite for wallet-based payments.

### Backend Changes

- New `POST /api/v1/payments/setup-intent` — creates SetupIntent for saving payment methods
- `automatic_payment_methods: { enabled: True, allow_redirects: "never" }` on ALL 4 intent creation paths (PaymentIntent ×2, SetupIntent ×2)
- `_advance_booking_on_capture` webhook handler — confirms booking on `requires_capture` status, atomic `UPDATE WHERE status=PENDING`
- `setup_future_usage='off_session'` always set for PaymentElement flow
- `_check_stripe_configured()` guard on `create_setup_intent_for_saving`
- `except HTTPException: raise` added to setup-intent route
- `_call_with_retry` on all Stripe API calls including SetupIntent

### Frontend Changes

- `PaymentMethods` + `PaymentMethodSelection`: SetupIntent + PaymentElement + `confirmSetup`
- `CheckoutFlow`: saved cards unchanged, new cards use PaymentElement + `confirmPayment`
- Tip + saved card 3DS: `confirmCardPayment` → `confirmPayment`
- `saveCard` checkbox removed (always saves, users manage from billing)
- PI cached across tab toggles (`hasFetchedIntentRef` + reset on error)
- Null Stripe in 3DS throws error instead of silent failure
- Consolidated 5 `loadStripe()` into shared `getStripe()` with lazy initialization
- Tip payment: don't navigate on tip failure (retry enabled)

### Zero Legacy Patterns

- 0 CardElement references
- 0 `confirmCardPayment` calls
- 0 `confirmCardSetup` calls
- 0 `payment_method_types` arrays (all use `automatic_payment_methods`)

### Apple Pay / Google Pay

- Apple Pay: shows automatically on Safari/iOS via PaymentElement
- Google Pay: requires card saved in Google Wallet to appear
- Domain registration: `instainstru.com`, `www.instainstru.com`, `beta.instainstru.com`, `preview.instainstru.com` — all registered
- Samsung Pay: blocked by `allow_redirects: "never"` (correct for Connect + manual capture)

### Rate Limit Decision

`/setup-intent` uses `rate_limit("write")` not `"financial"` — SetupIntent is preparatory (no money moves), and React StrictMode double-mount would hit financial bucket's 0 burst.

### Key Files

```
# Backend
backend/app/routes/v1/payments.py                    # setup-intent endpoint, webhook handler
backend/app/services/stripe_service.py               # create_setup_intent_for_saving, _advance_booking_on_capture
backend/app/schemas/payment_schemas.py               # SetupIntentResponse

# Frontend
frontend/components/booking/CheckoutFlow.tsx          # PaymentElement for new cards
frontend/features/student/payment/components/PaymentMethods.tsx    # PaymentElement for card saving
frontend/features/student/payment/components/PaymentMethodSelection.tsx  # PaymentElement in selection flow
frontend/features/shared/payment/utils/stripe.ts      # Shared getStripe()
frontend/app/(auth)/student/review/[id]/page.tsx      # Tip payment fix
```

---

## 📅 Availability Page Redesign — A-Team #33 (PR #339)

### Changes

Per A-Team reference sketch, reorganized the entire availability page layout:

- **Controls moved above calendar**: Today/Repeat/Apply + Teaching window controls row sits directly below month navigation
- **Compact format pills**: Replace verbose radio buttons with inline `All` (purple) · `Online` (blue) · `No Travel` (green) pills
- **Removed**: Tip section, format tags legend, "Business Hours" subtitle, verbose settings explanation
- **Side-by-side buffer cards**: "Staying put" and "Traveling to student" in horizontal grid instead of stacked
- **New copy**: Detailed buffer explanations per A-Team spec with NYC-specific guidance
- **Compact dropdown labels**: "15 minutes" → "15 min"
- **Simplified overnight protection**: 2 concise lines
- **Footer**: "About calendar protections" link + "Last updated" timestamp

### Buffer Minimum Changes

- Non-travel buffer minimum: 0 → **10 minutes** (FE + BE)
- Travel buffer minimum: 15 → **30 minutes** (FE + BE)

### Key Files

```
frontend/app/(auth)/instructor/availability/page.tsx           # Full page reorganization
frontend/components/availability/CalendarSettingsSection.tsx    # Side-by-side buffers, new copy
```

---

## 📊 Commission Tier Display — A-Team #39 (PR #338)

### What Was Built

Complete commission tier visibility system: new API endpoint, auto-updating tier on booking completion, nightly Celery sweep, and a frontend card matching the A-Team sketch exactly.

### Backend — New Endpoint

`GET /api/v1/instructors/me/commission-status` — instructor-only, rate-limited.

Returns: `tier_name`, `commission_rate_pct`, `completed_lessons_30d` (real DB count), `activity_window_days`, tier ladder with `is_current`/`is_unlocked` flags, next-tier progress.

Tier rates and thresholds read from `platform_config` (admin-configurable) — not hardcoded. `activity_window_days` configurable via `tier_activity_window_days` in pricing config.

### Backend — Tier Auto-Update

**Problem found during implementation:** `current_tier_pct` on instructor profiles was NEVER updated automatically. It was set during seeding and only changed by manual admin actions. The tier calculation `_resolve_instructor_tier_pct()` computed correct rates at pricing time but never persisted the result.

**Fix:**
- `_maybe_refresh_instructor_tier()` called at end of both `complete_booking()` and `instructor_mark_complete()` — wrapped in try/except so failures don't break booking completion
- Tier refresh also wired into `_auto_complete_booking()` in payment tasks
- Daily Celery beat task at **3:15am** evaluates all active non-founding instructors
- Founding instructors excluded from sweep query (`is_founding_instructor.is_(False)`)
- Per-instructor error handling in batch (one failure doesn't stop sweep)
- Respects `tier_stepdown_max` (max 1 tier drop per eval) and `tier_inactivity_reset_days` (90 days → Entry)

### Backend — Bulk Query Optimization

`evaluate_active_instructor_tiers` uses `get_instructor_completion_stats_in_window()` — single grouped query returning `{instructor_id: (count, last_completed_at)}` for all instructors. Eliminates 2N queries.

### Frontend — CommissionTierCard

Two completely different views based on `is_founding`:

**Founding Instructor View:**
- Star icon + "Founding Instructor" title
- Purple "8% · locked" badge
- "You have locked in our lowest rate—permanently. Whatever the floor is, you're on it."
- Divider + availability commitment text

**Standard Instructor View:**
- Title: "{Tier} tier · {rate}%"
- Subtitle: "{X} of {Y} lessons completed · in the last {window} days"
- Top-right rate badge (lavender for Entry/Growth, green for Pro)
- Vertical three-tier ladder:
  - Entry: NEVER shows a progress bar
  - Current tier: checkmark + full bar (if not Entry)
  - Next tier: partial bar with "X of Y · Z more to unlock"
  - Higher tiers: dimmed, no bar

### Seed Data Fixes

**Critical bug found:** `seed_tier_maintenance_sessions()` was creating booking rows but not committing the transaction — rows were silently dropped when the session closed. Fixed by adding explicit `session.commit()`.

- Sarah Chen: Pro (10%, 14 real completed bookings)
- Jason Park: Growth (12%, 7 real completed bookings)
- Emily Carter: Entry (15%, 3 real completed bookings)

### Rename: `count_instructor_completed_last_30d` → `count_instructor_completed_in_window`

Method now accepts `window_days` parameter and reads from `tier_activity_window_days` config. Old name was misleading.

### Shared Helpers

- `_founding_rate_pct()` — extracted from duplicated triple-nested `.get()` chains
- `TierEvaluationResults` TypedDict moved to `pricing_service.py` (source of truth), imported by `payment_tasks.py`

### Key Files

```
# Backend — Endpoint + Service
backend/app/routes/v1/instructors.py                           # GET /me/commission-status
backend/app/schemas/instructor.py                              # CommissionStatusResponse, TierInfo
backend/app/services/pricing_service.py                        # get_commission_status, evaluate methods, _founding_rate_pct

# Backend — Auto-Update
backend/app/services/booking_service.py                        # _maybe_refresh_instructor_tier in both complete paths
backend/app/tasks/payment_tasks.py                             # Tier refresh in auto-complete, nightly Celery task
backend/app/tasks/beat_schedule.py                             # 3:15am tier evaluation

# Backend — Repository
backend/app/repositories/booking_repository.py                 # count_instructor_completed_in_window, bulk stats
backend/app/repositories/instructor_profile_repository.py      # list_active_for_tier_evaluation (excludes founding)

# Frontend
frontend/components/earnings/CommissionTierCard.tsx             # Self-fetching component
frontend/hooks/queries/useCommissionStatus.ts                   # React Query hook (delegates to service layer)
frontend/app/(auth)/instructor/earnings/page.tsx                # Mounted above stat cards

# Seed
backend/scripts/seed_data/instructors.yaml                     # Tier targets
backend/scripts/reset_and_seed_yaml.py                         # Commit fix, tier-maintenance bookings
```

### Review Rounds

10+ review rounds across local audits, CI bots (Claude, Codex), and manual verification. All critical and high findings resolved. Key findings addressed:
- ValueError → print seed regression reverted
- Duplicate React Query hook deduplicated
- Hardcoded 30-day window made configurable
- Celery schedule collision offset to 3:15am
- Founding instructors excluded from nightly sweep
- N+1 queries eliminated with bulk stats query
- Auto-complete path wired for tier refresh

---

## 📋 A-Team Dashboard Beast — Triage Complete

Received 41-item backlog from A-Team. All items estimated and batched:

| Batch | Items | Effort | Description |
|-------|-------|--------|-------------|
| Quick wins | #1,3,5,6,7,10,12,14,15,17,19,20,21,22,23,27,28,29,36,37 | ~3 hr | Icon swaps, label fixes, badge colors, empty states |
| Account settings | #8,9,13,16 | ~4 hr | Split name, ZIP auto-fill, 2FA toggle, merge security |
| Referral cleanup | #2,3,4,11 | ~4 hr | Remove founding modal, fix broken link, relocate section |
| Bookings redesign | #24,25,26,5 | ~5 hr | Card redesign, detail page, public profile gate |
| Large redesigns | #32,34,35,38,40,41 | ~30 hr | Referrals, Reviews, Messages, Nav, Phone onboarding, Notifications |
| **Done** | **#33, #39** | **—** | **Availability redesign, Commission tier** |

### Business Decisions Needed

- **#32:** Student referral payout for instructor referrers → $20 cash via Stripe Transfer?
- **#33 Row 7:** Advance notice configurable for instructors? (Currently platform-dictated: 60/180 min)

---

## 🏛️ Architecture Decisions

### New ADRs from this session:

- **PaymentElement over CardElement** — `automatic_payment_methods` with `allow_redirects: "never"` replaces explicit `payment_method_types`. Unlocks Apple Pay, Google Pay, Link without code changes when enabled in Dashboard.

- **`allow_redirects: "never"` for Connect + manual capture** — Redirect-based payment methods (Samsung Pay, Bancontact, etc.) are incompatible with our destination charges + manual capture flow. Stripe silently falls back to non-redirect methods.

- **SetupIntent rate limit as "write" not "financial"** — SetupIntent is preparatory (no money moves). React StrictMode double-mount in development would hit `financial` bucket's 0 burst, breaking the card-save flow.

- **`_advance_booking_on_capture` webhook handler** — For PaymentElement, booking confirmation happens asynchronously after payment succeeds. Atomic `UPDATE WHERE status=PENDING` prevents race conditions on webhook replay.

- **Tier auto-update on booking completion** — `current_tier_pct` was never updated automatically. Now persisted at both manual completion paths and auto-complete. Nightly sweep at 3:15am as safety net for edge cases (inactivity reset, missed completions).

- **Bulk completion stats query** — Nightly tier sweep uses single grouped query for all instructor completion counts, eliminating 2N individual queries.

- **Configurable activity window** — `tier_activity_window_days` flows from `platform_config` through repository to display. Method renamed from `_last_30d` to `_in_window` to match.

- **Entry tier never shows progress bar** — Entry is the starting tier, not an achievement. Progress bars only appear on tiers you've reached or are working toward.

---

## 📊 Platform Health (Post-v143)

| Metric | Value | Change from v142 |
|--------|-------|-------------------|
| **Backend Tests** | 13,200+ | +34 |
| **Frontend Tests** | 8,260+ | +15 |
| **Backend Coverage** | 98%+ | Maintained |
| **Frontend Coverage** | 97%+ | Maintained |
| **Frontend Type Coverage** | 100% | Maintained |
| **API Endpoints** | 374+ | +2 (setup-intent, commission-status) |
| **PRs Merged** | 3 (#337, #338, #339) | — |
| **Celery Beat Tasks** | 28+ | +1 (evaluate-instructor-tiers) |
| **Payment Methods** | Card + Apple Pay + Google Pay + Link | Was: Card only |
| **A-Team Items Done** | 2/41 | New backlog |

---

## 📋 Remaining Work

### Product/Feature — A-Team Dashboard Beast

| Batch | Items | Priority | Notes |
|-------|-------|----------|-------|
| Quick wins | #1,3,5,6,7,10,12,14,15,17,19,20,21,22,23,27,28,29,36,37 | **Next** | ~3 hr, ship 20 items in one PR |
| Account settings | #8,9,13,16 | High | ~4 hr, single page context |
| Referral cleanup | #2,3,4,11 | High | ~4 hr, needs business decisions |
| Bookings redesign | #24,25,26,5 | High | ~5 hr, most-used daily page |
| Large redesigns | #32,34,35,38,40,41 | Medium | ~30 hr total, separate sessions |

### Product/Feature — Other

| Item | Priority | Notes |
|------|----------|-------|
| Founding instructor activation sequence | **High** | ~102 recruited, codes not all distributed |
| Student acquisition launch | **High** | Post founding instructor activation |
| SEO programmatic pages | Medium | 7 categories × 77 subcategories × 224 services × neighborhoods |
| LinkedIn authority sequence (Nina) | Medium | Forbes pipeline |
| Instagram content runway | Medium | |
| AWS Activate application | Low | Defer until full platform live |

---

## 🔑 Git History (main, post-v143)

```
HEAD     fix(earnings): address PR review findings on commission tier
         feat(earnings): commission tier display with auto-update (#338)
         feat(availability): reorganize availability page per A-Team design (#339)
         feat(payments): migrate CardElement → PaymentElement (#337)
         [v142 commits below]
```

---

*Session v143 — PaymentElement Migration + Dashboard Beast #33 + #39: 3 PRs merged, Apple Pay unlocked, tier auto-update system, 41-item backlog triaged. 13,200+ backend + 8,260+ frontend tests passing.* 🎉

**STATUS: PaymentElement live with Apple Pay confirmed. Commission tiers auto-update on booking completion + nightly sweep. A-Team Dashboard Beast 2/41 complete — quick wins batch (~20 items) recommended next.**
