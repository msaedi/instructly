# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🏆 Key Architectural Achievements & Defenses

### Repository Pattern: 29% → 100% ✅
- **Achievement**: Fixed 107 violations, created 4 new repositories, TRUE 100% compliance
- **Defense**: Pre-commit hook blocks any new `db.query()` in services
- **Result**: Architecture integrity permanently protected

### Timezone Consistency: 28 Fixes ✅
- **Achievement**: Fixed all timezone bugs, platform is globally ready
- **Defense**: Pre-commit hook blocks `date.today()` in user-facing code
- **Result**: No timezone bugs can be reintroduced

### Database Safety: 3-Tier Protection ✅
- **Achievement**: INT/STG/PROD separation with confirmation gates
- **Defense**: Automatic INT database default, production requires confirmation
- **Result**: Impossible to accidentally modify production

These defensive measures ensure our hard-won architectural improvements are permanent.

### Engineering Guardrails: Complete ✅
- **Achievement**: TypeScript strictest config with 0 errors, mypy strict ~95% backend coverage
- **Defense**: CI/CD blocks on any type errors, API drift, or security issues
- **Result**: FAANG-level code quality with automated enforcement

## 🛡️ Engineering Guardrails & Quality Standards

### TypeScript Configuration (Strictest Possible)
The frontend uses TypeScript's strictest configuration with ZERO errors allowed:
```json
{
  "strict": true,
  "noUncheckedIndexedAccess": true,
  "exactOptionalPropertyTypes": true,
  "noImplicitReturns": true,
  "noImplicitOverride": true,
  "noFallthroughCasesInSwitch": true,
  "noUnusedLocals": true,
  "noUnusedParameters": true,
  "noPropertyAccessFromIndexSignature": true
}
```
**CI blocks on ANY TypeScript errors - no exceptions.**

### Backend Type Safety (mypy strict)
- **Repositories**: 100% strict typing
- **Services**: ~95% strict (conscious exceptions for external SDKs like Stripe)
- **Routes**: ~95% strict with proper response_model
- **Schemas**: Dual-mode validation (see below)

### API Contract Enforcement
**OpenAPI → TypeScript with automatic drift detection:**
1. Backend exports deterministic OpenAPI spec
2. Frontend generates types via pinned `openapi-typescript`
3. Types accessed via shim at `frontend/features/shared/api/types.ts`
4. CI blocks if any drift detected

**NEVER import generated types directly - always use the shim.**

### API Endpoint Migration Checklist (CRITICAL)

**Problem This Solves:** When migrating endpoints from `/api/...` to `/api/v1/...`, it's easy to create new service layers but miss existing consumers that continue calling old endpoints, resulting in 404 errors at runtime.

**Root Cause:** The codebase has multiple API client patterns:
- Generated Orval hooks in `src/api/generated/`
- Service layers in `src/api/services/`
- Legacy imperative clients in `services/api/`
- Direct fetch calls in components
- E2E test mocks

**MANDATORY Migration Steps:**

1. **Before migration - Find ALL consumers:**
   ```bash
   # Search for ALL references to the endpoint path
   grep -r "/api/reviews" frontend/ --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v ".d.ts"
   ```

2. **Update ALL consumers (not just create new ones):**
   - Generated Orval clients (`src/api/generated/`)
   - Service layer files (`src/api/services/` AND `services/api/`)
   - Direct fetch calls in components
   - API client constants (`features/shared/api/client.ts`)

3. **Update ALL test mocks:**
   - E2E fixtures (`e2e/fixtures/api-mocks.ts`)
   - E2E test files (`e2e/tests/*.spec.ts`)
   - Unit test mocks

4. **Verify no legacy references remain:**
   ```bash
   # This should return NO results for migrated endpoints
   grep -r "/api/reviews/" frontend/ --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v ".d.ts" | grep -v "/api/v1/"
   ```

5. **Test in browser:** Navigate to pages that use the endpoints and check Network tab for 404s.

**Example of what goes wrong:**
```
❌ Created: src/api/services/reviews.ts (new v1 hooks)
❌ Missed:  services/api/reviews.ts (legacy client still calling /api/reviews/)
❌ Result:  Components using legacy client get 404 errors
```

**The rule:** A migration is NOT complete until `grep` for the old endpoint path returns ZERO results in non-generated TypeScript files.

### Post-Migration Comprehensive Audit (MANDATORY)

After ANY API migration, run these THREE audits to catch bugs that domain-specific grep misses:

