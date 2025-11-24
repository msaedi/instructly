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

## Phase 1 - Service Layer + `/api/v1` Routing

**Status:** ✅ Complete
**Date:** November 23, 2025

### Implementation Summary

1. **Created v1 Router Structure:**
   - New directory: `backend/app/routes/v1/`
   - Created `backend/app/routes/v1/instructors.py` with all instructor endpoints
   - All endpoints mounted under `/api/v1/instructors`

2. **Leveraged Existing Service Layer:**
   - Found `InstructorService` already exists with all business logic
   - All route handlers delegate to service methods
   - Clean separation maintained: routes → services → repositories

3. **Updated Main App:**
   - Created `api_v1 = APIRouter(prefix="/api/v1")` in `main.py`
   - Mounted v1 instructors router under api_v1
   - Deprecated legacy instructor routes (commented out)
   - Added `/api/v1/instructors` to `PUBLIC_OPEN_PREFIXES`

4. **Updated OpenAPI App:**
   - Modified `backend/app/openapi_app.py` to include v1 routes
   - Ensures OpenAPI schema reflects new v1 structure
   - Removed legacy instructor route mounts

5. **Added Routing Invariants Tests:**
   - Created `backend/tests/test_routes_invariants.py` (289 lines)
   - Tests enforce:
     - All JSON routes under `/api/v1` (with legacy exclusions)
     - No trailing slashes
     - Static routes before dynamic routes
     - v1 instructors endpoints exist
     - Legacy instructors endpoints removed

6. **Updated Existing Tests:**
   - Fixed `test_privacy_protection.py` to use `/api/v1/instructors` paths
   - All tests passing ✅

### V1 Instructor Endpoints

All mounted at `/api/v1/instructors`:
- `GET /api/v1/instructors` - List instructors (with service filter)
- `GET /api/v1/instructors/me` - Get instructor profile
- `POST /api/v1/instructors/me` - Create instructor profile
- `PUT /api/v1/instructors/me` - Update instructor profile
- `DELETE /api/v1/instructors/me` - Delete instructor profile
- `POST /api/v1/instructors/me/go-live` - Activate instructor profile
- `GET /api/v1/instructors/{id}` - Get instructor by ID
- `GET /api/v1/instructors/{id}/coverage` - Get service area coverage

### Test Results

**Backend Tests:**
- All existing tests passing ✅
- New routing invariants tests: 7 passed ✅
- Privacy protection tests updated and passing ✅
- mypy clean (0 new errors) ✅

**Type Safety:**
- Fixed mypy errors in v1 routes
- Added appropriate `# type: ignore` comments for known FastAPI/mypy issues

---

## Phase 2 - OpenAPI + Orval Integration

**Status:** ✅ Complete
**Date:** November 23, 2025

### Implementation Summary

1. **OpenAPI Schema Export:**
   - Found existing `backend/scripts/export_openapi.py` (already working)
   - Updated `backend/app/openapi_app.py` to include v1 routes
   - Schema exports to `backend/openapi/openapi.json` (344KB)

2. **Orval Installation & Configuration:**
   - Installed `orval@^7.16.1` as dev dependency
   - Created `frontend/orval.config.ts`:
     - Input: `../backend/openapi/openapi.json`
     - Output: `src/api/generated/instructly.ts`
     - Client: `react-query`
     - Mode: `tags-split` (generates separate files per OpenAPI tag)

3. **Custom Fetch Mutator:**
   - Created `frontend/src/api/orval-mutator.ts`
   - Uses existing `withApiBase()` infrastructure from `@/lib/apiBase`
   - Handles:
     - Base URL resolution (environment-aware)
     - Cookie-based authentication (`credentials: 'include'`)
     - JSON request/response handling
     - Query string building
     - Error normalization
     - AbortSignal support

4. **NPM Scripts:**
   - `api:schema` - Export OpenAPI schema from backend
   - `api:generate` - Run Orval to generate TypeScript + React Query clients
   - `api:sync` - Run both schema export and client generation

5. **Generated Files:**
   - Orval successfully generated 29 tag-split files in `src/api/generated/`
   - Instructor v1 routes: `src/api/generated/instructors-v1/instructors-v1.ts`
   - All URLs use correct `/api/v1/instructors` paths
   - Removed stale `instructors/instructors.ts` (legacy routes no longer exist)

### Generated React Query Hooks (Example)

From `instructors-v1/instructors-v1.ts`:
- `useListInstructorsApiV1InstructorsGet()` - List instructors query
- `useGetMyProfileInstructorsMeGet()` - Get my profile query
- `useCreateInstructorProfileInstructorsMePost()` - Create profile mutation
- `useUpdateProfileInstructorsMePut()` - Update profile mutation
- `useDeleteInstructorProfileInstructorsMeDelete()` - Delete profile mutation
- `useGoLiveInstructorsMeGoLivePost()` - Go live mutation
- Plus query key factories and options builders

### Custom Mutator Implementation

```typescript
export async function customFetch<T>(config: {
  url: string;
  method: string;
  params?: Record<string, unknown>;
  data?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
}): Promise<T> {
  // Build query string from params
  // Build full URL with withApiBase()
  // Handle credentials, JSON, errors
  // Support AbortSignal for cancellation
}
```

### Verification

**TypeScript Compilation:**
```bash
npm run typecheck
# Result: 0 errors ✅
```

