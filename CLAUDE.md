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

## Project Overview

InstaInstru is a marketplace platform for instantly booking private instructors in NYC. It's a full-stack application with:
- **Backend**: FastAPI (Python) with PostgreSQL, SQLAlchemy, and Redis caching
- **Frontend**: Next.js 15 with TypeScript and Tailwind CSS v4
- **Architecture**: Clean architecture with separated services, repositories, and route handlers

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

### For New Features
1. Identify all API calls needed
2. Use React Query from the start
3. Include filters/params in query keys
4. Test cache hit rate in DevTools
5. Verify instant navigation works

### Common Mistakes to Avoid
- ❌ Rewriting entire components (use incremental approach)
- ❌ Forgetting to include params in query keys
- ❌ Using staleTime: 0 (defeats caching purpose)
- ❌ Not testing cache behavior

### Testing Your Implementation
1. Load page → Check Network tab for API calls
2. Navigate away and back
3. ✅ Success: No API calls (using cache)
4. ❌ Failure: API calls made (cache not working)

Remember: Every API call costs money and time. React Query saves both.

## Current Project State & Priorities

### Critical Context
- **Mission**: Building for MEGAWATTS of energy allocation - quality over speed
- **Platform Status**: ~96% complete - instructor features work, student booking ready for implementation
- **Test Coverage**: 1415+ tests passing (100%), database safety tests complete
- **Major Blocker**: Only 2 critical pages remaining (Instructor Profile + My Lessons Tab)

### Immediate Priorities
1. **Instructor Profile Page**: Next critical component (1-2 days)
2. **My Lessons Tab**: Complete user management interface (2 days)
3. **Phoenix Week 4**: Final instructor migration (1 week)
4. **Security Audit**: Critical for launch (1-2 days)
5. **Load Testing**: Verify scalability (3-4 hours)

### Recently Completed ✅
1. **Database Safety System**: Three-tier protection (INT/STG/PROD)
2. **Search History Race Condition Fix**: PostgreSQL UPSERT eliminating duplicates
3. **Analytics Enhancement 100% Complete**: Privacy framework with GDPR compliance
4. **RBAC System**: 30 permissions replacing role-based access
5. **Redis Migration**: Migrated from Upstash to Render Redis ($7/month)
6. **Privacy Framework**: Complete GDPR compliance with automated retention

### Key Architectural Decisions
- **NO SLOT IDs**: Time-based booking only (instructor_id, date, start_time, end_time)
- **Layer Independence**: Bookings don't reference availability slots (Work Stream #9)
- **Single-Table Design**: Just availability_slots table (no InstructorAvailability)
- **Repository Pattern**: 100% implemented across all services
- **RBAC System**: Full Role-Based Access Control with permissions, NOT simple role checking
- **Redis Architecture**: Single Redis instance for caching, Celery broker, and sessions
- **Database Safety**: Three-tier protection system preventing production accidents
- **Privacy Framework**: GDPR compliance with automated retention and user controls
- **Race Condition Prevention**: PostgreSQL UPSERT for atomic operations

### Technical Debt Details
Frontend believes slots are database entities with IDs (WRONG). The operation pattern in useAvailabilityOperations.ts is 600+ lines that should be ~50 lines. Mental model mismatch causes 5x slower development.

### Common Test Fixes
- **Most Common Failure**: Missing specific_date field (~45 tests failing)
  - When creating slots, use: specific_date=target_date instead of date=
  - AvailabilitySlot.date was renamed to AvailabilitySlot.specific_date
- **Import Errors**: BaseRepositoryService → BaseService
- **Method Renames**:
  - get_booked_slots_for_date → get_booked_times_for_date
  - check_slot_availability → check_time_availability

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

### Recent Achievements
- **Database Safety System**: Three-tier protection preventing production accidents
- **Search History Race Condition Fix**: PostgreSQL UPSERT eliminating duplicates
- **Analytics Enhancement 100% Complete**: Privacy framework with GDPR compliance
- **RBAC System**: 30 permissions replacing role-based access
- **Redis Migration**: Moved from Upstash to Render, 89% reduction in operations
- **Privacy Framework**: Complete GDPR compliance with automated retention
- **Infrastructure Monitoring**: Redis and database dashboards operational
- Public API complete: GET /api/public/instructors/{id}/availability
- Repository Pattern: 100% implementation (7/7 services)
- N+1 query fixed: 99.5% improvement in InstructorProfileRepository
- 5 production bugs found and fixed through testing
- Celery Integration: Scheduled tasks, async processing, monitoring with Flower

