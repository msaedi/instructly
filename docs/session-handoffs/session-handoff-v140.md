# InstaInstru Session Handoff v140
*Generated: March 11, 2026*
*Previous: v139 | Current: v140 | Next: v141*

## 🎯 Session v140 Summary

**Bitmap Granularity Migration + AI Bio Generation + Stripe Security Hardening + Type Safety + Custom Skills + Production Fixes**

This session delivered a fundamental data model change (bitmap resolution 30min→5min), shipped AI-powered bio generation, achieved 100% frontend type-coverage, comprehensively hardened the Stripe integration (21+ findings), fixed a production instant payout bug, created custom Claude skills for the X-Team workflow, processed 13 dependabot PRs, hardened batch tasks against cascading failures, and resolved 20 Sentry issues.

| Objective | Status |
|-----------|--------|
| **AI Bio Generation** | ✅ GPT-5 Nano endpoint, replaces client-side shuffler |
| **100% Type Coverage** | ✅ 179,736/179,736 identifiers, hard-gated in CI + pre-push |
| **Bitmap Granularity Migration** | ✅ 5-min storage, 15-min booking, 30-min grid |
| **Stripe Audit Remediation** | ✅ 21+ findings: PCI, idempotency, refund flow, webhooks |
| **Production Instant Payout Fix** | ✅ Queries available balance instead of hardcoded 0 |
| **Custom Skills** | ✅ instainstru-verify (Claude Code) + orchestrator (Claude.ai) |
| **Batch Task Hardening** | ✅ Per-booking session rollback in 3 task files |
| **Dependency Updates** | ✅ 12 of 13 dependabot PRs merged |
| **Sentry Issue Resolution** | ✅ 20 issues resolved via redeploy + hardening |
| **FakeCheckrClient Fix** | ✅ Module-level candidate persistence |
| **PERF_LOG Documentation** | ✅ Process-restart notes on 4 search files |

---

## 🤖 AI Bio Generation (Complete)

`POST /api/v1/instructors/me/generate-bio` — real AI-generated instructor bios replacing the client-side sentence shuffler.

| Aspect | Details |
|--------|---------|
| **Model** | GPT-5 Nano with `reasoning_effort="minimal"` |
| **Rate limit** | `bio_generate` bucket: 5/min per user, burst 1 |
| **Resilience** | Semaphore(3) + circuit breaker (5 failures → 60s cooldown) |
| **Cost** | ~$0.0002 per generation |
| **Prompt** | Capped at 950 characters to fit 1000-char bio field |

**Key decision:** GPT-5 Nano is a reasoning model — with default `reasoning_effort="medium"`, it consumed all `max_completion_tokens` for chain-of-thought and returned empty output. Setting `reasoning_effort="minimal"` disables reasoning tokens, making it behave like a non-reasoning model at cheaper token pricing. Temperature parameter removed (nano only supports default 1).

**Graceful degradation:** Sparse profiles (onboarding step 1, name + experience only) produce valid generic bios. Full profiles with skills/neighborhoods get personalized output. Frontend shows "Tip: add your skills first for a more personalized bio" hint when no services exist.

Available on both instructor onboarding and dashboard profile editing.

### Key Files
```
backend/app/services/bio_generation_service.py       # BioGenerationService
backend/app/routes/v1/instructors.py                 # POST /me/generate-bio
backend/app/ratelimit/config.py                      # bio_generate bucket
backend/app/schemas/instructor.py                    # GenerateBioResponse
frontend/features/instructor-profile/InstructorProfileForm.tsx  # API call
frontend/app/(auth)/instructor/onboarding/account-setup/components/BioCard.tsx  # UI
```

---

## 🔢 100% Frontend Type Coverage (Complete)

Eliminated all 1,854 `any` identifiers across the frontend codebase.

| Phase | Scope | Identifiers Fixed |
|-------|-------|-------------------|
| Source files | 25 files | 127 |
| Top 8 test files | 8 files | 924 |
| **Total** | **33 files** | **1,051** |

**Key patterns fixed:**
- SSE callbacks typed as `MessageEvent<string>`
- Leaflet returns with generics: `L.geoJSON<GeoJSONProperties>()`
- `isUnknownArray()` utility replacing `Array.isArray()` on `unknown` inputs
- `featureProps()` helper for GeoJSON structural extraction
- `jest.requireMock` generics and mock callback types