**1. Legacy Path Audit (all API call patterns):**
```bash
# Find queryFn/fetch calls NOT using /api/v1 (excluding auth/admin/users)
grep -rE "(queryFn|fetch|httpGet|httpPost|httpJson|authFetch|withApiBase)\(['\"][^'\"]*['\"]" frontend/ \
  --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v ".d.ts" | \
  grep -v "/api/v1" | grep -v "/api/auth" | grep -v "/api/admin" | grep -v "/api/users"
```
This catches relative paths like `/bookings/` that bypass domain-specific grep patterns.

**2. E2E Mock Audit:**
```bash
# Find route mocks NOT using /api/v1
grep -rE "\.route\(['\"][^'\"]*" frontend/e2e/ --include="*.ts" | \
  grep -v "/api/v1" | grep -v "localhost:3000" | grep -v "_next"
```
E2E mocks use `page.route()` patterns and need separate verification.

**3. Parameter Validation Patterns (manual review):**
```bash
# Find conditional parameters that could pass invalid values (e.g., limit=0)
grep -rE "\? \d+ : 0\)" frontend/ --include="*.ts" --include="*.tsx" | grep -v node_modules
```
Catches patterns like `useHook(condition ? 2 : 0)` where `0` may cause 422 validation errors.

**Why these audits exist:** Domain-specific grep (e.g., `/api/reviews/`) only catches paths for the domain being migrated. Pre-existing bugs in OTHER domains, relative paths, E2E mocks, and semantic parameter bugs slip through without comprehensive audits.

### 🚨 MANDATORY: Global Legacy Path Audit (RUN THIS EVERY TIME)

**CRITICAL**: Before declaring ANY migration complete, run this single command that catches ALL legacy API paths:

```bash
# Find ALL /api/ calls that are NOT /api/v1 (the definitive audit)
grep -rn '"/api/' frontend/ --include="*.ts" --include="*.tsx" | \
  grep -v '/api/v1' | grep -v node_modules | grep -v '.d.ts' | grep -v '.next/' | \
  grep -v '/api/auth' | grep -v '/api/admin' | grep -v '/api/config' | \
  grep -v '/api/public' | grep -v '/api/payments' | grep -v '/api/uploads' | \
  grep -v '/api/users' | grep -v 'import.*from'
```

**This audit is non-negotiable.** It catches:
- Direct fetch calls: `fetch('/api/bookings')`
- Auth fetch: `fetchWithAuth('/api/addresses/me')`
- API base: `withApiBase('/api/favorites')`
- HTTP helpers: `httpGet('/api/reviews')`
- String templates: `` `/api/addresses/${id}` ``
- Constants: `API_ENDPOINTS.NYC_ZIP_CHECK: '/api/addresses/...'`

**The output MUST be empty** (or only show intentionally non-v1 endpoints like auth/payments).

**Why previous audits failed:**
1. Domain-scoped greps (`/api/referrals`) miss other domains' legacy paths
2. Pattern-based greps (`fetchWithAuth\(`) miss string templates and constants
3. Trusting "previous migrations were complete" without verification

**Browser verification is also mandatory** - one page load catches 404s that grep misses.

### Dual-Mode Request Validation
Backend supports two validation modes for request DTOs:

**Production Mode (default):**
```python
class UserRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')  # Ignores unknown fields
```

**Strict Mode (STRICT_SCHEMAS=1 for dev/test):**
```python
class UserRequest(StrictRequestModel):
    model_config = ConfigDict(extra='forbid')  # Returns 422 on unknown fields
```

### CI/CD Quality Gates
Every PR must pass these automated checks:
- **TypeScript**: Zero errors with strictest config
- **API Contract**: No drift between OpenAPI and TypeScript
- **Backend Types**: mypy strict compliance
- **Bundle Size**: Within defined limits (size-limit)
- **Security**: No High/Critical vulnerabilities (pip-audit, npm audit)
- **Tests**: 100% passing (1452+ tests)
- **Pre-commit hooks**: Repository pattern, timezone usage

### Environment Verification
Automated env-contract workflows verify:
- Headers: `X-Site-Mode`, `X-Phase` present and correct
- CORS: Credentials and origin validation
- Rate limiting: 429 behavior as expected
- Evidence required in job summaries

## Project Overview

InstaInstru is a marketplace platform for instantly booking private instructors in NYC. It's a full-stack application with:
- **Backend**: FastAPI (Python) with PostgreSQL, SQLAlchemy, and Redis caching
- **Frontend**: Next.js 15 with TypeScript and Tailwind CSS v4
- **Architecture**: Clean architecture with separated services, repositories, and route handlers

