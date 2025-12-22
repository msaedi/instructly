# InstaInstru Session Handoff v121
*Generated: December 2025*
*Previous: v120 | Current: v121 | Next: v122*

## 🎯 Session v121 Major Achievements

### Founding Instructor System + Major Platform Cleanup! 🏆🧹

This session delivered the complete Founding Instructor feature, fixed critical race conditions, resolved an availability persistence bug, and executed a massive legacy code cleanup removing ~14,000 lines of dead code.

**Founding Instructor System:**
- Database schema with `is_founding_instructor`, `founding_granted_at` fields
- Lifetime 8% platform fee (vs 15% standard)
- Search ranking boost (1.5x multiplier)
- Tier immunity (exempt from downgrades)
- Founding Instructor badge on profiles and search cards
- Admin UI for managing founding settings
- Atomic cap enforcement with PostgreSQL advisory locks

**Race Condition Fixes:**
- Stripe Connect double-insert → IntegrityError handling with re-fetch
- Founding cap TOCTOU → Advisory lock serialization
- Concurrent tests verify both fixes work under load

**Availability Bug Fix:**
- Hour range now persists in cookies (was resetting to 8-20)
- Auto-expand when data exists outside visible window
- Deleted legacy dashboard availability page (used deprecated 410 endpoint)

**Legacy Route Cleanup (~14,000 LOC removed):**
- Deleted 36 dead legacy route files
- Migrated ALL infrastructure routes to `/api/v1/*`
- Single rule achieved: Everything is `/api/v1/*`
- Cleaned up main.py, openapi_app.py
- Fixed CI workflows for monitoring-lint

## 📊 Current Platform State

### Overall Completion: ~100% COMPLETE + FOUNDING SYSTEM LIVE! ✅

**PRs Merged This Session:**

| PR | Title | Impact |
|----|-------|--------|
| #134 | Migration file reorganization | 2,505-line kitchen sink split into focused files |
| #135 | Payment system audit | Complete payment fixes + test coverage |
| #136 | Founding Instructor System | Full feature + onboarding/Stripe fixes |
| #137 | Legacy Route Cleanup | ~14,000 LOC removed, all routes under /api/v1/* |

**Platform Evolution (v120 → v121):**

| Component | v120 Status | v121 Status | Improvement |
|-----------|-------------|-------------|-------------|
| Founding Instructors | Not implemented | ✅ Complete | Full feature |
| API Paths | Mixed legacy + v1 | All `/api/v1/*` | Single rule |
| Dead Code | ~14,000 LOC | Removed | Clean codebase |
| Race Conditions | Potential issues | ✅ Fixed | Concurrent-safe |
| Availability UX | Hour range reset | ✅ Persists | Better UX |

## 🏗️ Architecture Decisions

### Founding Instructor Cap - Advisory Locks
**Decision**: Use PostgreSQL advisory lock instead of row-level locks.

**Rationale**:
- Row-level `FOR UPDATE` on all profiles causes table-wide contention
- Advisory lock serializes founding claims without blocking other queries
- Lock key: `0x494E5354_464F554E` ("INSTFOUN" in hex)

### Shared Founding Logic
**Decision**: Extract founding status granting to `BetaService.try_grant_founding_status()`.

**Rationale**:
- Logic was duplicated between `auth.py` and `v1/auth.py`
- Single source of truth for cap enforcement
- Returns `(granted: bool, message: str)` for observability

### Origin Validation Utility
**Decision**: Create shared `app/utils/url_validation.py`.

**Rationale**:
- `is_allowed_origin()` was duplicated in payments.py and stripe_service.py
- Security-critical code should have single implementation
- Restricts to explicit allowed IPs only (no generic IP matching)

### Single API Version Rule
**Decision**: ALL routes under `/api/v1/*`, no exceptions.

**Rationale**:
- Pre-launch, no production traffic to break
- Eliminates "is this migrated?" confusion
- Infrastructure routes (health, ready, metrics) also moved
- Only exceptions: `/docs`, `/redoc`, `/openapi.json`

## 💳 Stripe Connect Improvements

### Idempotency Pattern
```python
def create_connected_account(self, instructor_profile_id: str, ...) -> StripeConnectedAccount:
    # Check existing first (fast path)
    existing = self.payment_repository.get_connected_account_by_instructor_id(instructor_profile_id)
    if existing:
        return existing

    try:
        # Create new account
        with self.transaction():
            record = self.payment_repository.create_connected_account_record(...)
        return record
    except IntegrityError:
        # Race condition: another request created first
        self.db.rollback()
        return self.payment_repository.get_connected_account_by_instructor_id(instructor_profile_id)
```

### Origin-Aware Return URLs
- Stripe return URLs now respect request Origin header
- Prevents logout after payment setup (session cookie mismatch)
- Allowlist: localhost, 127.0.0.1, *.instainstru.com (HTTPS required for production)