**Enforcement:** `type-coverage --at-least 100` now hard-fails in both pre-push hooks and CI. Any new `any` introduction breaks the build.

---

## 🗺️ Bitmap Granularity Migration (Complete — PR #320)

Fundamental data model change: bitmap availability resolution from 30-minute (48 slots/day, 6 bytes) to 5-minute (288 slots/day, 36 bytes).

### Three-Tier Architecture

| Tier | Granularity | Purpose |
|------|-------------|---------|
| **Storage** | 5 minutes (288 slots, 36 bytes) | Backend bitmap, DB column |
| **Booking** | 15 minutes | Student time pickers, booking validation |
| **Editor** | 30 minutes (6 bits per cell) | Instructor availability grid |

### Backend Changes

- **Centralized constants** in `constants.py`: `MINUTES_PER_SLOT=5`, `SLOTS_PER_DAY=288`, `BYTES_PER_DAY=36`, `BOOKING_START_STEP_MINUTES=15`, `AVAILABILITY_CELL_MINUTES=30`, `BITS_PER_CELL=6`
- **`bitset.py`**: all formulas derive from constants, no hardcoded 30/48
- **`booking_service.py`**: removed `_half_hour_index`, 15-min boundary validation on create + reschedule + check-availability via shared `_check_bits_coverage` helper
- **PostgreSQL functions**: `check_availability()` + `clear_availability_bits()` updated to 5-min resolution
- **Fixed MSB→LSB bit ordering bug**: PostgreSQL functions used `7-(i%8)` (MSB) while Python/TypeScript used `i%8` (LSB) — now consistent LSB everywhere
- **Min-advance cutoff** snaps to 15-min boundaries (prevents offering 10:05, 10:20 etc.)
- **`bits_from_windows`**: midnight end time `"00:00"` now correctly maps to `SLOTS_PER_DAY` (288) instead of 0
- **DB constraint**: `CHECK(length(bits) = 36)` on `availability_days` table

### Frontend Changes

- **`bitset.ts`**: 288 slots, `toggleRange()` and `isRangeSet()` helpers for 6-bit cell operations
- **`InteractiveGrid`**: 30-min visual cells unchanged, each toggles 6 consecutive bitmap bits. Cell renders active if any bit set.
- **`TimeSelectionModal` + `RescheduleTimeSelectionModal`**: 30→15 min step
- **Extracted `expandDiscreteStarts`** utility with 15-min grid snapping (`Math.ceil(startTotal / stepMinutes) * stepMinutes`)
- **`idx()` function**: `Math.floor` added for defensive integer division
- **`toggleRange`**: optimized to single copy instead of N intermediate arrays
- **`computeBitsDelta`**: loop bound fixed from `i < 6` to `i < BYTES_PER_DAY`

### Audit Trail

| Round | Findings | Status |
|-------|----------|--------|
| Audit 1 (2 agents) | check-availability missing bitmap check, expandDiscreteStarts 5-min offset, partial cell rendering | Fixed |
| Audit 2 (2 agents) | check-availability still missing bitmap lookup (verified by invocation), `i < 6` loop bound | Fixed |
| Audit 3 (2 agents) | `Uint8Array(180)` stale test, minor naming/drift items | Fixed |
| Audit 4 (CI reviews) | `idx()` floating-point, `toggleRange` perf, midnight end time asymmetry, stale test indices | Fixed |
| Final CI reviews | LGTM from all reviewers, zero critical issues | Merged |

### Key Files
```
# Backend
backend/app/core/constants.py                         # 6 time granularity constants
backend/app/utils/bitset.py                           # 288-slot bitmap operations
backend/app/services/booking_service.py                # 15-min validation, _check_bits_coverage
backend/app/services/availability_service.py           # MINUTES_PER_SLOT cutoff + snap
backend/alembic/versions/003_availability_booking.py   # PG functions, CHECK constraint
backend/app/routes/v1/public.py                        # MINUTES_PER_SLOT import

# Frontend
frontend/lib/calendar/bitset.ts                        # 288-slot bitmap, toggleRange, isRangeSet
frontend/components/availability/InteractiveGrid.tsx    # 6-bit cell toggle
frontend/lib/time/expandDiscreteStarts.ts              # Shared utility, 15-min snap
frontend/features/student/booking/components/TimeSelectionModal.tsx      # 15-min step
frontend/components/lessons/modals/RescheduleTimeSelectionModal.tsx      # 15-min step
```