## 🔴 CRITICAL: ULID Architecture - ALL IDs are Strings!

**BREAKING CHANGE ALERT**: All IDs in the system are now ULIDs (26-character strings), NOT integers!

### What are ULIDs?
- **Universally Unique Lexicographically Sortable Identifiers**
- Example: `01K2GY3VEVJWKZDVH5HMNXEVRD` (always exactly 26 characters)
- Time-sortable (creation timestamp embedded)
- Case-insensitive in URLs
- Generated by application, not database

### Key Points - THIS WILL BREAK IF IGNORED:
- **ALL IDs are strings**: `id: string` not `id: number`
- **26 characters long**: Always exactly 26 characters
- **No sequential integers**: We don't use auto-increment
- **No numeric operations**: Can't use parseInt(), ++, or numeric comparisons

### Working with ULIDs:

**Python (Backend):**
```python
import ulid

# Generate new ULID
new_id = str(ulid.ULID())  # Returns: '01K2GY3VEVJWKZDVH5HMNXEVRD'

# Model definition
class User(Base):
    id: Mapped[str] = mapped_column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
```

**TypeScript (Frontend):**
```typescript
// ALL IDs are strings - NEVER use number!
interface User {
  id: string;           // NOT number! Always ULID string
  instructor_id: string;  // NOT number!
  booking_id: string;     // NOT number!
}

// API calls
GET /api/instructors/01K2GY3VEVJWKZDVH5HMNXEVRD  // NOT /api/instructors/123
```

**Test Data:**
```typescript
// Use proper ULID format in tests
const TEST_USER_ID = '01K2MAY484FQGFEQVN3VKGYZ58';      // ✅ Correct
const TEST_BOOKING_ID = '01K2MAY484FQGFEQVN3VKGYZ59';   // ✅ Correct
// const TEST_ID = 123;  // ❌ NEVER DO THIS!
```

### Common Pitfalls That WILL Break:
- **Don't use parseInt() on IDs** - They're ULID strings!
- **Don't compare IDs numerically** - Use string comparison
- **Don't generate sequential test IDs** - Use proper ULIDs
- **Don't assume IDs are short** - Always 26 characters
- **Don't use number type in TypeScript** - Always string

## 🔧 CI Database Image

**CRITICAL**: Our CI uses a custom PostgreSQL image with PostGIS + pgvector extensions.

### Image Details
- **Location**: `ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector`
- **Source**: `.github/docker/postgres-ci/Dockerfile`
- **Build**: Automated via `.github/workflows/build-ci-database.yml`
- **Base**: `postgis/postgis:14-3.3` + pgvector installed

### Why Custom Image?
- No official image includes both PostGIS AND pgvector
- CI tests require both extensions for spatial features and NL search
- Migrations will FAIL without both extensions

### ⚠️ DO NOT:
- Use random community images (security risk)
- Remove pgvector or PostGIS from migrations
- Change CI to use standard postgres image

## 🗺 Spatial Intelligence with PostGIS (v95)

### Location Architecture
- **Global Scalability**: Generic region boundaries support any city
- **PostGIS Enabled**: Spatial queries with GiST indexes
- **Provider-Agnostic Geocoding**: Swap between Google/Mapbox/Mock
- **Address Management**: Full CRUD with Google Places autocomplete
- **Region Detection**: Automatic neighborhood/region assignment

### Key Spatial Features
```python
# Region boundary detection with PostGIS
ST_Contains(region_boundaries.geometry, ST_MakePoint(lng, lat))

# Spatial repositories with performance metrics
RegionBoundaryRepository.find_region_for_point(lat, lng)
UserAddressRepository.create_with_geocoding(address_data)
```

### Database Tables
- **user_addresses**: User addresses with geocoding and metadata
- **region_boundaries**: Generic regions (NYC neighborhoods ready)
- **instructor_service_areas**: Service area preferences with regions

## 🎯 Natural Language Search Excellence (v94)

### Search Capabilities
- **Typo Tolerance**: Handles common misspellings using pg_trgm
- **Morphology**: Word form normalization (teach/teacher/teaching)
- **Hybrid Scoring**: Combines semantic vectors with text similarity
- **Zero-Result Handling**: Shows related options via vector neighbors
- **Performance**: Sub-50ms with GIN indexes

