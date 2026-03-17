# InstaInstru Session Handoff v141
*Generated: March 14, 2026*
*Previous: v140 | Current: v141 | Next: v142*

## 🎯 Session v141 Summary

**Calendar Beast — Complete Implementation (Phase 1 + Phase 2)**

This session delivered the full Calendar Beast feature: format-aware booking rules with travel buffers, advance notice, overnight protection (Phase 1), and per-block format tagging with a paint-mode instructor UI (Phase 2). The feature was built across 10 implementation phases, 3 independent audit rounds, 4 CI review rounds, and a comprehensive pre-existing cleanup pass. The branch shipped as a single squash-merged PR (#322).

| Objective | Status |
|-----------|--------|
| **Phase 1A: Data Model + Platform Config** | ✅ Buffer columns, booking_rules config, calendar-settings endpoints |
| **Phase 1B: Format-Aware Buffers + Advance Notice** | ✅ Travel/non-travel buffers, instructor + student self-conflicts |
| **Phase 1C: Overnight Booking Protection** | ✅ 9am/11am cutoffs, instructor opt-out toggle |
| **Phase 1D+1E: Public Slot Generation + Search** | ✅ Buffer-aware windows, tag-aware search second-pass |
| **Phase 1F: Availability Page Settings UI** | ✅ Buffer dropdowns, overnight toggle, first-save popup |
| **Phase 1G: Booking Flow Format Propagation** | ✅ Format picker, location_type in all query keys |
| **Phase 2A: Format Tags Data Model + Bitmap-Native API** | ✅ 2-bit encoding, base64 wire format, ETag on both bitmaps |
| **Phase 2B: Tag-Based Filtering** | ✅ Booking validation, public availability, search pipeline |
| **Phase 2C: Frontend Tagging UI** | ✅ Paint-mode toolbar, visual tag indicators, mixed-format detection |
| **Audit Round 1** | ✅ Copy/apply tags, bidirectional buffers, capability parity |
| **Audit Round 2** | ✅ Reschedule fund-lock, service-area, midnight check |
| **Audit Round 3** | ✅ Stale tag invariant, ORM drift, ETag after normalization |
| **CI Review Fixes** | ✅ N+1 config, advisory locks, PENDING conflicts, DI cleanup |
| **Pre-Existing Cleanup** | ✅ 11 calendar-adjacent issues fixed |
| **pyjwt CVE-2026-32597** | ✅ Upgraded 2.11.0 → 2.12.0 |
| **npm audit** | ✅ @size-limit/preset-app moved to devDependencies |

---

## 📊 Branch Statistics

| Metric | Value |
|--------|-------|
| **PR** | #322 |
| **Branch** | `feat/calendar-beast` |
| **Additions** | ~14,000 |
| **Deletions** | ~5,000 |
| **Backend Tests** | 13,137 passed, 54 skipped |
| **Frontend Tests** | 8,245 passed, 385 suites |
| **Frontend Type Coverage** | 100% |
| **npm audit** | 0 vulnerabilities |
| **Audit Rounds** | 3 (independent agents) |
| **CI Review Rounds** | 4 (Claude bot + Codex) |
| **Implementation Phases** | 10 |
| **Commits before squash** | 15+ |

---

## 🏗️ Phase 1 — Format-Aware Booking Rules

### Phase 1A: Data Model + Platform Config

New instructor profile columns: `non_travel_buffer_minutes` (default 15), `travel_buffer_minutes` (default 60), `overnight_protection_enabled` (default true), `calendar_settings_acknowledged_at`.

Deleted `buffer_time_minutes` and `min_advance_booking_hours` — replaced by format-aware fields and platform-dictated `booking_rules` config.

Platform config seeded with: `advance_notice_online_minutes=60`, `advance_notice_studio_minutes=60`, `advance_notice_travel_minutes=180`, overnight window 8pm-8am, earliest hours 9am (online/studio) / 11am (travel).

New endpoints:
- `PATCH /api/v1/instructors/me/calendar-settings`
- `POST /api/v1/instructors/me/calendar-settings/acknowledge`

### Phase 1B: Format-Aware Buffers + Advance Notice

Centralized format classification:
- **Instructor travel formats:** `{student_location, neutral_location}`
- **Student travel formats:** `{instructor_location, neutral_location}`
- **Non-travel:** `{online, instructor_location}` (instructor perspective)

Buffer rule: if either adjacent booking involves a travel format → travel buffer. Applied to the EARLIER booking's end: `B.start >= A.end + buffer`.

Advance notice platform-dictated (not instructor-configurable): online 60min, studio 60min, travel 180min. `neutral_location` uses travel rules.

`location_type` made required on `check-availability`. Optional on public availability (defaults to conservative travel).

### Phase 1C: Overnight Booking Protection

Students booking between 8pm-8am cannot book:
- Online/studio lessons before 9am
- Travel lessons before 11am

Instructor opt-out via calendar-settings toggle. All thresholds from `booking_rules` config. Enforcement in instructor local timezone across booking creation, check_availability, and public availability. Toggle takes effect immediately — no cache delay.

### Phase 1D+1E: Public Slot Generation + Search Filtering

Public availability now subtracts existing bookings with format-aware buffers. Bidirectional: `[booking.start - buffer, booking.end + buffer]`. Windows split on partial tag incompatibility (not wholesale removed).

Search pipeline: SQL `check_availability()` unchanged. Python second-pass filter applies buffer-aware subtraction and tag compatibility. Conservative mapping: `online` → non-travel buffer, `in_person`/`any` → travel buffer.

### Phase 1F: Availability Page Settings UI

Instructor availability page shows buffer dropdowns (non-travel + travel), overnight protection toggle, and auto-saves via `PATCH /instructors/me/calendar-settings`.

First-save acknowledgment popup with three variants based on instructor format mix. Acknowledgment-only modal, re-accessible via "About calendar protections" link.

### Phase 1G: Booking Flow Format Propagation

Students select lesson format before seeing time slots. Multi-format services show format picker with per-format prices. Single-format services auto-select. Format flows through entire booking lifecycle:
- `TimeSelectionModal` owns format selection
- `PaymentConfirmation` passes locked format on time change
- `RescheduleTimeSelectionModal` uses existing booking format
- `neutral_location` stays locked in downstream flows
- All availability hooks include `location_type` in React Query keys

---

## 🏗️ Phase 2 — Per-Block Format Tagging

### Phase 2A: Format Tags Data Model + Bitmap-Native API

**2-bit-per-slot encoding:** 288 slots × 2 bits = 576 bits = 72 bytes per day.

| Tag Value | Name | Allows |
|-----------|------|--------|
| `0b00` (0) | TAG_NONE | All formats |
| `0b01` (1) | TAG_ONLINE_ONLY | Online only |
| `0b10` (2) | TAG_NO_TRAVEL | Online + Studio |
| `0b11` (3) | TAG_RESERVED | Blocks all (future use) |

`format_tags` column added to `availability_days` with CHECK constraint `length(format_tags) = 72`.

**Bitmap-native week API:** Instructor availability GET/POST converted from window-based to base64-encoded bytes. Eliminates 4 window↔bitmap conversions per save/load. ETag/version hash incorporates both `bits` and `format_tags`.

### Phase 2B: Tag-Based Filtering

`is_tag_compatible(tag, location_type)` enforced server-side in:
- Booking validation: `FORMAT_TAG_INCOMPATIBLE` error
- Public availability: window splitting on partial incompatibility
- Search: Python second-pass tag filtering

### Phase 2C: Frontend Tagging UI

Paint-mode toolbar above availability grid for mixed-format instructors. Three brush modes: All / No Travel / Online. Drag-painting applies active mode.

Visual indicators: Online Only (blue + monitor icon), No Travel (green + car-with-strikethrough). Booked cells are tag-locked. Clearing availability auto-clears tags.

Tag legend shown below grid. Toolbar hidden for single-format instructors.

---

## 🔍 Audit Findings + Fixes

### Round 1 (2 Critical, 1 High)
| Finding | Fix |
|---------|-----|
| Copy/apply flows drop format_tags | copy_week and apply_pattern now copy both bits + tags |
| Buffer subtraction one-directional | Bidirectional: `[start - buffer, end + buffer]` |
| check_availability missing capability validation | Added `_validate_location_capability()` call |

### Round 2 (1 Critical, 1 High, 1 Medium)
| Finding | Fix |
|---------|-----|
| Reschedule locks funds before duration validation | Preflight validates duration before any fund lock |
| check_availability missing service-area validation | Optional lat/lng on AvailabilityCheckRequest |
| Midnight-ending bookings rejected on check | Schema allows midnight rollover matching create path |

### Round 3 (1 High, 1 Medium)
| Finding | Fix |
|---------|-----|
| Stale tags on bits-only write paths | Repository-level normalization: bits=0 → tags=TAG_NONE |
| ORM model drifts from migration | CHECK constraints + server_default added to model |
| ETag computed before normalization | Service normalizes tags before hash computation |

### CI Review Fixes
| Finding | Fix |
|---------|-----|
| N+1 ConfigService in ConflictChecker | Injected as constructor dependency, fetched once per call |
| `or 0` falsy config pattern | Explicit `None` check preserves valid 0 values |
| Boolean buffer coercion | Falls back to default instead of `int(True)=1` |
| PENDING bookings excluded from conflicts | Active PENDING included; auth-failed PENDING excluded |
| Race condition in booking creation | Advisory lock on `(instructor_id, booking_date)` |
| ConfigService in BookingService | Injected as constructor dependency |
| ConfigService in AvailabilityService | Injected as constructor dependency |

---

## 🧹 Pre-Existing Calendar-Adjacent Cleanup

| Fix | Details |
|-----|---------|
| `set_range_tag` strict validation | Raises on out-of-range instead of silently skipping |
| PII in logs | `availability_windows.py` logs user ID, not email |
| `save_week_bits` / `save_week_bitmaps` duplication | Consolidated into shared bitmap-native save core |
| Private cross-boundary method access | `resolve_default_buffer_minutes_from_config` made public |
| Double blackout check in conflict_checker | Called once, result reused |
| Profile fetched twice in conflict_checker | Fetched once, passed through |
| `_bitmap_repo()` per-call instantiation | Created once in `__init__`, stored as `self._bitmap_repository` |
| Redundant index on availability_days | Removed (PK already covers it) |
| Missing FK on availability_days.instructor_id | Added with CASCADE delete |
| Hardcoded NYC timezone in search | Requester timezone threaded through FilterService |
| FilterService not extending BaseService | Now extends BaseService with `@measure_operation` |

---

## 🛡️ Security Updates

| Update | Details |
|--------|---------|
| pyjwt 2.11.0 → 2.12.0 | CVE-2026-32597: `crit` header validation bypass |
| @size-limit/preset-app | Moved to devDependencies, aligned to 12.0.1. Production audit clean. |

---

## 🏛️ Architecture Decisions

### New ADRs from this session:

- **Format classification as shared helpers** — `INSTRUCTOR_TRAVEL_FORMATS = {"student_location", "neutral_location"}` and `STUDENT_TRAVEL_FORMATS = {"instructor_location", "neutral_location"}` centralized in `config_service.py`. Used everywhere — no duplicated branch logic.

- **neutral_location uses travel rules everywhere** — 3hr advance notice, travel buffer. The instructor is traveling regardless of who chose the venue.

- **Platform-dictated advance notice** — Not instructor-configurable. `booking_rules` platform config only. Fits the "Uber of learning" instant-booking philosophy.

- **2-bit-per-slot format tags** — Single `format_tags` column (72 bytes/day) with packed encoding. Mutual exclusivity enforced by data structure. Scales to 4 tag values without schema change.

- **Bitmap-native week API** — Base64 bytes on the wire. Zero conversion. Frontend bitmaps go directly to/from base64. Backend bitmaps go directly to/from DB.

- **Repository-level tag normalization** — `bits=0 → tags=TAG_NONE` enforced in all 3 write paths. Service normalizes before hash computation for ETag consistency. Single enforcement point, not scattered.

- **Paint-mode toolbar over context menu** — Right-click one-by-one was unusable. Toolbar with drag-painting is discoverable and efficient.

- **Advisory locks on booking creation** — `pg_advisory_xact_lock` keyed on `(instructor_id, booking_date)`. Wraps conflict check + INSERT. Prevents race between check and create.

- **Requester timezone for search window** — Authenticated user's timezone determines the 7-day search window. Unauthenticated falls back to `DEFAULT_TIMEZONE`. Instructor timezone used for per-instructor availability evaluation.

---

## 📋 Tracked Technical Debt (Post-Merge)

Full list in `tech-debt-from-calendar-beast-reviews.md`. Priority items:

| Priority | Item | Risk |
|----------|------|------|
| High | S1: Sensitive fields in public endpoints (Stripe session IDs) | Data exposure |
| High | S2: Student email exposed to instructors | Privacy |
| High | B2: Privacy service swallows PII anonymization failures | GDPR |
| Medium | P1: ConfigService TTL cache | Performance |
| Medium | S3: public_logout swallows tampered tokens | Security monitoring |
| Medium | S4: Cache-Control: public on authenticated responses | CDN correctness |
| Medium | A1: Service mutation at request time (race condition) | Correctness |
| Low | P2-P4: os.getenv hot paths, logger.info, anyio.run | Performance |
| Low | A2-A3: Duplicated helpers | Maintenance |
| Low | M1-M4: Dead code, schema inheritance, f-string logging | Cleanup |

---

## 🔑 Key Files Created/Modified

### Backend — New Files
```
backend/app/constants/booking_rules_defaults.py          # Booking rules default values
backend/app/schemas/booking_rules_config.py              # BookingRulesConfig schema
backend/app/utils/bitmap_base64.py                       # Base64 encode/decode for bitmaps
backend/app/models/service_format_pricing.py             # ServiceFormatPrice model (from v139)
backend/app/repositories/service_format_pricing_repository.py
```

### Backend — Major Modifications
```
backend/app/core/constants.py                            # Tag constants, BITS_PER_TAG, TAG_BYTES_PER_DAY
backend/app/utils/bitset.py                              # 2-bit tag helpers, is_tag_compatible
backend/app/models/availability_day.py                   # format_tags column, FK, CHECK constraints
backend/app/models/instructor.py                         # Buffer + overnight + acknowledged_at columns
backend/app/services/config_service.py                   # Travel classification, advance notice, overnight helpers
backend/app/services/conflict_checker.py                 # Buffer-aware conflicts, DI, single-fetch
backend/app/services/booking_service.py                  # Tag validation, overnight, advisory locks, DI
backend/app/services/availability_service.py             # Bitmap-native API, tag filtering, consolidated save
backend/app/services/week_operation_service.py            # Copy/apply preserves format_tags
backend/app/services/search/filter_service.py            # Tag-aware second pass, extends BaseService
backend/app/repositories/filter_repository.py            # Timezone cleanup, instructor TZ batch load
backend/app/repositories/availability_day_repository.py  # Tag normalization in all write paths
backend/app/repositories/conflict_checker_repository.py  # PENDING + auth_failure handling
backend/app/routes/v1/availability_windows.py            # Bitmap-native GET/POST
backend/app/routes/v1/public.py                          # Format-aware public availability
backend/app/routes/v1/bookings.py                        # Advisory locks, reschedule preflight
backend/app/schemas/availability_window.py               # DayBitmapInput/Response schemas
backend/app/schemas/booking.py                           # location_type required on check-availability
backend/alembic/versions/002_instructor_system.py        # Buffer + overnight columns
backend/alembic/versions/003_availability_booking.py     # format_tags column, FK, constraints
```

### Frontend — New Files
```
frontend/components/availability/FormatTagPaintToolbar.tsx
frontend/components/availability/NoTravelIcon.tsx
frontend/components/availability/CalendarSettingsSection.tsx
frontend/components/availability/CalendarSettingsAcknowledgementModal.tsx
frontend/components/availability/calendarSettings.ts
frontend/lib/calendar/bitmapBase64.ts
frontend/lib/pricing/formatPricing.ts
```

### Frontend — Major Modifications
```
frontend/lib/calendar/bitset.ts                          # 2-bit tag helpers
frontend/hooks/availability/useWeekSchedule.ts           # Bitmap-native decode
frontend/hooks/availability/useAvailability.ts           # WeekTags state, base64 save
frontend/hooks/queries/useInstructorAvailability.ts      # location_type in query key
frontend/hooks/queries/usePublicAvailability.ts          # location_type in query key
frontend/components/availability/InteractiveGrid.tsx     # Paint-mode brush, tag rendering
frontend/components/calendar/WeekView.tsx                # Tag props threading
frontend/features/student/booking/components/TimeSelectionModal.tsx  # Format picker
frontend/components/lessons/modals/RescheduleTimeSelectionModal.tsx  # Locked format
frontend/features/student/payment/components/PaymentConfirmation.tsx # Format propagation
frontend/app/(auth)/instructor/availability/page.tsx     # Settings UI, toolbar, acknowledgment
frontend/app/(public)/search/page.tsx                    # NL filter format mapping
frontend/types/availability.ts                           # DayTags, WeekTags types
```

---

## 📊 Platform Health (Post-v141)

| Metric | Value | Change from v140 |
|--------|-------|-------------------|
| **Backend Tests** | 13,137 | +206 |
| **Frontend Tests** | 8,245 | +28 |
| **Backend Coverage** | 98%+ | Maintained |
| **Frontend Coverage** | 97%+ | Maintained |
| **Frontend Type Coverage** | 100% | Maintained |
| **API Endpoints** | 372+ | +2 (calendar-settings, acknowledge) |
| **Audit Rounds** | 3 | New |
| **CI Review Rounds** | 4 | New |
| **npm Vulnerabilities** | 0 | Fixed |
| **Bitmap Resolution** | 288 slots/day (5-min) | Unchanged |

---

*Session v141 — Calendar Beast: 10 implementation phases, 3 audit rounds, 4 CI reviews, 11 pre-existing fixes, ~14K additions, 13,137 backend + 8,245 frontend tests passing* 🗓️

**STATUS: Calendar Beast merged via PR #322. Format-aware buffers, advance notice, overnight protection, per-block format tagging — complete end-to-end. Tech debt tracker created for post-merge cleanup.**
