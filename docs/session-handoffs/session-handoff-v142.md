# InstaInstru Session Handoff v142
*Generated: March 16, 2026*
*Previous: v141 | Current: v142 | Next: v143*

## 🎯 Session v142 Summary

**Post-Calendar-Beast Tech Debt Remediation — Security, Privacy, Performance, Architecture**

This session delivered three major PRs and a batch dependency update, comprehensively addressing all Critical/High/Medium tech debt items identified during Calendar Beast PR reviews and subsequent CI reviews. The work spanned security hardening (reschedule extraction, template credential isolation, referral validation, privacy enforcement), performance optimization (DB pagination, batch queries, lazy logging), architecture cleanup (single-role enforcement, typed exceptions, dead code removal), and full strict TypeScript broadening. A total of 10+ audit rounds were conducted across the PRs.

| Objective | Status |
|-----------|--------|
| **PR #323: Security, Privacy, Performance, Strict Typecheck** | ✅ Merged |
| **PR #335: Reschedule Extraction, Security Hardening, Query Optimization** | ✅ Merged |
| **PR #336: Lazy Logging, Dead Code, Env Constants, Reschedule Tests** | ✅ Merged |
| **Batch Dependency Updates (11 packages + CI action)** | ✅ Committed to main |
| **WCAG 2.1 AA E2E Mock Fixes (dotted initials)** | ✅ Included in #323 |
| **GitHub Account Security (spam repo cleanup)** | ✅ ~100 spam repos deleted |

---

## 📊 PRs Shipped

### PR #323: Post-Calendar-Beast Tech Debt — Security, Privacy, Performance, Strict Typecheck

| Metric | Value |
|--------|-------|
| **Files Changed** | ~100 |
| **Additions** | ~4,969 |
| **Deletions** | ~2,321 |
| **Audit Rounds** | 6 (local) + 3 (CI bot) |

**Security & Privacy:**
- `InstructorProfilePublic` schema: excludes `identity_verification_session_id`, `background_check_object_key`, `identity_name_mismatch`, `bgc_name_mismatch`, `bgc_status`, `background_check_uploaded_at`
- `StudentInfoPublic` schema: only `id`, `first_name`, `last_initial` exposed to instructors
- Symmetric privacy rule: students see instructor "First L.", instructors see student "First L.", self sees full name, admin sees everything
- `_public_student_payload()`: switched from blocklist to allowlist pattern
- `format_private_display_name()`: never falls back to email — uses "User" if both names empty
- `format_last_initial()`: always called with `with_period=True` — API returns "S." not "S"
- Tampered logout tokens logged at WARNING
- `Cache-Control: private` on authenticated instructor detail
- Booking DTO: `_uses_instructor_booking_response(user, booking)` checks `booking.instructor_id == user.id`, not `user.is_instructor`
- Single-role enforcement: `assign_role()` removes opposite end-user role (INSTRUCTOR removes STUDENT, vice versa). ADMIN exempt.
- Corruption recovery: if user somehow has both roles, `assign_role()` cleans up

**Performance:**
- ConfigService 60s TTL cache on `get_booking_rules_config` and `get_pricing_config` with `time.monotonic()` + `deepcopy()`
- Module-level constants replace `os.getenv` in availability hot paths
- Search logging downgraded to DEBUG
- `anyio.run()` replaced with async pre-step pattern
- ConfigService DI injected in all services (no request-time construction)
- Auto-bio redundant user fetch removed

**Architecture:**
- `_resolve_actor_payload` extracted to BaseService (DRY)
- `safe_float`/`safe_str` in shared `app/utils/safe_cast.py`
- `BookingResponseBase` composition eliminates LSP violation — `InstructorBookingResponse` no longer inherits `BookingResponse`
- Type shim complete: zero direct `@/src/api/generated/instructly.schemas` imports in app code
- `formatDisplayName` shared frontend helper in `lib/format/displayName.ts`
- Dead code removed: `_check_bits_coverage`, `requires_roles`, week_operation_service helpers

**TypeScript:**
- `tsconfig.strict-all.json` broadened to include tests + e2e (removed exclusions)
- 393 errors fixed across 127 files
- CI consolidated to `typecheck:strict-all` only
- `audit_production_type_ignores.py` script + pre-commit integration

**Privacy Tests:**
- `test_student_privacy_sweep.py`: end-to-end validation across 8 API paths and 3 roles
- Cross-student isolation: Student A cannot see Student B PII
- Notification content: email templates don't contain raw student email/phone