### PostgreSQL pg_trgm Extension
```sql
-- Fuzzy text search with trigram similarity
WHERE name % 'query' OR similarity(name, 'query') >= 0.3
ORDER BY similarity(name, 'query') DESC
```

### Search Observability
- Persists top-N candidates with scores
- Admin dashboards for category trends
- Query-level debugging and analysis

## 🚨 CRITICAL: Client-Side Caching with React Query

InstaInstru uses React Query (TanStack Query v5) for ALL data fetching. This is MANDATORY - no exceptions.

### Why This Matters
- 60-80% reduction in API calls
- Instant page navigation
- Better user experience
- Reduced server costs

### The Golden Rules
1. **NEVER use fetch() or useEffect for API calls** - Always use React Query
2. **INCREMENTAL approach only** - Add caching to existing code, don't rewrite entire files
3. **Preserve ALL UI/UX** - Caching changes data fetching, not appearance
4. **Test caching works** - Use DevTools to verify

### Quick Implementation Pattern
```jsx
// ✅ CORRECT - Use React Query
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';

const { data, isLoading } = useQuery({
  queryKey: queryKeys.instructors.search({ service: 'yoga' }),
  queryFn: () => queryFn('/api/instructors/search?service=yoga'),
  staleTime: 1000 * 60 * 5, // 5 minutes
});

// ❌ WRONG - Direct fetch
useEffect(() => {
  fetch('/api/instructors/search?service=yoga')
    .then(res => res.json())
    .then(setData);
}, []);
```

### Cache Time Quick Reference
- **User data**: `Infinity` (session-long)
- **Categories/Services**: `1 hour` (static content)
- **Instructor profiles**: `15 minutes`
- **Search results**: `5 minutes`
- **Availability**: `5 minutes` with background refresh
- **Real-time data**: `1 minute`

### Testing Your Implementation
1. Load page → Check Network tab for API calls
2. Navigate away and back
3. ✅ Success: No API calls (using cache)
4. ❌ Failure: API calls made (cache not working)

## Current Project State & Priorities

### Critical Context
- **Mission**: Building for MEGAWATTS of energy allocation - quality over speed
- **Platform Status**: 100% COMPLETE (All core systems operational, ready for beta launch)
- **Test Coverage**: 2,130+ tests passing (100%), zero flakes, deterministic behavior
- **Engineering Quality**: TypeScript strictest mode (0 errors), mypy strict (~95%), automated guardrails

### Platform Excellence Achieved
- **Type Safety**: Frontend 100% strict TypeScript, Backend ~95% mypy strict
- **API Contracts**: Automatic drift prevention with CI enforcement
- **Rate Limiting**: Production-ready GCRA with hot-reload and full observability
- **Operational Controls**: Runtime configuration, comprehensive metrics, battle-tested runbooks
- **CI/CD**: Bulletproof with Node 22, security gates, automated proofs
- **Zero Engineering Debt**: Platform is pristine with FAANG-level code quality

### Pre-Launch Requirements
1. **🔴 Load Testing**: Verify performance with all systems active (3-4 hours)
2. **🔴 Security Audit**: OWASP scan, penetration testing (1-2 days)
3. **🟡 Beta Smoke Test**: Final manual verification (1 day)
4. **🟢 Search Debounce**: 300ms frontend optimization (1 hour)

### Core Systems (All Complete ✅)

| System | Key Features |
|--------|-------------|
| **Payments** | Stripe Connect, 24hr pre-auth, platform credits, tips, tiered commissions |
| **Auth** | JWT + RBAC (30 permissions), 2FA (TOTP + backup codes) |
| **Booking** | Instant booking, bitmap availability, conflict detection, ETag versioning |
| **Search** | Natural language, typo tolerance, morphology, PostGIS spatial (<50ms) |
| **Messaging** | Real-time SSE, archive/trash, reactions, typing, editing |
| **Reviews** | 5-star ratings, text reviews, instructor responses |
| **Referrals** | Give $20/Get $20, device fingerprinting fraud detection |
| **Achievements** | 7 badge types, event-driven awarding, hold mechanism |
| **Background Checks** | Checkr integration, adverse action workflow |
| **Rate Limiting** | GCRA algorithm, runtime config, shadow mode, triple financial protection |

## 🌐 Dual Environment Architecture

**CRITICAL**: We operate two production environments for phased rollout:

