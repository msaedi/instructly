# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InstaInstru is a marketplace platform for instantly booking private instructors in NYC. It's a full-stack application with:
- **Backend**: FastAPI (Python) with PostgreSQL, SQLAlchemy, and DragonflyDB caching
- **Frontend**: Next.js 15 with TypeScript and Tailwind CSS v4
- **Architecture**: Clean architecture with separated services, repositories, and route handlers

## Current Project State & Priorities

### Critical Context
- **Mission**: Building for MEGAWATTS of energy allocation - quality over speed
- **Platform Status**: ~65% complete - instructor features work, student booking NOT IMPLEMENTED
- **Test Coverage**: Backend tests need fixes (specific_date field issues), new search analytics tests passing
- **Major Blocker**: Frontend has 3,000+ lines of technical debt from wrong mental model

### Immediate Priorities
1. **Frontend Technical Debt (Work Stream #13)**: Delete operation pattern, fix mental model
2. **Student Booking Features**: Core functionality missing (not broken, never built)
3. **Redis Migration**: ✅ COMPLETE: Migrated from Upstash to Render Redis ($7/month)
4. **Search Analytics**: ✅ COMPLETE: Full tracking system with Celery async processing
5. **Service Metrics**: ✅ COMPLETE: All service methods already have @measure_operation decorators

### Key Architectural Decisions
- **NO SLOT IDs**: Time-based booking only (instructor_id, date, start_time, end_time)
- **Layer Independence**: Bookings don't reference availability slots (Work Stream #9)
- **Single-Table Design**: Just availability_slots table (no InstructorAvailability)
- **Repository Pattern**: 100% implemented across all services
- **RBAC System**: Full Role-Based Access Control with permissions, NOT simple role checking
- **Redis Architecture**: Single Redis instance for caching, Celery broker, and sessions

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
- Public API complete: GET /api/public/instructors/{id}/availability
- Repository Pattern: 100% implementation (7/7 services)
- N+1 query fixed: 99.5% improvement in InstructorProfileRepository
- 5 production bugs found and fixed through testing
- Search Analytics: Complete tracking system with async Celery processing
- Redis Migration: Moved from Upstash to Render, 89% reduction in operations
- RBAC System: Full permission-based access control implemented
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
- Celery runs analytics every 3 hours, search metrics hourly
- All services configured with optimized settings for cost efficiency
- Monitoring endpoints require ACCESS_MONITORING permission

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

## Essential Commands

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

# Database operations
alembic upgrade head            # Apply migrations
alembic revision -m "message"   # Create new migration
python scripts/reset_and_seed_yaml.py  # Reset and seed DB

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

5. **Testing Approach**:
   - Separate test database with safety checks
   - Fixtures for common test data
   - Async test support with pytest-asyncio

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