---

## 🛡️ Batch Task Hardening (Complete)

One failed DB query poisoned entire PostgreSQL sessions via `InFailedSqlTransaction`, cascading to all subsequent records in batch tasks. Root cause: stale deployment (41 commits behind per-format pricing migration) caused `UndefinedColumn` errors that cascaded to 20 Sentry issues.

**Fix:** Added `db.rollback()` in per-record except blocks to isolate failures.

| Task File | Change |
|-----------|--------|
| `video_tasks.py` | Per-booking rollback in no-show detection |
| `notification_tasks.py` | Per-booking rollback in 24h + 1h reminder loops |
| `email.py` | Per-email rollback in email task processing |

Not modified (already resilient): `payment_tasks.py` (per-session pattern), `embedding_migration.py` (internal error handling), `db_maintenance.py` (context manager auto-rollback).

4 new isolation tests verifying next record processes after previous failure.

---

## 📦 Dependency Updates (Complete)

12 of 13 dependabot PRs processed in a single batch commit. All PRs closed.

### Updated
| Package | From → To | Stack |
|---------|-----------|-------|
| stripe | 14.3.0 → 14.4.1 | Backend |
| opentelemetry-exporter-otlp-proto-http | 1.39.1 → 1.40.0 | Backend |
| opentelemetry-instrumentation-celery | 0.60b1 → 0.61b0 | Backend |
| opentelemetry-instrumentation-httpx | 0.60b1 → 0.61b0 | Backend |
| All OTEL packages (10 total) | version-aligned | Backend |
| size-limit | 12.0.0 → 12.0.1 | Frontend |
| @size-limit/file | 12.0.0 → 12.0.1 | Frontend |
| openapi-typescript | 7.10.1 → 7.13.0 | Frontend |
| @types/node | 25.3.3 → 25.4.0 | Frontend |
| botid | 1.5.10 → 1.5.11 | Frontend |
| docker/setup-buildx-action | v3 → v4 | CI |
| docker/login-action | v3 → v4 | CI |
| docker/build-push-action | v6 → v7 | CI |

### Skipped
| Package | Reason |
|---------|--------|
| redis 6.4.0 → 7.3.0 | kombu incompatible with redis>=7 |

---

## 🔧 Other Fixes

| Fix | Details |
|-----|---------|
| FakeCheckrClient persistence | Candidate storage moved from instance-level to module-level `_fake_candidate_store` |
| PERF_LOG documentation | Process-restart notes added to 4 search files |
| openapi-typescript exact pinning | CI requires exact pins, fixed `^7.13.0` → `7.13.0` |

---

## 💳 Stripe Audit Remediation (Complete — PR merged)

Comprehensive Stripe integration audit by 4 parallel agents identified 21+ findings. All remediated across multiple audit rounds with CI bot reviews.

### Critical Fixes
- **C1**: SDK manages API version — removed hardcoded pin, startup log shows SDK + API version
- **C2**: Idempotency keys on all 6 `.create()` calls (PaymentIntent ×2, Customer, Account, Payout, AccountLink)
- **C4**: Removed raw CVV input from CheckoutFlow and PaymentConfirmation (PCI violation)
- **C5**: Refund status verified from Stripe before writing — `succeeded` → `refunded`, `pending` → `refund_pending`, `failed` → `refund_failed`

### Payment Hardening
- Stale payment object refreshed from DB after Stripe refund call
- Webhook atomic claim via `mark_processing()` — prevents concurrent duplicate processing
- Orphaned refund detection logged at CRITICAL level for reconciliation
- `_call_with_retry` with exponential backoff on all money-movement create calls
- Production guard (`INSTAINSTRU_PRODUCTION_MODE`) on all mock Stripe fallback paths
- HTTP timeout 3s → 30s (Stripe recommended minimum)
- Transient webhook failures return 503 for Stripe retry; permanent return 200