| Environment | Domain | Purpose | Database |
|-------------|--------|---------|----------|
| **Preview** | preview.instainstru.com | Internal testing, stakeholder demos | preview_prod |
| **Beta** | beta.instainstru.com | Beta users, public launch | beta_prod |

**Environment Detection:**
- Frontend reads `NEXT_PUBLIC_SITE_MODE` env var (`preview` or `beta`)
- Backend reads `SITE_MODE` env var
- Headers: `X-Site-Mode`, `X-Phase` set by middleware
- Different Stripe accounts, email templates, feature flags per environment

**Why Two Environments:**
- Preview: Safe space for testing with real infrastructure
- Beta: Actual paying customers, production-grade reliability
- Phased rollout: Preview → Beta → Full launch

## 📋 API Versioning (v1)

**ALL API routes are versioned under `/api/v1/*`** (100+ endpoints migrated).

**Structure:**
```
/api/v1/
├── bookings/          # Student booking operations
├── instructors/       # Instructor profiles & search
├── messages/          # Real-time messaging
├── reviews/           # Reviews & ratings
├── favorites/         # Student favorites
├── services/          # Service catalog
├── addresses/         # Address management
├── search/            # Natural language search
├── search-history/    # Search tracking
└── [other domains]/   # Additional features

/api/auth/             # Authentication (not versioned)
/api/admin/            # Admin operations (separate namespace)
```

**Key Points:**
- Contract testing enforces OpenAPI compliance
- Frontend uses generated types via shim (`frontend/features/shared/api/types.ts`)
- Never import generated types directly - always use the shim
- See "API Endpoint Migration Checklist" above for migration process

## Key Architectural Decisions

- **ULID IDs**: All IDs are 26-character strings, not integers (sortable, non-sequential)
- **Time-Based Booking**: No slot entities, just time ranges (instructor_id, date, start_time, end_time)
- **Bitmap Availability**: 1440-bit per day (70% storage reduction vs slots)
- **24hr Pre-Authorization**: Payments authorized T-24hr, captured T+24hr (chargeback protection)
- **Per-User Conversation State**: Independent archive/trash for each participant
- **Repository Pattern**: 100% enforced via pre-commit hooks
- **RBAC**: 30 permissions, not role-based checks
- **Database Safety**: 3-tier (INT/STG/PROD) with automatic INT default
- **API Versioning**: All routes under `/api/v1/*` with contract testing
- **Dual Environments**: Preview and Beta for phased rollout

### Technical Debt Details
Frontend believes slots are database entities with IDs (WRONG). The operation pattern in useAvailabilityOperations.ts is 600+ lines that should be ~50 lines. Mental model mismatch causes 5x slower development.

### Critical Files & Patterns
#### Frontend Technical Debt (3,000+ lines to remove):
- frontend/src/hooks/useAvailabilityOperations.ts (600→50 lines)
- frontend/src/utils/operationGenerator.ts (DELETE ENTIRELY)
- frontend/src/types/availability.ts (remove slot ID references)
- frontend/src/utils/slotHelpers.ts (complex→simple time helpers)

#### Backend Excellence (maintain these patterns):
- All services extend BaseService
- Use @measure_operation decorator on public methods
- Repository pattern: service.repository.method() not direct DB
- Transaction pattern: with self.transaction(): not db.commit()
- No singletons - all services use dependency injection

### Service Quality Scores (maintain or improve):
- ConflictChecker: 9/10 (99% test coverage)
- SlotManager: 9/10 (97% coverage)
- BookingService: 8/10 (97% coverage)
- AvailabilityService: 8/10 (63% coverage - needs work)

## 🛡️ Database Safety System

### Three-Tier Database Architecture
We use a **safe-by-default** three-tier database system:

1. **INT (Integration Test DB)** 🟢
   - **Default database** - no flags needed
   - Database name: `instainstru_test`
   - Used for: pytest, scripts without explicit database selection
   - Can be freely dropped/reset

2. **STG (Staging/Local Dev DB)** 🟡
   - Requires `USE_STG_DATABASE=true`
   - Database name: `instainstru_stg`
   - Used for: local development, preserves data between test runs
   - Automatically used by: `./run_backend.py`, `./run_celery_worker.py`, etc.

3. **PROD (Production DB)** 🔴
   - Requires `USE_PROD_DATABASE=true` + interactive confirmation
   - Database: Supabase PostgreSQL
   - Protection: Must type "yes" to confirm access
   - Non-interactive mode: Raises error (production servers need `INSTAINSTRU_PRODUCTION_MODE=true`)

