# API Versioning & Migration

*Last Updated: November 2025 (Session v117)*

## Overview

InstaInstru uses a **path-based API versioning** strategy where all API endpoints are organized under `/api/v1/`. This architecture enables contract testing, type safety, and graceful migrations without breaking clients.

### Key Characteristics

| Aspect | Implementation |
|--------|---------------|
| Version Prefix | `/api/v1/` |
| OpenAPI Export | Deterministic JSON generation |
| Type Generation | `openapi-typescript` → TypeScript types |
| Contract Testing | Schemathesis (daily runs) |
| Type Shim | `features/shared/api/types.ts` |

### API Structure

```
/api/v1/
├── /auth              # Authentication
├── /bookings          # Booking management
├── /instructors       # Instructor profiles
├── /instructors/availability  # Availability windows
├── /messages          # Messaging system
├── /payments          # Payment processing
├── /reviews           # Review system
├── /search            # Search endpoints
├── /services          # Service catalog
└── /admin/*           # Admin endpoints
```

---

## Architecture

### Backend Router Setup

Located in `backend/app/main.py`:

```python
# Create API v1 router
api_v1 = APIRouter(prefix="/api/v1")

# Mount v1 routes (order matters for path collision avoidance)
api_v1.include_router(availability_windows_v1.router, prefix="/instructors/availability")
api_v1.include_router(instructors_v1.router, prefix="/instructors")
api_v1.include_router(bookings_v1.router, prefix="/bookings")
api_v1.include_router(messages_v1.router, prefix="/messages")
api_v1.include_router(payments_v1.router, prefix="/payments")
# ... more routes ...

# Mount on main app
app.include_router(api_v1)
```

### Route Module Structure

Each v1 route module in `backend/app/routes/v1/`:

```python
# backend/app/routes/v1/bookings.py
from fastapi import APIRouter

router = APIRouter(tags=["bookings"])

@router.get("/", response_model=PaginatedResponse[BookingResponse])
async def list_bookings(...):
    ...

@router.post("/", response_model=BookingResponse)
async def create_booking(...):
    ...
```

### OpenAPI Generation

Located in `backend/scripts/export_openapi.py`:

```python
def main():
    # Import minimal app (no prod dependencies)
    from app.openapi_app import openapi_app as app

    # Generate OpenAPI spec
    spec = app.openapi()

    # Minified, deterministic output
    data = dumps_min(spec)

    # Strip docs if too large (>500KB)
    if len(data) > 500_000:
        spec = strip_docs(spec)
        data = dumps_min(spec)

    # Write to backend/openapi/openapi.json
    out_path.write_bytes(data)
```

**Key Features:**
- Uses `orjson` for deterministic, sorted JSON output
- Strips descriptions/examples to reduce size
- No runtime dependencies (uses `openapi_app.py` minimal app)

---

## Key Components

### 1. TypeScript Type Generation

The frontend generates types from the OpenAPI spec:

```bash
# In frontend/package.json
"scripts": {
  "api:sync": "openapi-typescript ../backend/openapi/openapi.json -o ./types/generated/api.d.ts"
}
```

**Generated types at:** `frontend/types/generated/api.d.ts`

### 2. Type Shim Layer

Located in `frontend/features/shared/api/types.ts`:

```typescript
/**
 * Single import surface for generated OpenAPI types.
 * NOTE: type-only re-exports to avoid bundling.
 */

// Re-export all types under namespace
export type * as Gen from '@/types/generated/api';

// Import components for use in other files
import type { components } from '@/types/generated/api';
export type { components };

// Canonical aliases for commonly used models
export type User = components['schemas']['AuthUserWithPermissionsResponse'];
export type Booking = components['schemas']['BookingResponse'];
export type InstructorProfile = components['schemas']['InstructorProfileResponse'];

// Common endpoint payloads
export type CreateBookingRequest = components['schemas']['BookingCreate'];
export type AvailabilityCheckResponse = components['schemas']['AvailabilityCheckResponse'];
```

**Usage:**
```typescript
// ✅ CORRECT - Use the shim
import { Booking, User } from '@/features/shared/api/types';

// ❌ WRONG - Never import generated types directly
import { components } from '@/types/generated/api';
```

### 3. Contract Testing with Schemathesis

Located in `.github/workflows/schemathesis.yml`:

```yaml
name: schemathesis (read-only)

on:
  schedule:
    - cron: '0 8 * * *'  # Daily at 8:00 UTC
  workflow_dispatch:
    inputs:
      target:
        description: "Which environment to test"
        type: choice
        options: [preview, beta, all]

jobs:
  preview:
    steps:
      - name: Run Schemathesis
        run: |
          schemathesis run "${BASE_URL}/openapi.json" \
            --include-method GET --include-method HEAD \
            --phases=examples \
            --checks not_a_server_error \
            --workers=4
```

**Test Coverage:**
- 61+ Schemathesis tests
- GET/HEAD methods (read-only)
- Runs against preview and beta environments
- Checks for 5xx server errors

---

## Data Flow

### API Contract Lifecycle

```
1. Backend schema changes
   backend/app/schemas/*.py

2. Export OpenAPI spec
   python scripts/export_openapi.py
   → backend/openapi/openapi.json

3. Generate TypeScript types
   npm run api:sync
   → frontend/types/generated/api.d.ts

4. Update type shim (if needed)
   frontend/features/shared/api/types.ts

5. CI validates no drift
   - OpenAPI export is deterministic
   - Type generation is checked
   - Schemathesis tests run daily
```

### Migration Workflow

When migrating endpoints from legacy paths to v1:

