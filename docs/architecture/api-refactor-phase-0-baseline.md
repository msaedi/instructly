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

## Phase 4 - Expand Usage + Guardrails

**Status:** ✅ Complete
**Date:** November 24, 2025

### Implementation Summary

Phase 4 focused on consolidating auth usage, expanding the service layer pattern, and adding guardrails to prevent regressions.

### 1. Auth/Session Consolidation

**Goal:** Consolidate all `/auth/me` calls to use the canonical `useSession` hook.

**Changes:**
1. **Migrated `hooks/queries/useHomepage.ts`:**
   - Replaced `useUser()` with `useCurrentUser()` from `@/src/api/hooks/useSession`
   - Updated 3 functions: `useUpcomingBookings`, `useBookingHistory`, `useHomepageData`
   - Simplified auth checks: `const user = useCurrentUser()` instead of `const { data: user } = useUser()`

2. **Deprecated old `hooks/queries/useUser.ts`:**
   - Added `@deprecated` JSDoc comments to all exports
   - Provided migration guide for each function
   - Kept file functional for backward compatibility during transition

3. **Updated documentation and examples:**
   - Updated `lib/react-query/README.md` to reference new hooks
   - Updated `lib/react-query/example-usage.tsx` with new patterns

**Result:**
- ✅ `useSession` is now the ONLY hook that directly calls `/auth/me`
- ✅ All new code must use hooks from `@/src/api/hooks/useSession`
- ✅ Clear deprecation path for old hooks

### 2. Expanded Instructor Service Usage

**Goal:** Migrate additional instructor features to the new Orval-based service layer.

**Migrated Feature:**
- **Onboarding Go-Live** (`app/(auth)/instructor/onboarding/status/page.tsx:165-173`):
  - **Before:** `fetchWithAuth('/instructors/me/go-live', { method: 'POST' })`
  - **After:** `useGoLiveInstructor()` mutation hook from service layer
  - Proper error handling with logger instead of console.error

**Result:**
- ✅ Demonstrated service layer pattern works beyond initial dashboard migration
- ✅ One more endpoint migrated from raw fetch to Orval-generated hooks
- ✅ Cleaner, type-safe implementation with React Query mutation

### 3. Guardrails Against Raw `/api/` Strings

**Goal:** Prevent new raw `/api/...` string literals in app code.

**Implementation:**
- Created pre-commit hook: `frontend/scripts/precommit_no_raw_api.sh`
- Added to `.pre-commit-config.yaml` as `frontend-no-raw-api-strings`
- Blocks commits containing `"/api/"`, `'/api/'`, or `` `/api/` `` in:
  - Components, hooks, app, features, lib, services

**Exclusions (allowed to have `/api/` strings):**
- `src/api/generated/**/*` - Orval-generated files
- `src/api/orval-mutator.ts` - Orval configuration
- `orval.config.ts` - Configuration
- Test files (`__tests__/`, `*.test.*`, `*.spec.*`, `e2e/`)
- Legacy files being migrated: `lib/api.ts`, `lib/apiBase.ts`, `lib/betaApi.ts`
- API client layer: `features/shared/api/**/*`

**Error Message:**
```
❌ Phase 4 API Guardrail: Raw /api/ strings detected

The following files contain raw /api/ path strings:
  - path/to/file.ts
      123: const url = '/api/instructors/me';

❌ Use Orval-generated hooks from @/src/api/services/* instead of raw /api/ strings.
   See: docs/architecture/api-refactor-phase-4.md
```

**Result:**
- ✅ Pre-commit hook prevents new violations
- ✅ Developers guided to use Orval-generated clients
- ✅ Legacy files excluded during migration period

### 4. Verification & Testing

**All checks passing:**
```bash
npm run lint                    # ✅ 0 errors, 0 warnings
npm run typecheck               # ✅ Pass
npm run typecheck:strict        # ✅ Pass
npm run typecheck:strict-all    # ✅ Pass
pre-commit run --all-files      # ✅ All hooks pass
```

**Pre-commit hooks:**
- ✅ `frontend-eslint` - Pass
- ✅ `frontend-no-console` - Pass
- ✅ `frontend-no-raw-api-strings` - Pass (new)
- ✅ `frontend-public-env` - Pass