### How Database Safety Works

**The Critical Innovation**: `settings.database_url` is now a **property** that defaults to INT database!

```python
# This used to be dangerous (went straight to production):
db_url = settings.database_url  # ❌ OLD: Production!

# Now it's safe by default:
db_url = settings.database_url  # ✅ NEW: INT database!
```

### Database Commands

**Primary tool**: `prep_db.py` - Does everything (migrations, seeding, embeddings)
```bash
python scripts/prep_db.py        # Default: INT database
python scripts/prep_db.py int    # Explicit INT
python scripts/prep_db.py stg    # Staging database
python scripts/prep_db.py prod   # Production (requires confirmation)
```

**Local development setup**:
```bash
# First time only - create databases
python scripts/prep_db.py int
python scripts/prep_db.py stg

# Start services (automatically use STG)
./run_backend.py
./run_celery_worker.py

# Run tests (automatically use INT)
pytest -v
```

### Environment Variables
- `USE_STG_DATABASE=true` - Use staging database
- `USE_PROD_DATABASE=true` - Use production (requires confirmation)
- `INSTAINSTRU_PRODUCTION_MODE=true` - Allow production servers to access without confirmation
- `CI=true` - CI/CD environments can use their own DATABASE_URL
- No flag = INT database (safest default)

## 🛡️ Defensive Measures: Preventing Architectural Regression

The project has **strong defensive measures** to prevent regression. These automated guards ensure architectural achievements are never lost.

### Installation
```bash
cd /path/to/instructly
pre-commit install
```

### Active Hooks

#### 1. **Repository Pattern Compliance** (`check-repository-pattern`)
**Purpose**: Ensures services only use repositories for database access.

**Violation patterns detected**:
```python
# ❌ These will be blocked:
self.db.query(User).filter(...)
self.db.add(booking)
self.db.commit()

# ✅ Use repositories instead:
self.repository.get_user_by_id(user_id)
self.repository.create_booking(booking_data)
```

**Markers for exceptions**:
```python
# For legitimate database access:
# repo-pattern-ignore: Transaction management requires direct DB
with self.db.begin_nested():
    ...
```

#### 2. **Timezone Consistency** (`check-timezone-usage`)
**Purpose**: Prevents timezone bugs by blocking `date.today()` in user-facing code.

```python
# ❌ This will be blocked:
today = date.today()

# ✅ Use timezone-aware alternative:
from app.core.timezone_utils import get_user_today_by_id
user_today = get_user_today_by_id(user_id, self.db)
```

#### 3. **API Contract Compliance** (`api-contracts`)
**Purpose**: Ensures all API endpoints return proper Pydantic response models.

### Bypassing Hooks (Emergency Only)
```bash
git commit --no-verify -m "Emergency fix: reason"
```
⚠️ Only use for critical production fixes. Create follow-up task to fix violations.

### CI/CD Integration
Multi-layer defense ensures no regression:
1. **Local Development**: Pre-commit hooks block violations
2. **Pull Request Level**: GitHub Actions runs all checks
3. **Merge Protection**: PRs cannot merge if violations detected

## Features & Systems

### Automatic Timezone Detection
Users' timezones are automatically set based on ZIP code during registration:
- **NYC zips (100-119)** → America/New_York
- **LA zips (900-969)** → America/Los_Angeles
- **Chicago zips (606-608)** → America/Chicago
- **Invalid/missing** → defaults to America/New_York

### Favorites System
Students can favorite/unfavorite instructors:
- **Heart icons** visible to all users
- **Optimistic UI updates** - Instant feedback
- **5-minute cache TTL** - Balance freshness/performance
- **API**: POST/DELETE `/api/favorites/{instructor_id}`

### Schema-Owned Construction Pattern
**Architectural Innovation**: Schemas own their privacy transformation logic.

```python
class InstructorInfo:
    @classmethod
    def from_user(cls, user):
        """Handles privacy transformation - returns FirstName L. format"""
        return cls(
            first_name=user.first_name,
            last_initial=user.last_name[0] if user.last_name else "",
            # Never expose full last name to students
        )
```

### Asset Management with Cloudflare R2
All images served via Cloudflare R2:
- **Custom domain**: assets.instainstru.com
- **80% bandwidth reduction** via Image Transformations
- **Cost**: ~$10/month total

## Infrastructure

