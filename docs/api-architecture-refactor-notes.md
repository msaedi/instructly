# API Architecture Refactor Notes

## Phase 0 - Baseline & Setup

**Branch:** `feat/api-architecture-v1`
**Default Branch:** `main`
**Date:** November 23, 2025

## Current Repository Structure

### Backend (FastAPI)

**Main App Entry:** `backend/app/main.py`

**Router Directory:** `backend/app/routes/`

### Current Router Mounts

The backend currently has **dual mounting patterns** where many routers are mounted both with and without `/api` prefix:

#### Routers with Dual Mounts (both `/prefix` and `/api/prefix`)
- `instructors.router` → mounted at `/instructors` (line 954)
- `instructors.api_router` → mounted at `/api` (line 955)
- `instructor_bookings.router` → mounted at `/instructors/bookings` (line 957)
- `instructor_bookings.api_router` → mounted at `/api` (line 958)

#### Routers Mounted Only with Prefix
- `auth.router` → no prefix (includes `/auth/login`, `/auth/register`, etc.)
- `two_factor_auth.router` → no prefix
- `account_management.router` → no prefix
- `services.router` → no prefix
- `availability_windows.router` → no prefix
- `password_reset.router` → no prefix
- `bookings.router` → no prefix
- `student_badges.router` → no prefix
- `pricing_preview.router` → no prefix
- `pricing_config_public.router` → no prefix
- `favorites.router` → no prefix
- `payments.router` → no prefix
- `messages.router` → no prefix
- `reviews.router` → no prefix

#### Routers Mounted with `/api` Prefix
- `analytics.router` → `/api/analytics` (line 975)
- `search.router` → `/api/search` (line 981)
- `search_history.router` → `/api/search-history` (line 982)
- `privacy.router` → `/api/privacy` (line 989)

#### Admin & Monitoring Routers
- `admin_config.router`
- `admin_audit.router`
- `admin_badges.router`
- `admin_background_checks.router`
- `admin_instructors.router`
- `metrics.router`
- `monitoring.router`
- `alerts.router`
- `codebase_metrics.router`
- `redis_monitor.router`
- `database_monitor.router`
- `prometheus.router`

#### Webhook & Internal Routers
- `stripe_webhooks.router`
- `webhooks_checkr.router`
- `internal.router`
- `ready.router`
- `beta.router`
- `gated.router`
- `uploads.router`
- `users_profile_picture.router`
- `public.router`
- `referrals.public_router`
- `referrals.router`
- `referrals.admin_router`
- `addresses.router`

### Router File Examples

**instructors.py** (lines 69-70):
```python
router = APIRouter(prefix="/instructors", tags=["instructors"])
api_router = APIRouter(prefix="/api", tags=["instructors"])
```

**instructor_bookings.py** (lines 32-34):
```python
router = APIRouter(prefix="/instructors/bookings", tags=["instructor-bookings"])
# Mirror routes under /api for environments that mount the backend behind that prefix
api_router = APIRouter(prefix="/api", tags=["instructor-bookings"])
```

### Key Observations

1. **Inconsistent Mounting:** Some routers have dual mounts (e.g., `/instructors` and `/api/instructors`), others only one
2. **No `/api/v1` Structure:** Routes are not versioned
3. **Mixed Patterns:** Some routers define their own prefix, some rely on app-level mounting
4. **Legacy Comment:** "Mirror routes under /api for environments that mount the backend behind that prefix" suggests evolution

### Frontend API Layer

**Primary API Files:**
- `frontend/lib/api.ts` - Main API client with `fetchWithAuth` function
- `frontend/lib/apiBase.ts` - Base URL configuration
- `frontend/features/shared/api/client.ts` - Clean API client for student features
- `frontend/features/shared/api/types.ts` - Generated TypeScript types (OpenAPI shim)

**API Patterns:**
- Mix of direct `fetch()` calls and centralized `fetchWithAuth()`
- Some endpoints use OpenAPI-generated types, some don't
- Constants for endpoints exist in `client.ts` (PUBLIC_ENDPOINTS, PROTECTED_ENDPOINTS)
- Raw `/api/...` strings scattered throughout codebase

### Baseline Test Results

**Backend Tests:**
```bash
# Command: python -m pytest tests/models/ -v
# Result: 25 passed, 6 skipped in 6.36s ✅
# All passing tests are related to model validation
# Skipped tests are for deprecated AvailabilitySlot model
```

**Frontend Tests:**
```bash
# Command: npm run typecheck
# Result: TypeScript compilation successful with 0 errors ✅
# Using strictest TypeScript configuration
```

**Missing Tests:**
- No `tests/test_routes_invariants.py` (to be created in Phase 1)
- No routing conflict tests
- No `/api/v1` structure tests

## Next Steps (Phase 1)

1. Introduce domain/service structure in backend
2. Create `InstructorService` as reference pattern
3. Build v1 router for instructors (`/api/v1/instructors`)
4. Centralize all routes under `/api/v1`
5. Add routing invariants tests:
   - All routes start with `/api/v1`
   - No trailing slashes
   - No static vs dynamic conflicts

## Architecture Goals

### Backend
- All JSON endpoints under `/api/v1`
- Business logic in services (not routers)
- Routing tests catch conflicts
- Clean separation: routes → services → repositories

### Frontend
- Orval-generated clients/hooks only
- `useSession` as sole `/auth/me` consumer
- Centralized query keys via factory
- No raw `/api/...` strings in app code

---

**Status:** Phase 0 Complete ✅
**Ready for:** Phase 1 Implementation