### Frontend Cleanup
- Consolidated 5 scattered `loadStripe()` into shared `getStripe()` with lazy initialization
- Removed hardcoded card data (4242, 12/2025) from legacy payment UI
- Missing expiry renders as `••/••` instead of `0/0`
- Removed unused props (userId, instructorId), TEST_CARDS from production bundle
- Onboarding logging redacted (no full Stripe account IDs)

### Code Quality
- All f-string logger calls in `stripe_service.py` converted to lazy `%s` formatting
- Stripe error details preserved in refund failures (specific `StripeError` catch)
- Audit failure logs upgraded debug → warning
- New payment statuses (`refund_pending`, `refund_failed`) added to existing migration constraint
- `@validates` decorator typed via `cast()` — no config suppression

### Key Files
```
backend/app/services/stripe_service.py          # Idempotency, retry, version, production guards
backend/app/services/refund_service.py           # Refund status mapping, stale object refresh
backend/app/routes/v1/payments.py                # Webhook atomic claim, transient 503
backend/app/services/admin_booking_service.py    # Orphaned refund logging, audit log levels
frontend/components/booking/CheckoutFlow.tsx      # CVV removed, getStripe consolidated
frontend/features/student/payment/utils/stripe.ts # Shared getStripe(), no placeholder fallback
```

---

## 💰 Production Instant Payout Fix (Complete)

`POST /api/v1/payments/instant-payout` was hardcoding `amount_cents=0`, which Stripe rejected (`amount >= 1` required). This caused 6 Sentry issues (4B–4G).

**Fix:** Removed `amount_cents` parameter from route. Service now queries connected account's available balance via `stripe.Balance.retrieve()`, then pays out that amount. Zero-balance guard returns clear error instead of Stripe rejection.

### Key Files
```
backend/app/services/stripe_service.py    # Balance.retrieve(), zero-balance guard
backend/app/routes/v1/payments.py          # Removed amount_cents=0
```

---

## 🛠️ Custom Skills (Complete)

Created two custom skills for the X-Team workflow:

### instainstru-verify (Claude Code skill)
Installed at `.claude/skills/instainstru-verify/`. Auto-discovered by Claude Code, appears in available skills list.

| Component | Purpose |
|-----------|---------|
| `SKILL.md` | Core instructions: run verify.sh, self-check protocol, reporting format |
| `scripts/verify.sh` | Deterministic verification — runs all checks, structured pass/fail report |
| `references/troubleshooting.md` | How to fix specific failures (mypy, type-coverage, pre-commit) |
| `references/conventions.md` | Project coding rules, forbidden patterns, config-level suppression ban |

Key feature: **Config-level suppression ban** — adding `disallow_untyped_decorators = false` in pyproject.toml is treated the same as inline `# type: ignore`. Learned from a real incident where Claude Code added a mypy override instead of fixing the code.

### instainstru-orchestrator (Claude.ai project skill)
Codifies the X-Team workflow: coding agent prompt templates, audit loop protocol, commit message format, PR creation, session handoff structure, decision patterns.

---

## 📊 Platform Health (Post-v140)

| Metric | Value | Change from v139 |
|--------|-------|-------------------|
| **Backend Tests** | 12,935+ | +118 |
| **Frontend Tests** | 8,217+ | -127 (test consolidation) |
| **Backend Coverage** | 99%+ | Maintained |
| **Frontend Coverage** | 97%+ | Maintained |
| **Frontend Type Coverage** | 100% | NEW — hard-gated |
| **API Endpoints** | 370+ | +1 (generate-bio) |
| **Sentry Issues Resolved** | 20 | Stale deployment cascade |
| **Dependabot PRs Processed** | 13 (12 merged, 1 skipped) | — |
| **Bitmap Resolution** | 288 slots/day (5-min) | Was 48 (30-min) |

---

## 🏛️ Architecture Decisions

### New ADRs from this session:

- **Three-Tier Time Granularity** — Storage precision (5 min) ≠ booking step (15 min) ≠ editor cell size (30 min). These are independent constants. The instructor availability editor can change from 30-min to 15-min cells in the future with zero backend changes — just a frontend constant swap (each cell becomes 3 bits instead of 6).