### Production Services (Render)
- **API**: instructly-backend (Web Service)
- **Redis**: instructly-redis (Private Service, $7/month)
- **Celery Worker**: instructly-celery (Background Worker)
- **Celery Beat**: instructly-celery-beat (Background Worker)
- **Flower**: instructly-flower (Web Service for monitoring)
- **Database**: Supabase PostgreSQL (external)
- **Total Cost**: $53/month

### Key Infrastructure Updates
- Redis handles all caching, Celery broker, and session needs
- Celery runs analytics processing with async privacy-first design
- Monitoring endpoints require ACCESS_MONITORING permission

## 🚦 Rate Limiter System (Production-Ready)

### GCRA Algorithm with Operational Excellence
The platform uses a sophisticated Generic Cell Rate Algorithm (GCRA) rate limiter with full operational controls:

**Core Features:**
- **Smart Identity Resolution**: User ID → IP fallback chain
- **Financial Triple Protection**: Booking, payment, refund operations protected
- **Runtime Configuration**: Hot-reload without deployment via HMAC-secured endpoints
- **Redis Overrides**: Dynamic per-route policy adjustments
- **Comprehensive Observability**: Decision tracking, latency metrics, error rates

**Operational Endpoints:**
- `POST /api/admin/rate-limiter/reload` - Hot-reload configuration
- `GET /api/admin/rate-limiter/effective-policy` - Query any route's policy
- `GET /api/admin/rate-limiter/config` - View current configuration

**Frontend Integration:**
- Graceful 429 handling with user-friendly banner
- Retry-After header respected
- E2E tests verify behavior

**Configuration Example:**
```python
RATE_LIMIT_BUCKETS = {
    "search": "100/minute",      # High-frequency operations
    "booking": "10/hour",         # Financial operations
    "auth": "5/minute",           # Authentication endpoints
}
```

## Documentation Structure

Key project documentation in `docs/`:
- **Project Overview**: `docs/project-overview/01_core_project_info.md`
- **Architecture State**: `docs/architecture/02_architecture_state.md`
- **Work Streams Status**: `docs/project-status/03_work-streams-status.md`
- **System Capabilities**: `docs/project-status/04_system-capabilities.md`
- **Frontend Cleanup Guide**: `docs/project-status/Frontend Technical Debt Cleanup Checklist - Work Stream #13.md`

A-Team designs in `docs/a-team-deliverables/`:
- **Implementation Guide**: `student-booking-implementation-guide.md`
- **UI Components**: `missing-ui-components.md`

All designs are ASCII mockups with exact specifications. These ARE the official designs.

## Development Approach: Database Migrations

### During Development Phase (No Production Data)
**Important**: Modify existing Alembic migration files instead of creating new ones.

**Workflow for Schema Changes**:
1. **Modify existing migration files** in `backend/alembic/versions/`
2. **Test using INT database**: `python scripts/prep_db.py int`
3. **Reset and rebuild**: Since no production data exists
4. **Use prep_db.py** for all database operations

**DO NOT** create new migration files with `alembic revision` during development.

## 🔴 CRITICAL: Long-Running Command Output Capture

**MANDATORY**: For ANY command that runs longer than 30 seconds (tests, load tests, builds), ALWAYS capture output to a file:

```bash
# ❌ WRONG - Output will be truncated/lost
locust -f locustfile.py --headless -u 150 -r 10 -t 3m

# ✅ CORRECT - Capture to file, then read results
locust -f locustfile.py --headless -u 150 -r 10 -t 3m 2>&1 | tee /tmp/loadtest.log
tail -50 /tmp/loadtest.log  # Read final summary
```

**Why This Matters:**
- Long commands produce output that exceeds buffer limits
- Truncated output wastes user time (e.g., 3-minute load test lost)
- File capture ensures complete results are always available

**Apply To:**
- Load tests (`locust`, `k6`, `artillery`)
- Test suites (`pytest`, `jest`, `playwright`)
- Builds (`npm run build`, `docker build`)
- Any command with `--timeout` or `-t` duration flags

## Essential Commands

### Test Credentials
- **Test User Email**: john.smith@example.com (or any seeded user)
- **Test Password**: Test1234

### Backend Development
```bash
# Setup and run backend
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
uvicorn app.main:app --reload

# Run tests
pytest                           # All tests
pytest -m unit                   # Unit tests only
pytest -m integration            # Integration tests only
pytest -k "test_name"           # Single test

# Database operations (DEVELOPMENT MODE)
python scripts/prep_db.py int   # Reset INT database
python scripts/prep_db.py stg   # Reset STG database

# Code quality
black .                         # Format Python code
isort .                         # Sort imports
```