```
1. Create v1 route with same functionality
   backend/app/routes/v1/feature.py

2. Mount in main.py
   api_v1.include_router(feature_v1.router, prefix="/feature")

3. Update frontend consumers
   - Search for all references to old path
   - Update API client calls
   - Update test mocks

4. Remove legacy route (after verification)

5. Export and sync types
   python scripts/export_openapi.py
   npm run api:sync
```

---

## Error Handling

### API Response Consistency

All v1 endpoints use Pydantic response models:

```python
@router.get("/{id}", response_model=BookingResponse)
async def get_booking(id: str) -> BookingResponse:
    ...
```

### Error Response Format

```json
{
  "detail": "Booking not found",
  "code": "BOOKING_NOT_FOUND"
}
```

### Validation Errors (422)

```json
{
  "detail": [
    {
      "loc": ["body", "start_time"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Monitoring

### CI/CD Drift Detection

The CI workflow verifies no API contract drift:

1. **OpenAPI Export Check** - Spec must be deterministic
2. **Type Generation Check** - Types must match spec
3. **Schemathesis Tests** - API must match spec at runtime

### Daily Contract Tests

Schemathesis runs daily against:
- Preview environment
- Beta environment

Results are published to GitHub Actions artifacts.

---

## Common Operations

### Export OpenAPI Spec

```bash
cd backend
python scripts/export_openapi.py
# Output: backend/openapi/openapi.json
```

### Sync Frontend Types

```bash
cd frontend
npm run api:sync
# Output: frontend/types/generated/api.d.ts
```

### Full Sync Flow

```bash
# Backend: Export spec
cd backend && python scripts/export_openapi.py

# Frontend: Generate types
cd frontend && npm run api:sync

# Verify no changes (in CI)
git diff --exit-code frontend/types/generated/api.d.ts
```

### Add New v1 Endpoint

1. **Create route module**:
   ```python
   # backend/app/routes/v1/new_feature.py
   from fastapi import APIRouter

   router = APIRouter(tags=["new-feature"])

   @router.get("/", response_model=FeatureResponse)
   async def get_feature(...):
       ...
   ```

2. **Add to v1 package**:
   ```python
   # backend/app/routes/v1/__init__.py
   from . import new_feature
   ```

3. **Mount in main.py**:
   ```python
   from .routes.v1 import new_feature as new_feature_v1
   api_v1.include_router(new_feature_v1.router, prefix="/new-feature")
   ```

4. **Export and sync**:
   ```bash
   python scripts/export_openapi.py
   cd ../frontend && npm run api:sync
   ```

5. **Update type shim** (if needed):
   ```typescript
   // frontend/features/shared/api/types.ts
   export type FeatureResponse = components['schemas']['FeatureResponse'];
   ```

---

## Troubleshooting

### Types Not Matching API

1. **Re-export OpenAPI spec**:
   ```bash
   cd backend && python scripts/export_openapi.py
   ```

2. **Re-generate types**:
   ```bash
   cd frontend && npm run api:sync
   ```

3. **Clear TypeScript cache**:
   ```bash
   rm -rf frontend/.next frontend/node_modules/.cache
   ```

### Schemathesis Failures

1. **Check which endpoints failed** in the artifacts log

2. **Common causes**:
   - Schema mismatch (response doesn't match model)
   - Missing required fields
   - 5xx server errors

3. **Run locally**:
   ```bash
   pip install schemathesis
   schemathesis run http://localhost:8000/openapi.json \
     --include-method GET \
     --checks not_a_server_error
   ```

### Legacy Path Still Being Used

Use the audit command from CLAUDE.md:

```bash
# Find ALL /api/ calls that are NOT /api/v1
grep -rn '"/api/' frontend/ --include="*.ts" --include="*.tsx" | \
  grep -v '/api/v1' | grep -v node_modules | grep -v '.d.ts'
```

---

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAPI_EXPORT` | Set to `1` during spec generation to skip DB |

### NPM Scripts

| Script | Purpose |
|--------|---------|
| `api:sync` | Generate TypeScript types from OpenAPI |

### CI/CD Workflows

| Workflow | Purpose | Schedule |
|----------|---------|----------|
| `schemathesis.yml` | Contract testing | Daily 8:00 UTC |
| `ci.yml` | Type check, lint, test | On PR/push |

---

## Migration Checklist

When migrating an endpoint to v1:

### 1. Pre-Migration

- [ ] Search for ALL references to the old endpoint path
- [ ] Document all consumers (frontend, tests, E2E mocks)

### 2. Backend Changes

- [ ] Create v1 route module
- [ ] Add to v1 package `__init__.py`
- [ ] Mount in `main.py`
- [ ] Export OpenAPI spec

### 3. Frontend Changes

- [ ] Update all API client calls
- [ ] Update service layer files (`src/api/services/*`)
- [ ] Update E2E test mocks
- [ ] Sync types (`npm run api:sync`)
- [ ] Update type shim if needed

### 4. Verification

- [ ] Run legacy path audit (grep for old path)
- [ ] Run TypeScript type check
- [ ] Run E2E tests
- [ ] Browser test affected pages

### 5. Cleanup

- [ ] Remove legacy route (after verification period)
- [ ] Update documentation

---

## Related Documentation

- OpenAPI export: `backend/scripts/export_openapi.py`
- Type shim: `frontend/features/shared/api/types.ts`
- Generated types: `frontend/types/generated/api.d.ts`
- Schemathesis workflow: `.github/workflows/schemathesis.yml`
- v1 routes: `backend/app/routes/v1/`
