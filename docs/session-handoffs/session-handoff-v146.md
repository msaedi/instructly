# InstaInstru Session Handoff v146
*Generated: April 4, 2026*
*Previous: v145 | Current: v146 | Next: v147*

## Session v146 Summary

**Feature completion, architectural hardening, and pre-existing issues sweep.**

Completed all A-Team UI packages (23 dashboard items + 20 test log bugs), implemented 5 pre-existing issues packages (A through E) plus a final 12-item cleanup sweep, built persistent Celery task execution history, handled a supply chain security incident, and cleared the entire backlog of user-facing bugs.

| Objective | Status |
|-----------|--------|
| **All A-Team dashboard + test log items** | ✅ 43/43 items resolved |
| **Pre-existing issues sweep** | ✅ 5 packages (A-E) + final cleanup |
| **TaskExecution persistent history** | ✅ Signal-based, OTEL-correlated |
| **Security incident (axios compromise)** | ✅ Credentials rotated, SHA pinned |
| **Pre-existing issues tracker** | 68 open → ~0 actionable |
| **Backend coverage** | 98.27% (13,526+ tests) |
| **Frontend coverage** | 100% type coverage (8,446 tests, 427 suites) |
| **MCP coverage** | 100% (421+ tests) |

---

## Key Decisions

### PAYMENT_FAILED Booking Status
New terminal status for bookings where payment authorization never succeeded. `confirmed_at` stays NULL. No cancellation emails, no chat messages, no instructor notification. Instructor queries exclude; student queries include in history. Modified existing migration 003.

### Video Join Window = Full Session
Removed the late-join cutoff entirely. Users can join from 5 minutes before start until `booking_end_utc`. No per-user tracking needed — simplified from the original "track returning users" approach. Frontend shows "Session ends in..." instead of "Window closes in..."

### No-Show Lifecycle — Immediate Transition
Both automated AND manual no-show paths now transition booking immediately to NO_SHOW status. Previously, manual reports left booking as CONFIRMED with a no-show record — creating a stuck state. Cancelled no-show resolution restores to CONFIRMED.

### State Machine Enforcement
Zero runtime `booking.status =` writes outside the Booking model. Every transition goes through `mark_*()` helpers which enforce `_ALLOWED_TRANSITIONS`. Admin transitions explicitly listed and commented. `atomic_confirm_if_pending` uses `mark_confirmed()` instead of raw SQL UPDATE. Tests and factories may still set status directly for setup.

### Booking State Transitions (Complete Map)
```
PENDING → CONFIRMED, COMPLETED, CANCELLED, PAYMENT_FAILED
CONFIRMED → COMPLETED, CANCELLED, NO_SHOW
COMPLETED → CANCELLED (admin refund), NO_SHOW (admin correction)
NO_SHOW → CONFIRMED (dispute cancelled), COMPLETED (dispute upheld), CANCELLED
CANCELLED → (terminal)
PAYMENT_FAILED → (terminal)
```

### Reminder Timezone
"Tomorrow" computed in lesson-local time using 50h UTC candidate window + local-date filter. Fallback chain: `lesson_timezone` → `instructor_tz_at_booking` → platform default. Fixes the bug where NYC bookings got reminders a day early.

### Next Availability — Earliest Across All Formats
When no format filter is selected, the search card shows the earliest available time across ALL formats the instructor offers (online=60min < studio=60min < travel=180min advance notice). Shows format label: "Next: 12:30 PM · Online".

### Map Click-to-Scroll
Clicking a service area polygon scrolls the instructor list to the first instructor covering that area. Clicking again cycles to the next instructor. All instructors' areas remain visible; existing hover highlight behavior unchanged.

### TaskExecution — Persistent Celery History
Signal-based recording via `task_prerun`/`task_postrun`/`task_failure`/`task_retry`. Universal coverage (not BaseTask-dependent). OTEL `trace_id` captured for Sentry/Axiom correlation. Status enum: STARTED, SUCCESS, FAILURE, RETRY. 90-day retention with daily purge (4 AM Eastern). ~5,400 executions/day estimated. 2 new MCP tools: `instainstru_celery_task_history_persistent` + `instainstru_celery_task_stats` (p50/p95 duration, success rate).

### Size Budget Enforcement
New pre-commit hook `check_size_budgets.py` with baseline allowlist. Warn at 500 lines/file or 100 lines/method. Hard-fail at 700/125. Existing large files are baselined — only new violations fail. Ratchet-down approach: remove files from baseline as they're fixed.

### Type Safety Protocols
Eliminated `Any` from lazy import helpers and cross-module contracts:
- `StripeServiceModuleProtocol` (11 helpers)
- `InstructorServiceModuleProtocol` (8 attributes)
- `PaymentTasksFacadeApi` fully typed (13 attributes, only `stripe: Any` remains)
- `SearchServiceLike` fully typed (7 collaborators)
- Stub-drift enforcement test (AST-based signature comparison)