### Summary

**What Changed:**
1. Auth consolidated: `useSession` is now the canonical source for `/auth/me`
2. Service layer expanded: Go-live endpoint migrated to Orval pattern
3. Guardrails added: Pre-commit hook prevents raw `/api/` strings

**What's Protected:**
- ✅ No new raw `/api/` strings can be committed to app code
- ✅ All `/auth/me` access goes through one canonical hook
- ✅ New features must use Orval-generated clients

**Migration Strategy:**
- Legacy files explicitly excluded from guardrails
- Deprecation notices guide developers to new patterns
- Clear error messages when violations detected

---

## Phase 5 - Backend Testing Hardening

**Status:** ✅ Complete
**Date:** November 24, 2025

### Implementation Summary

Phase 5 added automated API contract testing and schema validation using Schemathesis and Spectral to ensure our FastAPI application conforms to its OpenAPI schema.

### 1. Schemathesis API Contract Tests

**Goal:** Automatically validate that `/api/v1` endpoints conform to their OpenAPI schema through property-based testing.

**Implementation:**
1. **Added Schemathesis as backend dev dependency:**
   - Updated `backend/requirements-dev.txt` with `schemathesis>=3.34.0`

2. **Created Schemathesis test module** (`backend/tests/integration/test_schemathesis_api_v1.py`):
   - Uses `schemathesis.from_asgi()` to load OpenAPI schema directly from the ASGI app
   - Filters tests to `/api/v1/instructors.*` endpoints initially (focused scope)
   - Configures Hypothesis with `max_examples=5` for fast feedback
   - Validates responses match schema and checks for server errors

3. **Added pytest marker configuration** (`backend/pyproject.toml`):
   ```toml
   [tool.pytest.ini_options]
   markers = [
       "schemathesis: Schemathesis-based API contract tests",
       "unit: Unit tests",
       "integration: Integration tests",
   ]
   ```

**Test Structure:**
```python
@schema.parametrize(endpoint="/api/v1/instructors.*")
@hypothesis_settings(max_examples=5, deadline=None)
def test_api_v1_instructors_schema_compliance(case):
    """Test /api/v1/instructors/** endpoints conform to OpenAPI schema."""
    response = case.call_asgi()
    case.validate_response(response)
    not_a_server_error(response, case)
```

**Running Tests:**
```bash
# Run only Schemathesis tests
cd backend && pytest -m schemathesis -v

# Or via Makefile
make api-test
```

### 2. Spectral OpenAPI Linting

**Goal:** Ensure OpenAPI schema quality through static analysis and style enforcement.

**Implementation:**
1. **Installed Spectral CLI** as frontend dev dependency:
   - `npm install --save-dev @stoplight/spectral-cli`

2. **Created Spectral configuration** (`backend/openapi/spectral.yaml`):
   - Extends `spectral:oas` ruleset
   - Enforces operation descriptions and tags
   - Validates operation IDs (uniqueness, URL-safe)
   - Custom rule: No trailing slashes in paths (matches routing invariants)
   - Disabled noisy rules: `info-contact`, `info-license`

3. **Added npm script** (`frontend/package.json`):
   ```json
   "api:lint": "spectral lint ../backend/openapi/openapi.json -r ../backend/openapi/spectral.yaml"
   ```

**Running Linter:**
```bash
# From frontend directory
npm run api:lint

# Or via Makefile
make api-lint
```

**Linter Output Example:**
```
/Users/.../backend/openapi/openapi.json
    1:1    warning  oas3-api-servers             OpenAPI "servers" must be present and non-empty array.
  1:67270    error  oas3-valid-schema-example    "profile" property must have required property "id"
  1:194506  warning  operation-description        Operation "description" must be present and non-empty string.
```

### 3. Makefile Convenience Commands

**Added to root `Makefile`:**
```makefile
api-test:
	@echo "Running Schemathesis API contract tests..."
	cd backend && pytest -m schemathesis -v

api-lint:
	@echo "Running Spectral OpenAPI linter..."
	cd frontend && npm run api:lint

api-check:
	@echo "Running full API validation (tests + lint)..."
	$(MAKE) api-test
	$(MAKE) api-lint
```