### Team Structure
- **X-Team**: Technical implementation (you are part of this)
- **A-Team**: UX/Design decisions (separate team, we await their input)

## Current Infrastructure

### Production Services (Render)
- **API**: instructly-backend (Web Service)
- **Redis**: instructly-redis (Private Service, $7/month)
- **Celery Worker**: instructly-celery (Background Worker)
- **Celery Beat**: instructly-celery-beat (Background Worker)
- **Flower**: instructly-flower (Web Service for monitoring)
- **Database**: Supabase PostgreSQL (external)

### Key Infrastructure Updates
- Redis handles all caching, Celery broker, and session needs
- Celery runs analytics processing with async privacy-first design
- All services configured with optimized settings for cost efficiency
- Monitoring endpoints require ACCESS_MONITORING permission
- Total infrastructure cost: $53/month (increased from $46 due to Redis)

## 🛡️ Critical: Database Safety System

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

**Implementation Details**:
- Raw database URLs are stored as `*_raw` fields (not for direct use)
- Public `database_url` property uses `DatabaseConfig` for safety
- Old scripts are automatically protected without code changes

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
./run_celery_beat.py
./run_flower.py

# Run tests (automatically use INT)
pytest -v
```

### Safety Verification

**Check database safety**:
```bash
python scripts/check_database_safety.py
```

**See safety demonstration**:
```bash
python scripts/demonstrate_database_safety.py
```

### Environment Variables

- `USE_STG_DATABASE=true` - Use staging database
- `USE_PROD_DATABASE=true` - Use production (requires confirmation)
- `INSTAINSTRU_PRODUCTION_MODE=true` - Allow production servers to access without confirmation
- `CI=true` - CI/CD environments can use their own DATABASE_URL
- No flag = INT database (safest default)

### Common Scenarios

**Running any script** (defaults to INT):
```bash
python scripts/some_script.py         # Uses INT
alembic upgrade head                  # Uses INT
python scripts/reset_schema.py        # Uses INT (safe!)
```

**Local development** (use STG):
```bash
USE_STG_DATABASE=true python scripts/some_script.py
# OR use the convenience scripts:
./run_backend.py  # Already sets USE_STG_DATABASE=true
```

**Production operations** (requires confirmation):
```bash
USE_PROD_DATABASE=true alembic upgrade head
# Will show warning and ask for "yes" confirmation
```

**Production server operations** (no confirmation needed):
```bash
# On Render/Vercel with both flags set:
INSTAINSTRU_PRODUCTION_MODE=true USE_PROD_DATABASE=true
# Automatically uses production database without confirmation
```

**CI/CD operations** (uses CI database):
```bash
# GitHub Actions with CI=true and DATABASE_URL set
CI=true DATABASE_URL=postgresql://postgres:postgres@localhost/test_db
# Uses the CI-provided database automatically
```

### Safety Features

1. **Default to INT**: Any database access without explicit flags uses INT
2. **Visual indicators**: Green [INT], Yellow [STG], Red [PROD], Blue [CI]
3. **Audit logging**: All database operations logged to `logs/database_audit.jsonl`
4. **Production confirmation**: Interactive "yes" required for production
5. **Non-interactive protection**: Scripts/CI can't accidentally access production
6. **Zero breaking changes**: Old code automatically becomes safe
7. **Production server mode**: Authorized servers can access production without confirmation
8. **CI/CD support**: Automatically detects CI environments and uses their databases
9. **Environment detection**: Automatically suggests appropriate database based on context

### Testing Database Safety

Run the test suite to verify safety:
```bash
pytest tests/test_database_safety.py -v
```

### Important Files

- `app/core/config.py` - Settings with safe database_url property
- `app/core/database_config.py` - Three-tier database selection logic with CI/production support
- `scripts/prep_db.py` - Main database management tool
- `scripts/check_database_safety.py` - Verify safety is working
- `tests/test_database_safety.py` - Automated safety tests
- `.github/workflows/backend-tests.yml` - GitHub Actions configuration with CI database

## 🛡️ Defensive Measures: Preventing Architectural Regression

The project has **strong defensive measures** to prevent regression of critical fixes. These automated guards ensure that the hard-won achievements in repository pattern (29% → 100%) and timezone consistency (28 fixes) are never lost.

### Why These Defenses Matter
- **Repository Pattern**: Prevents regression from TRUE 100% compliance back to violations
- **Timezone Consistency**: Prevents reintroduction of timezone bugs that were fixed
- **Zero-Tolerance Policy**: Commits are blocked if violations are detected
- **CI/CD Integration**: PRs fail if defensive measures are bypassed

### Installation

Pre-commit hooks are already configured. To ensure they're active:
```bash
cd /path/to/instructly
pre-commit install
```

### Active Hooks

#### 1. **Repository Pattern Compliance** (`check-repository-pattern`)
**Purpose**: Ensures services only use repositories for database access, maintaining clean architecture.

**What it checks**:
- Services don't make direct `db.query()` calls
- No direct SQLAlchemy operations in service layer
- Proper use of repository pattern

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
# For legitimate database access (like BaseService transactions):
# repo-pattern-ignore: Transaction management requires direct DB
with self.db.begin_nested():
    ...

# For code that will be migrated:
# repo-pattern-migrate: TODO: Create UserRepository
user = self.db.query(User).filter_by(id=user_id).first()
```