---

## Security Incident — Axios NPM Compromise (March 31, 2026)

GitHub notified that compromised axios versions (1.14.1, 0.30.4) executed in CI and communicated with attacker C2 server. Axios was pulled in by `codecov/codecov-action@v6`, not a direct dependency.

**Blast radius (limited to CI):**
- `CODECOV_TOKEN` — rotated
- `BGC_ENCRYPTION_KEY` — rotated
- `RESEND_API_KEY` — not exposed (fallback to test value in CI)
- `E2E_*_PASSWORD` — hardcoded in source, zero additional exposure
- All production secrets (DB URLs, Stripe, Twilio, etc.) — NOT in GitHub Actions, only on Render

**Hardening:** `codecov/codecov-action` pinned to commit SHA `57e3a136b779b570ffcdbf80b3bdc90e7fab3de2` instead of mutable `@v6` tag.

---

## New Seed Data

Two new piano instructors added for search/map testing:
- **Emily Park** — Piano, $90 online / $120 travel. Areas: East Midtown-Turtle Bay (overlaps Sarah), Morningside Heights, Harlem. 8 completed lessons, 4.5 rating.
- **James Williams** — Piano, $100 online / $110 studio / $140 travel. Areas: Upper West Side Central (overlaps Sarah), West Village, Greenwich Village. Teaching location: 45 W 21st St. 15 completed lessons, 4.8 rating.

Teaching locations added for all `instructor_location` instructors. Seed script is `prep_db.py --seed-all` via `reset_and_seed_yaml.py` + YAML files.

---

## MCP Server Changes

404 normalization across all 18 backend-backed tool modules:
- Read tools: `{"found": false, "error": "instructor_not_found", ...}`
- Write tools: `{"success": false, "error": "booking_not_found", ...}`
- Domain-specific error codes per resource type
- Raw client still raises (unchanged) — normalization is tool-layer only

2 new tools for task execution history:
- `instainstru_celery_task_history_persistent`
- `instainstru_celery_task_stats`

---

## Platform Health (End of Session)

| Metric | Value | Change |
|--------|-------|--------|
| Backend Tests | 13,527+ | +160 |
| Backend Coverage | 98.27% | +0.30% |
| Frontend Tests | 8,446 | +24 |
| Frontend Suites | 427 | +0 |
| Frontend Type Coverage | 100% | Maintained |
| MCP Tests | 421+ | +2 |
| MCP Coverage | 100% | Maintained |
| E2E Tests | 225 passing | Maintained |
| Pre-existing Issues | ~0 actionable | Was: 68 open |
| Pre-existing Fixed | 60+ | Was: 5 |

---

### Final Pre-Existing Issues Cleanup (12 items) ✅
Direct to main. All low-risk nits:
1. Duplicate TYPE_CHECKING blocks removed from notification mixins (centralized in mixin_base)
2. Keyword-only `*` restored on `build_instructor_response`
3. Stripe API key lazy init (was set at import time)
4. Redundant double import in preflight.py removed
5. `_validate_go_live_prerequisites` — removed unused context dict mutation
6. `PRICE_FLOOR_CONFIG_KEYS` → model constants instead of string literals
7. `self.db.expire_all()` → repository seam
8. Clock skew buffer (5s) added to `detect_video_no_shows`
9. Edge-case test for shortened booking (`booking_end_utc` < start + duration)
10. `pre_data.skip_vector` — documenting comment (mutation safe due to ordering)
11. Two flaky tests stabilized (performance overhead + bulk operation)
12. `PaymentTasksFacadeApi` method params — confirmed already clean

## Remaining Work

### Frontend Decomposition (P3)
- `PaymentConfirmation.tsx` (2,539 lines)
- `search/page.tsx` (2,274 lines)
- `student/dashboard/page.tsx` (2,097 lines)

### Backend Remaining Large Files (P3)
- `payment_repository.py` (1,679)
- `instructor_profile_repository.py` (1,582)
- `config.py` (1,484)
- `main.py` (1,467)

### Blocked / External Dependencies
- redis-py 7.4.0 upgrade — blocked by Kombu `<6.5` cap
- TypeScript 6.0 upgrade — wait for ecosystem
- NL search #3: No direct unit tests for 13 pipeline modules (low priority, pure functions)
- NL search #8: Postflight layers naming unclear (cosmetic)
- Availability #1: availability_service_module() bridge weak typing (same pattern as booking, acceptable)
- Availability #3: async/sync mismatch on save_week_availability (low risk)

### Infrastructure (Go-Live Day)
- Supabase Pro + PITR ($140/month)
- `app_user` role switch

### Business (Non-Engineering)
- Founding instructor activation codes (Instantly campaign)
- Nina's LinkedIn authority sequence (9-post calendar)
- SEO programmatic pages
- PRD completion (Parts 2, 3, 5, 6, 7, 8, 9)