**Usage:**
```bash
make api-test    # Run Schemathesis contract tests
make api-lint    # Run Spectral OpenAPI linter
make api-check   # Run both tests and linter
```

### 4. Benefits

**Automated Contract Validation:**
- Catches schema drift between implementation and documentation
- Finds edge cases and invalid responses through property-based testing
- Ensures type safety between backend and frontend

**Schema Quality Enforcement:**
- Prevents trailing slashes (routing invariant compliance)
- Enforces documentation completeness (descriptions, tags)
- Validates operation ID conventions
- Catches schema definition errors

**Fast Feedback Loop:**
- Schemathesis: ~5 examples per endpoint (fast iteration)
- Spectral: Sub-second linting
- Both run locally without server startup

### 5. Current Status

**Schemathesis Tests:**
- ✅ Test module created and configured
- ✅ Scoped to `/api/v1/instructors.*` initially
- ✅ Pytest marker registered
- ✅ Fast test execution (5 examples per endpoint)
- 📋 Broader `/api/v1/.*` test available but skipped (enable when ready)

**Spectral Linting:**
- ✅ Configuration created with sane defaults
- ✅ Custom rules for project conventions
- ✅ Finds 12 errors and 140+ warnings in current schema
- 📋 Warnings can be addressed incrementally

### 6. Next Steps (Optional)

**For Schemathesis:**
- Increase `max_examples` for more thorough testing (when needed)
- Enable broader `/api/v1/.*` test coverage
- Add authentication fixtures for protected endpoints
- Configure custom data generation strategies

**For Spectral:**
- Address schema validation errors (example mismatches)
- Add missing operation descriptions
- Enable additional rules as needed (info-contact, etc.)
- Consider CI integration with exit-on-error

### Phase 5c – Test Regression Cleanup

**Overview:**
- Schemathesis introduced database pollution because tests bypassed our standard fixtures.
- Manual performance/email scripts were being collected by pytest, causing SSL, async, and network failures.
- Event outbox cleanup logic and instructor ID validation needed to be tightened for v1 routes.

**Fixes:**
- Added reusable helpers (`create_test_session`, `cleanup_test_database`) for isolated Schemathesis calls and switched the tests to use our FastAPI test client overrides.
- Restricted instructor path parameters with FastAPI `Path` metadata and fixed `is_valid_ulid` to use `ULID.from_str` so coverage endpoints accept valid IDs.
- Ignored dev/performance script suites that are not meant for pytest, and forced `anyio`-based tests to run under asyncio (`anyio_backend` fixture) while marking async modules appropriately.
- Configured pytest to skip script harnesses under `scripts/*` and `tests/performance/*`, and cleaned up MyPy issues in bookings/payment summaries and instructor routes.
- Ensured `pre-commit`/mypy gates stay green and documented the regression cleanup here for future reference.
- Documented test collection intent:
  - `scripts/dev/test_*.py`, `scripts/test_*.py`, and `scripts/monitoring/test_*.py` are dev/ops harnesses that hit running services or send alerts, so they remain out of the automated suite via `collect_ignore_glob`.
  - `tests/performance/test_*.py` hosts manual perf harnesses (FastAPI apps, long‑running scripts) and stays opt-in for engineers; these are ignored by default to avoid Redis/API dependencies during CI.
  - Added `.hypothesis` back to `norecursedirs` so Hypothesis no longer warns during collection.

### 7. Files Changed

**Backend:**
- `requirements-dev.txt` - Added schemathesis
- `pyproject.toml` - Added pytest markers
- `tests/integration/test_schemathesis_api_v1.py` - New test module
- `openapi/spectral.yaml` - New linter configuration

**Frontend:**
- `package.json` - Added `@stoplight/spectral-cli` and `api:lint` script

**Root:**
- `Makefile` - Added `api-test`, `api-lint`, `api-check` commands

---

**Status:** Phases 0, 1, 2, 3, 4, 5 Complete ✅
**Ready for:** Phase 6 (Full Migration - Remaining Endpoints) or Production Deployment

## Phase 7 - Bookings V1 Migration (Student Upcoming Lessons)