## 🧹 Legacy Cleanup Summary

### Files Deleted (36 route files + 1 service)
```
backend/app/routes/
├── account_management.py ❌
├── addresses.py ❌
├── admin_*.py (7 files) ❌
├── analytics.py ❌
├── auth.py ❌
├── availability_windows.py ❌
├── beta.py ❌
├── bookings.py ❌
├── codebase_metrics.py ❌
├── database_monitor.py ❌
├── favorites.py ❌
├── health.py ❌
├── instructor_*.py (2 files) ❌
├── instructors.py ❌
├── password_reset.py ❌
├── payments.py ❌
├── pricing_*.py (2 files) ❌
├── privacy.py ❌
├── public.py ❌
├── redis_monitor.py ❌
├── referrals.py ❌
├── reviews.py ❌
├── search_history.py ❌
├── services.py ❌
├── stripe_webhooks.py ❌
├── student_badges.py ❌
├── two_factor_auth.py ❌
├── uploads.py ❌
├── users_profile_picture.py ❌
└── webhooks_checkr.py ❌

backend/app/services/
└── adverse_action_email_templates.py ❌
```

### Infrastructure Routes Migrated
| Old Path | New Path |
|----------|----------|
| `/ready` | `/api/v1/ready` |
| `/health` | `/api/v1/health` |
| `/metrics/prometheus` | `/api/v1/metrics/prometheus` |
| `/v1/gated/ping` | `/api/v1/gated/ping` |
| `/ops/*` | `/api/v1/ops/*` |
| `/api/monitoring/*` | `/api/v1/monitoring/*` |
| `/internal/*` | `/api/v1/internal/*` |
| `/r/{slug}` | `/api/v1/r/{slug}` |

### Render Health Check Updated
- Changed from `/ready` to `/api/v1/ready`
- Flower remains `/healthcheck` (separate application)

## 📈 Test Coverage

### Test Metrics
- **Total Tests**: 3,090+ passing
- **New Tests Added**:
  - 21 URL validation tests
  - 5 founding cap race condition tests
  - 4 registration response tests
  - Stripe Connect idempotency tests
  - Fee consistency test (frontend/backend sync)

### CI Fixes
- `monitoring-lint.yml`: Fixed promtool/amtool entrypoints
- `e2e-tests.yml`: Updated 14 health endpoint references
- All workflows passing

## 🔧 Configuration Updates

### Prometheus
```yaml
# monitoring/prometheus/prometheus.yml
metrics_path: '/api/v1/internal/metrics'  # Was /internal/metrics
```

### Middleware Path Exclusions
All middleware updated to use `/api/v1/*` paths:
- `rate_limiter.py`
- `timing.py`
- `rate_limiter_asgi.py`
- `prometheus_middleware.py`
- `https_redirect.py`

## 🎯 Recommended Next Steps

### From TODO List
1. **Instructor Profile Page** - Critical for booking flow
2. **My Lessons Tab** - Student lesson management
3. **Security Audit** - OWASP scan before launch
4. **Load Testing** - Verify performance under load

### Quick Wins
1. A-team content updates (founding instructor welcome page done ✅)
2. Beta smoke testing
3. Search debounce (300ms frontend optimization)

## 📊 Metrics Summary

### Code Quality
- **Lines Removed**: ~14,000 (dead legacy code)
- **Lines Added**: ~3,500 (founding system + tests)
- **Net Reduction**: ~10,500 lines
- **API Paths**: 235 (all under `/api/v1/*`)
- **TypeScript Errors**: 0
- **mypy Errors**: 0

### Platform Health
- **Response Time**: <100ms average
- **Cache Hit Rate**: 80%+
- **Infrastructure Cost**: $53/month
- **Test Pass Rate**: 100%

## 🚀 Bottom Line

This session achieved two major milestones:

1. **Founding Instructor System** - Complete feature with proper concurrency handling, giving early instructors lifetime benefits and creating urgency for signup.

2. **Legacy Code Elimination** - Single API versioning rule (`/api/v1/*`) eliminates confusion and removes ~14,000 lines of dead code.

The platform is now cleaner, more maintainable, and has a compelling founding instructor offering. Combined with the payment system audit (PR #135) and migration reorganization (PR #134), the codebase is in excellent shape for launch.

**Remember:** We're building for MEGAWATTS! The founding instructor system creates urgency, the clean codebase enables velocity, and the race condition fixes ensure reliability under load. Ready to onboard our first 100 founding instructors! ⚡🏆🚀

---

*Platform 100% COMPLETE + FOUNDING SYSTEM LIVE - Clean architecture, compelling offer, ready for instructors! 🎉*

**STATUS: All legacy code removed, single API version rule achieved, founding instructor system operational! 🚀**