**Run manually**:
```bash
python backend/scripts/check_repository_pattern.py
```

#### 2. **Timezone Consistency** (`check-timezone-usage`)
**Purpose**: Prevents timezone bugs by blocking `date.today()` in user-facing code.

**What it checks**:
- No `date.today()` in routes, services, or API code
- Ensures timezone-aware date handling

**Example violation**:
```python
# ❌ This will be blocked:
today = date.today()
if booking_date < today:
    raise Error("Cannot book past date")

# ✅ Use timezone-aware alternative:
from app.core.timezone_utils import get_user_today_by_id
user_today = get_user_today_by_id(user_id, self.db)
if booking_date < user_today:
    raise Error("Cannot book past date")
```

**Allowed exceptions**:
- Test files (`test_*.py`)
- System services (cache_service.py, logging_service.py, metrics_service.py)
- System-level operations that genuinely need server time

**Run manually**:
```bash
python backend/scripts/check_timezone_usage.py backend/app/
```

#### 3. **API Contract Compliance** (`api-contracts`)
**Purpose**: Ensures all API endpoints return proper Pydantic response models.

**What it checks**:
- All routes use `response_model=` parameter
- No raw dict/list returns
- Consistent API responses

**Run manually**:
```bash
backend/scripts/check_api_contracts_wrapper.sh
```

### Standard Pre-commit Hooks

The project also uses standard hooks for code quality:
- **black**: Code formatting (120 char line length)
- **isort**: Import sorting
- **trailing-whitespace**: Remove trailing spaces
- **end-of-file-fixer**: Ensure files end with newline
- **check-yaml**: Validate YAML syntax
- **check-added-large-files**: Prevent large file commits

### Bypassing Hooks (Emergency Only)

If you absolutely need to bypass hooks in an emergency:
```bash
git commit --no-verify -m "Emergency fix: reason"
```

**⚠️ WARNING**: Only use this for critical production fixes. Create a follow-up task to fix any violations.

### Configuration

Pre-commit configuration is in `.pre-commit-config.yaml`. The hooks run on relevant files only:
- Repository pattern: `backend/app/(services|core)/.*\.py$`
- Timezone check: `backend/app/(routes|services|api)/.*\.py$`
- API contracts: `backend/app/routes/.*\.py$`

### CI/CD Integration - Multi-Layer Defense

These defensive measures operate at multiple levels:

1. **Local Development**: Pre-commit hooks block violations before commit
2. **Git Level**: Commits are rejected if hooks are bypassed
3. **Pull Request Level**: GitHub Actions runs all checks on PRs
4. **Merge Protection**: PRs cannot merge if violations are detected

This multi-layer defense ensures:
- **Repository Pattern**: Stays at 100% (no regression from 107 fixes)
- **Timezone Consistency**: No reintroduction of the 28 fixed bugs
- **API Contracts**: All endpoints maintain Pydantic response models
- **Code Quality**: Black, isort, and other standards enforced

The defensive measures are **permanent and non-negotiable** - they protect the architectural achievements that earned our megawatts! ⚡

## Documentation Structure

Key project documentation is organized in `docs/`:

- **Project Overview**: `docs/project-overview/01_core_project_info.md`
- **Architecture State**: `docs/architecture/02_architecture_state.md`
- **Work Streams Status**: `docs/project-status/03_work-streams-status.md`
- **System Capabilities**: `docs/project-status/04_system-capabilities.md`
- **Frontend Cleanup Guide**: `docs/project-status/Frontend Technical Debt Cleanup Checklist - Work Stream #13.md`

Always check these documents for current state before making changes.

## A-Team Design Deliverables

The A-Team has delivered complete design specifications in `docs/a-team-deliverables/`:

- **Implementation Guide**: `docs/a-team-deliverables/student-booking-implementation-guide.md`
  - 6-8 week plan with all features designed
  - References all design artifacts
  - Technical implementation details

- **UI Components**: `docs/a-team-deliverables/missing-ui-components.md`
  - Availability calendar grid design
  - Time selection patterns
  - Instructor search cards
  - Booking form specifications

All designs are provided as ASCII mockups with exact measurements, interactions, and specifications. These ARE the official designs, not placeholders.

When implementing any student-facing feature, ALWAYS check these documents first.

## Development Approach: Database Migrations

### During Development Phase (No Production Data)
**Important**: While we're in development without production data, we **modify existing Alembic migration files** instead of creating new ones. This prevents accumulation of migration files that need to be squashed later.

**Workflow for Schema Changes**:
1. **Modify existing migration files** in `backend/alembic/versions/`
2. **Test using INT database**: `python scripts/prep_db.py int`
3. **Reset and rebuild**: Since no production data exists, we can drop and rebuild the schema
4. **Use prep_db.py** for all database operations (migrations, seeding, embeddings)

**DO NOT** create new migration files with `alembic revision` during development unless absolutely necessary.

**When to create new migrations**:
- Only after production launch
- When we have real user data to preserve
- For hotfixes that need to be applied without dropping tables

This approach keeps our migration history clean and manageable.

## Essential Commands

### Test Credentials
- **Test User Email**: john.smith@example.com (or any seeded user)
- **Test Password**: Test1234
- All test users in the seeded database use this password

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
pytest tests/test_file.py       # Single file
pytest -vv                      # Verbose output

# Database operations (DEVELOPMENT MODE)
python scripts/prep_db.py int   # Reset INT database with migrations + seed
python scripts/prep_db.py stg   # Reset STG database with migrations + seed
# DO NOT use: alembic revision -m "message" (modify existing files instead)

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
docker-compose up -d            # Start Redis (replaced DragonflyDB)
docker-compose down             # Stop services