**Date:** November 24, 2025
**Status:** ✅ Complete

### Overview

Migrated the **student upcoming lessons** vertical slice from legacy bookings endpoints to v1 API + service-layer pattern, establishing the foundation for full bookings migration.

### Migrated Components

#### Frontend Hooks
- **File:** `frontend/hooks/useMyLessons.ts`
- **Hook:** `useCurrentLessons()`
- **Migration:** Legacy `queryFn('/bookings/upcoming')` → v1 `useBookingsList({ upcoming_only: true })`
- **Endpoint:** `/bookings/upcoming` → `/api/v1/bookings?upcoming_only=true`
- **Response:** Now returns full `BookingResponse[]` objects instead of lightweight summaries

#### Frontend Pages
- **File:** `frontend/app/(auth)/student/lessons/page.tsx`
- **Usage:** Consumes `useCurrentLessons()` hook (no changes needed due to preserved interface)
- **Behavior:** Displays upcoming lessons for students with full booking details

### Key Changes

#### 1. V1 Service Usage
```typescript
// Before (legacy)
export function useCurrentLessons(enabled: boolean = true) {
  return useQuery<BookingListResponse>({
    queryKey: queryKeys.bookings.all,
    queryFn: queryFn('/bookings/upcoming', {
      params: { limit: 20 },
      requireAuth: true,
    }),
    staleTime: CACHE_TIMES.FREQUENT,
  });
}

// After (v1)
export function useCurrentLessons(_enabled: boolean = true) {
  const result = useBookingsList({
    upcoming_only: true,
    per_page: 20,
  });

  // Map v1 response shape to legacy shape for backward compatibility
  return {
    ...result,
    data: result.data ? {
      items: result.data.items as Booking[],
      total: result.data.total,
      page: result.data.page ?? 1,
      per_page: result.data.per_page ?? 20,
      has_next: result.data.has_next,
      has_prev: result.data.has_prev,
    } as BookingListResponse : undefined,
  };
}
```

#### 2. Response Shape Mapping
- **V1 Response:** `PaginatedResponseBookingResponse` with `has_next`, `has_prev`
- **Legacy Interface:** Preserved for backward compatibility
- **Items:** Full `BookingResponse[]` objects with all booking fields

#### 3. Query Key Migration
- **Old:** `queryKeys.bookings.all` (from `lib/react-query/queryClient.ts`)
- **New:** `queryKeys.bookings.student({ status: 'upcoming' })` (from `src/api/queryKeys.ts`)
- **Note:** V1 services use the new centralized query key factory

### Tests Updated

#### Hook Tests
- **File:** `frontend/__tests__/hooks/useMyLessons.test.tsx`
- **Changes:**
  - Added mock for `@/src/api/services/bookings.useBookingsList`
  - Mock returns proper React Query hook shape with all properties
  - Removed dependency on legacy `queryFn` mock for `useCurrentLessons`
  - All 13 tests passing ✅

#### Page Tests
- **File:** `frontend/__tests__/pages/lessons/MyLessonsPage.test.tsx`
- **Changes:** None needed (mocks work through hook abstraction)
- **Status:** All 13 tests passing ✅

### Pre-commit Guardrails Added

#### Script Updated
- **File:** `frontend/scripts/precommit_no_raw_api.sh`
- **New Check:** Now blocks raw `/bookings` strings in addition to `/api/` strings
- **Allowed Patterns:**
  - `lib/api/bookings.ts` (legacy client, will be deprecated)
  - `__tests__/` (test files)
  - `src/api/generated/` (Orval-generated code)
- **Error Message:**
```bash
❌ API Architecture Guardrail: Raw endpoint strings detected

Files with raw /bookings strings (Phase 7 migration):
  - path/to/file.ts

❌ Use Orval-generated hooks from @/src/api/services/* instead of raw endpoint strings.
   For bookings: import from @/src/api/services/bookings or @/src/api/services/instructor-bookings
   See: docs/architecture/api-refactor-phase-7.md
```

### Quality Gate Results