- **GPT-5 Nano with `reasoning_effort="minimal"` for Creative Generation** — Reasoning models consume `max_completion_tokens` for hidden chain-of-thought before producing visible output. For creative tasks (bio writing) where reasoning adds no value, set `reasoning_effort="minimal"` to disable reasoning tokens entirely. This makes nano behave like a non-reasoning model at cheaper pricing than gpt-4o-mini.

- **Hard-Gated Type Coverage at 100%** — `type-coverage --at-least 100` enforced in both CI and pre-push hooks. Any new `any` introduction fails the build. Source of truth is the TypeScript compiler + type-coverage tool, not developer discipline.

- **Per-Record Session Rollback in Batch Tasks** — When iterating over DB records in Celery tasks, `db.rollback()` in the except block before `continue` prevents one failed query from poisoning the session for all remaining records. This is a systemic pattern, not per-task.

- **LSB Bit Ordering Convention** — All bitmap operations (Python `bitset.py`, TypeScript `bitset.ts`, PostgreSQL functions) use LSB-first ordering: `bit_index = slot % 8`, bit set via `1 << bit_index`. The MSB convention (`7 - (slot % 8)`) that existed in PostgreSQL was a bug, now fixed.

- **Midnight End Time Convention** — `"00:00"` as an end time means end-of-day (slot 288), not start-of-day (slot 0). Both backend `bits_from_windows` and frontend `fromWindows` handle this with an `is_end` / `isEndTime` parameter.

- **SDK-Managed Stripe API Version** — Do not hardcode Stripe API version strings. The stripe-python SDK pins its own version and sends it on every call. Pinning in config creates a maintenance burden (must update on every SDK upgrade). Instead, log the SDK version at startup for production verification.

- **Refund Status from Stripe** — Never blindly write `"refunded"` after `Refund.create()`. Check `refund.status` first: `succeeded` → `refunded`, `pending` → `refund_pending`, `failed` → `refund_failed`. Refresh the payment object from DB after the Stripe call to prevent stale-object overwrites.

- **Webhook Atomic Claim** — Use `mark_processing()` with atomic SQL `UPDATE ... WHERE status IN ('received', 'failed') RETURNING id` to claim webhook events before processing. Simple `status == "processed"` checks allow race conditions on concurrent duplicate deliveries.

- **Config-Level Suppression Ban** — Adding `disallow_untyped_decorators = false` in `pyproject.toml` is equivalent to inline `# type: ignore` — both suppress errors instead of fixing them. The only acceptable response to a failing check is to fix the code. Codified in the `instainstru-verify` skill.

---

## 📋 Remaining Work

All items from this session are resolved. No carryover.

### Follow-up items (non-blocking, from CI reviews):

| Item | Priority | Notes |
|------|----------|-------|
| C3: CardElement → PaymentElement migration | Medium | Unlocks Apple Pay/Google Pay. Separate session. |
| `VerificationSession.create` idempotency key | Low | Out of scope for Stripe PR, not money-movement. |
| `_check_bits_coverage` DI pattern | Low | `getattr` fallback works but bypasses DI. |
| Frontend/backend constant sync enforcement | Low | Constants duplicated across stacks. |
| `TimeSelectionModal` / `RescheduleTimeSelectionModal` import from bitset.ts | Low | Both define local `SLOT_STEP_MINUTES = 15`. |
| `InteractiveGrid` `isSlotBooked` param rename | Low | Named `slotIndex` but receives a row index. |

---

## 🔑 CLAUDE.md Correction

Updated bitmap description from incorrect "1440-bit per day" to:

> **Bitmap Availability**: 288-bit per day at 5-min resolution (36 bytes BYTEA). Instructor editor displays 30-min cells, students book in 15-min increments.

---

*Session v140 — Bitmap Migration + AI Bio + Stripe Hardening + Type Safety + Custom Skills: 8 features, 10+ audit rounds, 65+ files, 21,152+ tests passing* 🎉

**STATUS: Bitmap granularity migrated to 5-min resolution. AI bio generation live. Stripe integration comprehensively hardened (21+ findings). 100% type coverage enforced. Custom skills operational. Platform hardened against cascading task failures. Production instant payout bug fixed. All dependency updates processed.**