---

### PR #335: Tech Debt Remediation — Reschedule Extraction, Security Hardening, Query Optimization

| Metric | Value |
|--------|-------|
| **Files Changed** | ~45 |
| **Additions** | ~2,000 |
| **Deletions** | ~1,200 |
| **Audit Rounds** | 5 (local) + 2 (CI bot) |

**Critical — Reschedule Extraction:**
- Entire reschedule flow extracted from route to `BookingService.reschedule_booking()`
- Route shrunk from ~240 to ~15 lines: fetch booking → student-only guard → acquire lock → delegate → serialize
- **Student-only guard**: 403 when `current_user.id != original_booking.student_id` (pre-existing bug fixed — endpoint accepted any participant but assumed current_user was student)
- **Canonical student resolution**: `_resolve_reschedule_student()` reads from `original_booking.student`, not `current_user`. All downstream creation, availability, and payment use the real student.
- Three paths: lock (atomic transaction), existing-payment (atomic transaction), new-payment (compensating saga with `_rollback_reschedule_replacement()`)
- Stripe calls OUTSIDE DB transactions
- Compensation failure logged at CRITICAL
- Reschedule-reachable logging classified: WARNING for data-integrity paths (ORM refresh, session expire), DEBUG with explicit comments for side-effects (cache, audit)
- `@cached_method` removed from `_booking_list_query()` — SQLAlchemy Query objects cannot be cached (serialized to string on second call, crashing `.filter()`)

**Critical — Security:**
- Settings object removed from Jinja template context — only `frontend_url`, `support_email` passed. Prevents credential exposure via template typos.
- Referral link validated against frontend origin via `urlparse` scheme+netloc comparison. Negative-path test proves `https://evil.com/...` rejected with 400.
- Privacy anonymization re-raises: all `except Exception` blocks in `delete_user_data` now `logger.error()` + `raise`. PII deletion failures cannot be silently swallowed.

**Medium — Query + HTTP + Errors:**
- HTTP 304 returns empty body per spec via `Response(status_code=304)`
- Booking pagination pushed to repository LIMIT/OFFSET (both student and instructor)
- Conversation last-message uses batch SQL lookup (ROW_NUMBER window function) — no in-memory `sorted()` fallback
- Catalog ID validation uses bulk `WHERE id IN (...)` — no N+1 `exists()` loop
- `_get_booking_end_utc` removed — null filtering pushed to DB WHERE clause
- Typed exceptions replace string matching in instructors (`BusinessRuleException.code`) and conversations (`error_code`)
- `report_no_show` auth documented as intentional: both students and instructors can report

**Low — Cleanup:**
- ULID pattern validation on public availability path params
- Input length constraints (`max_length=2000`) on booking notes/reason
- Double service sort removed
- Unsafe `getattr` fixed with default

---

### PR #336: Code Quality Cleanup — Lazy Logging, Dead Code, Env Constants

| Metric | Value |
|--------|-------|
| **Audit Rounds** | 2 (CI bot) |

**Logging Sweep:**
- ALL f-string logger calls under `backend/app/` converted to lazy `%s` formatting
- Zero remaining (`grep` count = 0)
- Message text preserved, structured kwargs preserved, no level changes

**Dead Code Removal:**
- Defensive `getattr(service, "batch_get_latest_messages", None)` → direct call
- No-op `sort_services` validator removed
- Dead in-memory pagination branch removed from `_paginate_bookings`

**Env Constants:**
- `os.getenv` in `dependencies.py` and `notification_provider.py` → module-level constants
- Tests updated to patch module constants instead of env vars

**Other:**
- `parse_time_string` field description updated to HH:MM (parser only handles HH:MM)
- Hardcoded `/Users/mehdisaedi/` paths in utility scripts → script-relative resolution
- Lock-path + existing-payment-path reschedule unit tests added (both verify canonical student, atomic transaction, create-then-cancel order)

---

### Batch Dependency Updates (committed directly to main)