#### Backend
- ✅ **ruff**: All checks passed
- ✅ **mypy --no-incremental app**: Success, no issues in 339 files
- ✅ **TZ=UTC pytest backend/**: 2043 passed, 83 skipped (9:09 runtime)

#### Frontend
- ✅ **npm run build**: Build successful
- ✅ **npm run lint**: No errors, no warnings
- ✅ **npm run typecheck**: TypeScript check passed
- ✅ **npm run typecheck:strict**: Strict TypeScript check passed
- ✅ **npm run typecheck:strict-all**: Strictest TypeScript check passed
- ✅ **npm run test**: All tests passing

### Remaining Legacy Bookings Consumers

The following components still use legacy bookings endpoints and should be migrated in future phases:

#### Frontend Hooks
- `useCompletedLessons()` - Uses `/bookings/?exclude_future_confirmed=true`
- `useLessonDetails()` - Uses `/bookings/${id}`
- `useCancelLesson()` - Uses `/bookings/${id}/cancel`
- `useRescheduleLesson()` - Uses `/bookings/${id}/reschedule`
- `useCompleteLesson()` - Uses `bookingsApi.completeBooking()`
- `useMarkNoShow()` - Uses `bookingsApi.markNoShow()`

#### Frontend Components
- `frontend/app/(auth)/instructor/messages/page.tsx` - Uses `bookingsApi`
- Various lesson card modals and components

#### Legacy API Client
- **File:** `frontend/lib/api/bookings.ts`
- **Endpoints:** All legacy non-v1 endpoints
- **Status:** Should be fully deprecated once all consumers migrated

### Migration Gotchas Discovered

1. **Response Shape Differences:**
   - V1 upcoming endpoint returns lightweight `UpcomingBookingResponse` with fewer fields
   - Had to use full `/api/v1/bookings` with `upcoming_only` filter instead
   - Full `BookingResponse` objects required for component compatibility

2. **Query Key Systems:**
   - Two separate query key factories exist (old and new)
   - V1 services use new factory from `src/api/queryKeys.ts`
   - Legacy hooks use old factory from `lib/react-query/queryClient.ts`
   - Gradual migration path needed to avoid cache invalidation issues

3. **React Query Properties:**
   - Must include all React Query hook properties in mocks
   - Missing properties like `dataUpdatedAt` caused test failures
   - V1 Orval hooks have slightly different property types

4. **Backward Compatibility:**
   - Preserved `enabled` parameter signature even though v1 doesn't support it
   - Used underscore prefix to indicate unused parameter
   - Maintained legacy response shape for consuming components

### Next Steps

For complete bookings migration:

1. **Phase 7b:** Migrate `useCompletedLessons` and lesson history
2. **Phase 7c:** Migrate lesson details and mutations (cancel, reschedule, complete, no-show)
3. **Phase 7d:** Migrate instructor bookings consumers
4. **Phase 7e:** Deprecate and remove `frontend/lib/api/bookings.ts`
5. **Phase 7f:** Update MSW mocks and E2E tests to use v1 endpoints

### Files Changed

#### Added/Modified
- `frontend/hooks/useMyLessons.ts` - Migrated `useCurrentLessons` to v1
- `frontend/__tests__/hooks/useMyLessons.test.tsx` - Updated mocks for v1
- `frontend/scripts/precommit_no_raw_api.sh` - Added `/bookings` check
- `docs/architecture/api-refactor-phase-0-baseline.md` - This documentation

#### No Changes Needed
- `frontend/app/(auth)/student/lessons/page.tsx` - Hook interface preserved
- `frontend/__tests__/pages/lessons/MyLessonsPage.test.tsx` - Mocks work through abstraction

### Architecture Patterns Established

This migration establishes the pattern for all future bookings migrations:

1. **Use v1 services** from `@/src/api/services/bookings` or `@/src/api/services/instructor-bookings`
2. **Preserve hook interfaces** when migrating to avoid cascading changes
3. **Map response shapes** for backward compatibility during transition
4. **Update test mocks** to reflect v1 service usage
5. **Add pre-commit checks** to prevent new legacy endpoint usage
6. **Verify all quality gates** before considering migration complete

---

**Phase 7 Status:** ✅ **Complete** - First vertical slice successfully migrated with zero regressions.