### Frontend Development
```bash
# Setup and run frontend
cd frontend
npm run dev                     # Development server
npm run build                   # Production build
npm run lint                    # Run ESLint
```

### Redis & Celery Management
```bash
docker-compose up -d            # Start Redis
docker-compose down             # Stop services

# Local Celery commands
celery -A app.tasks.celery_app worker --loglevel=info
celery -A app.tasks.celery_app beat --loglevel=info
celery -A app.tasks.celery_app flower  # Monitoring UI
```

## High-Level Architecture

### Backend Architecture (FastAPI)
1. **Routes Layer**: FastAPI endpoints handling HTTP requests
2. **Services Layer**: Business logic with dependency injection
3. **Repositories Layer**: Data access abstraction with SQLAlchemy
4. **Models Layer**: Database schema definitions
5. **Schemas Layer**: Pydantic models for validation

### Frontend Architecture (Next.js 15)
- **App Directory**: Page routing and layouts
- **Components**: Reusable UI components
- **Hooks**: Custom React hooks for shared logic
- **Lib**: API client and utilities
- **Types**: TypeScript interfaces matching backend schemas

### Key Patterns
1. **Dependency Injection**: Services injected via FastAPI's system
2. **Caching**: Single Redis instance for all needs
3. **Authentication**: JWT-based with RBAC permissions
4. **Error Handling**: Consistent responses with custom exceptions
5. **API Standards**: ALL endpoints use Pydantic response models
6. **Testing**: UUID-based unique data prevents conflicts

## Configuration

### Environment Variables
- Backend: Copy `.env.example` to `.env`
- Frontend: Copy `.env.local.example` to `.env.local`
- Never commit `.env` files

### API Integration
- Frontend API client at `frontend/lib/api.ts`
- Backend API docs available at `/docs` when running
- CORS configured for local development

## Frontend Logging Standards

**CRITICAL: Use Proper Logging, NOT console.log**

```typescript
// ❌ WRONG - Never use console.log
console.log('Debug message');

// ✅ CORRECT - Use the logger
import { logger } from '@/lib/logger';
logger.debug('Debug message', { context: data });
logger.info('Info message');
logger.warn('Warning message');
logger.error('Error message', error);
```

**Setting log level**:
```javascript
// In browser console
localStorage.setItem('log-level', 'debug'); // or 'info', 'warn', 'error'
```

## Common Development Tasks

### Adding New Features
1. Create database model in `backend/app/models/`
2. Create Pydantic schemas in `backend/app/schemas/`
3. Add repository methods in `backend/app/repositories/`
4. Implement service logic in `backend/app/services/`
5. Create API routes in `backend/app/routes/`
6. Add tests in `backend/tests/`
7. Update frontend types and API client
8. Implement UI components

### Performance Optimization
- Use monitoring middleware data at `/ops/performance`
- Profile slow queries with SQLAlchemy logging
- Leverage caching for read-heavy operations
- Database indexes already configured

### Debugging
- Backend logs are comprehensive with proper formatting
- Use pytest's `-vv` flag for detailed test output
- Check `/health` endpoint for system status

## Team Structure
- **X-Team**: Technical implementation (you are part of this)
- **A-Team**: UX/Design decisions (separate team, we await their input)

When working on any feature, ALWAYS check the documentation first for context and current state.

Remember: We're building for MEGAWATTS! Quality over speed. Launch when AMAZING.

## 📁 Guardrail Files Reference

### Critical Guardrail Files
- **TypeScript Config**: `frontend/tsconfig.json` (strictest settings)
- **API Contract Shim**: `frontend/features/shared/api/types.ts` (use this, not generated)
- **Strict DTO Base**: `backend/app/schemas/_strict_base.py` (dual-mode validation)
- **OpenAPI Export**: `backend/scripts/export_openapi.py`, `backend/app/openapi_app.py`
- **Public Env Guard**: `frontend/lib/publicEnv.ts`, `frontend/scripts/verify-public-env.mjs`
- **Rate Limiter Config**: `backend/app/core/rate_limiter.py`
- **Pre-commit Hooks**: `.pre-commit-config.yaml` (repository pattern, timezone checks)
- **CI Workflow**: `.github/workflows/ci.yml` (all quality gates)
- **Env Contract**: `.github/workflows/env-contract.yml` (runtime verification)
- **Schemathesis**: `.github/workflows/schemathesis.yml` (API stability testing)