# Local Celery commands
celery -A app.tasks.celery_app worker --loglevel=info
celery -A app.tasks.celery_app beat --loglevel=info
celery -A app.tasks.celery_app flower  # Monitoring UI
```

## High-Level Architecture

### Backend Architecture

The backend follows a layered architecture pattern:

1. **Routes Layer** (`app/routes/`): FastAPI endpoints that handle HTTP requests
   - Each router handles a specific domain (auth, users, availability, etc.)
   - Routes delegate business logic to services

2. **Services Layer** (`app/services/`): Business logic and orchestration
   - Services use dependency injection pattern
   - Examples: AuthService, EmailService, AvailabilityService
   - Services coordinate between repositories and external systems

3. **Repositories Layer** (`app/repositories/`): Data access abstraction
   - All database queries are encapsulated here
   - Uses SQLAlchemy ORM with async support
   - Implements caching strategies with DragonflyDB

4. **Models Layer** (`app/models/`): Database schema definitions
   - SQLAlchemy models with proper relationships
   - Key models: User, Instructor, Student, AvailabilityWindow, Booking

5. **Schemas Layer** (`app/schemas/`): Request/response validation
   - Pydantic models for API contracts
   - Separate schemas for creation, update, and response

### Frontend Architecture

The frontend uses Next.js 15 App Router with:

1. **App Directory**: Page routing and layouts
2. **Components**: Reusable UI components
3. **Hooks**: Custom React hooks for shared logic
4. **Lib**: API client and utilities
5. **Types**: TypeScript interfaces matching backend schemas

### Key Patterns and Practices

1. **Dependency Injection**: Services are injected via FastAPI's dependency system
   ```python
   def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
       return AuthService(db, email_service, token_service)
   ```

2. **Caching & Infrastructure**:
   - Single Redis instance (Render $7/month) for all needs:
     - Application caching
     - Celery message broker
     - Session storage
   - Optimized Celery config reduces operations by 89%
   - Redis monitoring available at `/api/redis/*` endpoints

3. **Authentication & Authorization**:
   - JWT-based authentication with refresh tokens
   - **RBAC System**: Full permission-based access control
     - Use `require_permission(PermissionName.PERMISSION)` NOT role checks
     - Permissions are defined in `app/core/enums.py`
     - Example: `Depends(require_permission(PermissionName.ACCESS_MONITORING))`
   - Roles: admin, instructor, student, guest
   - Each role has specific permissions assigned

4. **Error Handling**: Consistent error responses
   - Custom exception classes
   - Proper HTTP status codes

5. **API Standards & Contract Testing**:
   - **ALL endpoints MUST use Pydantic response models** - No raw dict returns
   - **Consistent response format** across all endpoints
   - **Automated contract testing** prevents regression
   - **CI/CD integration** blocks PRs with violations
   - Response models defined in `app/schemas/*_responses.py`
   - Use `response_model=ModelName` on ALL route decorators
   - **See**: `docs/api/api-standards-guide.md` for complete implementation guide

6. **Testing Approach**:
   - Separate test database with safety checks
   - Fixtures for common test data
   - Async test support with pytest-asyncio
   - **API contract tests** ensure response model compliance
   - **Test Isolation**: Use UUID-based unique data generation to prevent test conflicts
     - Import from `tests.fixtures.unique_test_data` for unique emails, names, etc.
     - Example: `unique_data.unique_email("instructor")` → `instructor.abc123@example.com`
     - This prevents test failures when running tests together locally
     - See `tests/fixtures/unique_test_data.py` for available generators

## Important Configuration

### Environment Variables
- Backend: Copy `.env.example` to `.env`
- Frontend: Copy `.env.local.example` to `.env.local`
- Never commit `.env` files

### Database Safety
- Test database includes safety suffix to prevent accidental production data deletion
- Migrations are versioned with Alembic
- Always review migrations before applying

### API Integration
- Frontend API client at `frontend/lib/api.ts`
- Backend API docs available at `/docs` when running
- CORS configured for local development

## Key Documentation

### New Developer Onboarding
- **`docs/architecture/new-developer-guide.md`** - **COMPLETE architecture guide for new developers**
- **`docs/architecture/quick-reference.md`** - **Essential patterns and commands**

### Project Overview & State
- `docs/project-overview/01_core_project_info.md` - Mission, team structure, priorities
- `docs/architecture/02_architecture_state.md` - Current architecture
- `docs/project-status/03_work-streams-status.md` - Active work status
- `docs/project-status/04_system-capabilities.md` - What's working/broken

### Current Priority Work
- `docs/project-status/Frontend Technical Debt Cleanup Checklist - Work Stream #13.md` - Critical blocker
- `docs/project-status/work-streams/Work Stream #10 - Two-Table Availability Design Removal.md` - Backend complete, frontend needs update

### Architecture References
- `docs/architecture/06_repository_pattern_architecture.md` - Repository implementation guide
- `docs/architecture/architecture-decisions.md` - All architectural decisions

When working on any feature, check these docs first for context and current state.

## Frontend Logging Standards

### CRITICAL: Use Proper Logging, NOT console.log

**Frontend code MUST use the centralized logger, NOT console.log**:

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

**Why this matters**:
- Production builds strip debug logs automatically
- Centralized control via localStorage ('log-level')
- Structured logging with context
- Performance optimized
- Consistent formatting

**Logger features**:
- `logger.debug()` - Development only, stripped in production
- `logger.info()` - General information
- `logger.warn()` - Warnings that should be addressed
- `logger.error()` - Errors that need immediate attention
- Second parameter accepts context object for additional data

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
6. Generate migration: `alembic revision -m "description"`
7. Add tests in `backend/tests/`
8. Update frontend types and API client
9. Implement UI components

### Performance Optimization
- Use the monitoring middleware data at `/metrics/performance`
- Profile slow queries with SQLAlchemy logging
- Leverage caching for read-heavy operations
- Use database indexes (already configured for common queries)

### Debugging
- Backend logs are comprehensive with proper formatting
- Frontend console logs should be removed before committing
- Use pytest's `-vv` flag for detailed test output
- Check `/health` endpoint for system status