| Package | From → To | Stack |
|---------|-----------|-------|
| uvicorn | 0.41.0 → 0.42.0 | Backend |
| pyjwt[crypto] | 2.12.0 → 2.12.1 | Backend |
| hiredis | 3.3.0 → 3.3.1 | Backend |
| pydantic-settings | 2.13.0 → 2.13.1 | Backend |
| openai | 2.21.0 → 2.28.0 | Backend |
| @sentry/nextjs | 10.41.0 → 10.43.0 | Frontend |
| @stripe/react-stripe-js | 5.6.0 → 5.6.1 | Frontend |
| @jest/globals | 30.2.0 → 30.3.0 | Frontend |
| jsdom | 28.1.0 → 29.0.0 | Frontend |
| knip | 5.85.0 → 5.87.0 | Frontend |
| docker/metadata-action | v5 → v6 | CI |

**Breaking changes resolved:**
- OpenAI 2.28: client init changed — tests now set API key state explicitly at service creation time (CI-safe)
- Caching test updated for removed `@cached_method`
- 11 dependabot PRs (#324-#334) closed as included in batch

---

## 🏛️ Architecture Decisions

### New ADRs from this session:

- **Symmetric Privacy Rule** — Students see instructor "First L.", instructors see student "First L.", self-view sees full name, admin sees everything. Enforced at schema, service, route, and template layers. `StudentInfoPublic` (3 fields only) and `InstructorProfilePublic` (excludes onboarding state) are the boundary schemas.

- **Single-Role Enforcement** — `PermissionService.assign_role()` enforces mutual exclusivity between STUDENT and INSTRUCTOR. ADMIN is additive. Corruption recovery: if both roles present, assigning either cleans up the opposite. Product decision: instructors cannot book as students on the platform.

- **Booking DTO by Relationship, Not Role** — `_uses_instructor_booking_response(user, booking)` checks `booking.instructor_id == user.id`. Never checks `user.is_instructor`. Works correctly for any role configuration.

- **Allowlist over Blocklist for PII** — `_public_student_payload()` picks specific fields (`id`, `first_name`, `last_initial`). Never pops from a copy. New fields cannot leak through.

- **Reschedule Student-Only Guard** — Route returns 403 when caller is not the booking's student. Service resolves canonical student from `original_booking.student` regardless of who calls it. `current_user` is only used for access checks and cancellation actor.

- **Reschedule Compensation Pattern** — Lock and existing-payment paths use single DB transaction for cancel+create. New-payment path uses compensating saga: Stripe calls outside transaction, `_rollback_reschedule_replacement()` if original cancel fails. Compensation failure logged at CRITICAL.

- **Query Objects Are Not Cacheable** — `@cached_method` on `_booking_list_query()` caused the cache to serialize SQLAlchemy Query to string. Second call returned `str` instead of `Query`, crashing on `.filter()`. Decorator removed.

- **Template Credential Isolation** — Full `settings` object (containing DB URLs, API keys) never passed to Jinja templates. Only `frontend_url` and `support_email` exposed.

- **Lazy Logging Convention** — All logger calls use `%s` formatting, never f-strings. Prevents string interpolation when log level is disabled. Enforced via grep check in CI reviews.

---

## 📋 Remaining Backlog

### Code Quality (deferred — not worth the effort)

| Item | Notes |
|------|-------|
| `date.today()` in ~1,048 test locations | Pre-commit blocks production code. Migration-scale, not cleanup-scale. |
| 120+ `"Non-fatal error ignored"` in non-reschedule services | Broader tech debt, most are side-effect paths |

### Product / Feature

| Item | Priority | Notes |
|------|----------|-------|
| Founding instructor activation sequence | **High** | ~102 recruited, codes not all distributed, non-activating instructors need nudges |
| Student acquisition launch | **High** | Post founding instructor activation |
| SEO programmatic pages | Medium | 7 categories × 77 subcategories × 224 services × neighborhoods |
| CardElement → PaymentElement migration | Medium | Unlocks Apple Pay / Google Pay |
| LinkedIn authority sequence (Nina) | Medium | Forbes pipeline |
| Instagram content runway | Medium | |
| AWS Activate application | Low | Defer until full platform live |

---

## 🔒 Security Incident

~100 spam repos with random names and description "Sha1-Hulud: The Second Coming." were found on the GitHub account, all created on November 24, 2025. Pattern consistent with OAuth token abuse (bypasses 2FA). All spam repos deleted. Recommended: revoke unused OAuth apps (Auth0, Database Client, DigitalOcean, Replicate). 2FA was already enabled. GitHub security log didn't retain logs before December 10, 2025, so exact attack vector is unconfirmed.

---

## 📊 Platform Health (Post-v142)

| Metric | Value | Change from v141 |
|--------|-------|-------------------|
| **Backend Tests** | 13,166 | +29 |
| **Frontend Tests** | 8,245 | — |
| **Backend Coverage** | 98%+ | Maintained |
| **Frontend Coverage** | 97%+ | Maintained |
| **Frontend Type Coverage** | 100% | Maintained |
| **API Endpoints** | 372+ | — |
| **Logger f-string Count** | 0 | Was ~200+ |
| **Direct Schema Imports** | 0 | Was 10 |
| **npm Vulnerabilities** | 0 | Maintained |
| **PRs Merged** | 3 (#323, #335, #336) | — |
| **Dependabot PRs Closed** | 11 (#324-#334) | Batch committed |

---

## 🔑 Key Files Created/Modified

### PR #323 — Major Files
```
backend/app/schemas/booking.py                          # BookingResponseBase composition, StudentInfoPublic
backend/app/schemas/instructor.py                       # InstructorProfilePublic, UserBasicPrivacy
backend/app/routes/v1/bookings.py                       # _public_student_payload allowlist, DTO by relationship
backend/app/routes/v1/conversations.py                  # Privacy-safe display names
backend/app/services/permission_service.py              # Single-role enforcement
backend/app/services/config_service.py                  # TTL cache, thread-safety comment
backend/app/utils/privacy.py                            # format_private_display_name, format_last_initial
backend/app/utils/safe_cast.py                          # safe_float, safe_str
backend/app/services/base.py                            # _resolve_actor_payload
backend/scripts/audit_production_type_ignores.py        # Type ignore allowlist audit
backend/tests/integration/test_student_privacy_sweep.py # Privacy regression tests
frontend/lib/format/displayName.ts                      # Shared formatDisplayName helper
frontend/features/shared/api/types.ts                   # Complete type shim
frontend/tsconfig.strict-all.json                       # Broadened — no exclusions
```

### PR #335 — Major Files
```
backend/app/services/booking_service.py                 # reschedule_booking(), _resolve_reschedule_student()
backend/app/routes/v1/bookings.py                       # Thin reschedule route, student-only guard
backend/app/services/privacy_service.py                 # Anonymization re-raises
backend/app/services/notification_service.py            # Template context isolation
backend/app/routes/v1/public.py                         # 304 empty body, referral validation, ULID patterns
backend/app/routes/v1/instructor_bookings.py            # DB pagination, input constraints
backend/app/routes/v1/conversations.py                  # Batch latest-message, typed error codes
backend/app/repositories/booking_repository.py          # Paginated queries, removed @cached_method
backend/app/repositories/message_repository.py          # batch_get_latest_messages (window function)
backend/app/services/instructor_service.py              # Bulk catalog validation, typed exceptions
```

### PR #336 — Major Files
```
backend/app/**/*.py                                     # ~200+ f-string logger → lazy %s (repo-wide)
backend/app/services/dependencies.py                    # Module-level SITE_MODE, CI constants
backend/app/services/notification_provider.py           # Module-level RAISE_ON constant
backend/app/routes/v1/conversations.py                  # Direct batch_get_latest_messages call
backend/app/routes/v1/instructor_bookings.py            # Simplified _paginate_bookings
backend/app/schemas/instructor.py                       # Removed sort_services validator
backend/app/schemas/booking.py                          # HH:MM docs
backend/scripts/check_bgc_counts.py                     # Script-relative paths
backend/scripts/run_rbac_tests.sh                       # Script-relative paths
```

---

## 🏗️ Git History (main, post-v142)

```
HEAD     chore(quality): lazy logging, dead code removal, env constants, reschedule test coverage (#336)
         chore(deps): batch dependency updates March 2026
         fix(platform): tech debt remediation — reschedule extraction, security hardening, query optimization (#335)
         chore(ci): upgrade Claude model to 1M context variant in workflows
         fix(platform): post-Calendar-Beast tech debt — security, privacy, performance, strict typecheck (#323)
         feat: Calendar Beast — format-aware scheduling + per-block format tagging (#322)
```

---

*Session v142 — Tech Debt Remediation: 3 PRs merged, 11 dependabot PRs closed, 10+ audit rounds, security hardening, privacy enforcement, reschedule extraction, query optimization, lazy logging. 13,166 backend + 8,245 frontend tests passing.* 🛡️

**STATUS: All Critical/High/Medium tech debt resolved. Code quality backlog cleared. Remaining work is product/feature only: founding instructor activation → student acquisition → SEO pages.**