**Generated URLs Verified:**
All instructor v1 endpoints use correct paths:
- `/api/v1/instructors`
- `/api/v1/instructors/me`
- `/api/v1/instructors/me/go-live`
- `/api/v1/instructors/{instructorId}`
- `/api/v1/instructors/{instructorId}/coverage`

**OpenAPI Tags:**
- No "instructors" tag (legacy removed)
- New "instructors-v1" tag present
- 29 total tags generating separate client files

### What's NOT Done Yet (Phase 3)

Phase 2 explicitly **did not** refactor frontend components. That's Phase 3:
- Migrate existing components to use Orval-generated hooks
- Create `useSession` canonical hook
- Create query key factories
- Remove raw `/api/` strings from app code
- Update React Query usage patterns

---

## Phase 3 - Core Frontend Infrastructure

**Status:** ✅ Complete
**Date:** November 23, 2025

### Implementation Summary

1. **Created Core Infrastructure Files:**
   - `src/api/queryKeys.ts` - Centralized React Query key factory
   - `src/api/hooks/useSession.ts` - Canonical session hook (sole `/auth/me` consumer)
   - `src/api/services/instructors.ts` - Service layer wrapping Orval-generated instructor hooks

2. **Fixed Module Import Paths:**
   - Identified path alias issue: files in `src/` require `@/src/...` not `@/api/...`
   - Fixed imports in all three new infrastructure files
   - Aligned with existing codebase patterns (e.g., `@/src/types/api`)

3. **Migrated Vertical Slice Feature:**
   - **Target:** `hooks/queries/useInstructorProfileMe.ts`
   - **Reason:** Small (36 lines), focused, used by real components (dashboard, dropdown)
   - **Strategy:** Maintain exact backward compatibility while using new architecture
   - **Implementation:**
     - Uses Orval-generated `useGetMyProfileApiV1InstructorsMeGet` hook
     - Uses centralized `queryKeys.instructors.me` from query key factory
     - Properly passes `enabled` parameter through to React Query
     - Casts response to `InstructorProfile` type for backward compatibility
   - **Consumers Updated:**
     - Fixed `app/(auth)/instructor/dashboard/page.tsx` to properly type-cast error

4. **Fixed Type Issues:**
   - Changed `SessionUser` from empty interface to type alias (ESLint requirement)
   - Removed unused imports
   - Added proper error type casting in dashboard

### Architecture Files

**Query Key Factory** (`src/api/queryKeys.ts`):
```typescript
export const queryKeys = {
  auth: {
    me: ['auth', 'me'] as const,
  },
  instructors: {
    list: (filters?) => ['instructors', 'list', filters ?? {}] as const,
    detail: (id: string) => ['instructors', 'detail', id] as const,
    me: ['instructors', 'me'] as const,
    coverage: (id: string) => ['instructors', 'coverage', id] as const,
  },
  bookings: { /* ... */ },
  services: { /* ... */ },
  availability: { /* ... */ },
};
```

**Session Hook** (`src/api/hooks/useSession.ts`):
- Wraps `useReadUsersMeAuthMeGet()` from `@/src/api/generated/auth/auth`
- Uses `queryKeys.auth.me` for cache key
- Session-long caching (`staleTime: Infinity`, `gcTime: Infinity`)
- No automatic refetching
- Exports convenience functions: `useCurrentUser()`, `useIsAuthenticated()`, `useUserPermissions()`, `useHasPermission()`

**Instructor Service Layer** (`src/api/services/instructors.ts`):
- Wraps all Orval-generated instructor hooks
- Applies consistent query options (stale times, query keys)
- Domain-friendly function names (e.g., `useInstructorMe()` instead of `useGetMyProfileApiV1InstructorsMeGet()`)
- Exports type aliases for convenience

**Migrated Hook** (`hooks/queries/useInstructorProfileMe.ts`):
```typescript
export function useInstructorProfileMe(enabled: boolean = true) {
  const result = useGetMyProfileApiV1InstructorsMeGet({
    query: {
      queryKey: queryKeys.instructors.me,
      staleTime: 1000 * 60 * 15, // 15 minutes
      enabled,
    },
  });

  return {
    ...result,
    data: result.data as InstructorProfile | undefined,
  };
}
```

### Verification Results

**ESLint:**
```bash
npm run lint
# Result: 0 errors, 0 warnings ✅
```

**TypeScript Compilation:**
```bash
npm run typecheck           # ✅ Pass
npm run typecheck:strict    # ✅ Pass
npm run typecheck:strict-all # ✅ Pass
```

**Pre-commit Hooks:**
```bash
pre-commit run frontend-eslint --files <modified files>
# Result: Passed ✅
```

### Key Learnings

1. **Path Aliases:** Files in `src/` directory must use `@/src/...` import pattern
2. **Backward Compatibility:** Migrated hooks must preserve exact interface (including `enabled` parameter)
3. **Service Layer Optional:** For hooks needing custom options (like `enabled`), can call Orval hooks directly
4. **Error Typing:** Orval-generated hooks may have loose error types (`{}`), require type assertion in consumers
5. **Type Aliases Over Empty Interfaces:** ESLint enforces type aliases for single-type extensions

### What's NOT Done Yet (Phase 4)

Phase 3 established **infrastructure and proof-of-concept only**. Remaining work:
- Migrate remaining hooks to use Orval-generated clients
- Remove raw `/api/` strings from components
- Replace direct `fetch()` calls with React Query hooks
- Update all components to use new service layer

---

**Status:** Phases 0, 1, 2, 3 Complete ✅
**Ready for:** Phase 4 Full Frontend Migration
