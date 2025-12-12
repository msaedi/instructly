# InstaInstru Architecture Guide for New Developers

Welcome to InstaInstru! This guide will get you up to speed on our architecture, patterns, and development practices.

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack](#technology-stack)
4. [Core Architectural Patterns](#core-architectural-patterns)
5. [Directory Structure](#directory-structure)
6. [Development Workflow](#development-workflow)
7. [Key Concepts](#key-concepts)
8. [Common Tasks](#common-tasks)
9. [Testing Strategy](#testing-strategy)
10. [Deployment & Infrastructure](#deployment--infrastructure)

## Project Overview

InstaInstru is the "Uber of instruction" - a marketplace platform for instantly booking private instructors in NYC.

### Mission
Building for **MEGAWATTS of energy allocation** - quality over speed, scalable architecture from day one.

### Current State
- **~96% Complete** - Instructor features work, student booking ready for implementation
- **1415+ Tests Passing** (100% test coverage)
- **Production Ready** - Database safety, Redis infrastructure, monitoring

## Architecture Overview

InstaInstru follows **Clean Architecture** principles with clear separation of concerns:

```
┌─────────────────────────────────────────────────┐
│                 Frontend (Next.js)              │
│           React Query + TypeScript              │
└─────────────────┬───────────────────────────────┘
                  │ HTTP/JSON API
┌─────────────────▼───────────────────────────────┐
│              Backend (FastAPI)                  │
│  ┌─────────────────────────────────────────────┐ │
│  │            Routes Layer                     │ │  ← HTTP Endpoints
│  └─────────────┬───────────────────────────────┘ │
│  ┌─────────────▼───────────────────────────────┐ │
│  │           Services Layer                    │ │  ← Business Logic
│  └─────────────┬───────────────────────────────┘ │
│  ┌─────────────▼───────────────────────────────┐ │
│  │         Repositories Layer                  │ │  ← Data Access
│  └─────────────┬───────────────────────────────┘ │
│  ┌─────────────▼───────────────────────────────┐ │
│  │            Models Layer                     │ │  ← Database Schema
│  └─────────────────────────────────────────────┘ │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│          Infrastructure Layer                   │
│     PostgreSQL + Redis + Celery + Monitoring   │
└─────────────────────────────────────────────────┘
```

## Technology Stack

### Backend
- **FastAPI** - Modern Python web framework with automatic OpenAPI docs
- **SQLAlchemy** - ORM with async support
- **PostgreSQL** - Primary database (Supabase)
- **Redis** - Caching, sessions, Celery broker (Render Redis)
- **Celery** - Background task processing
- **Pydantic** - Data validation and serialization
- **Alembic** - Database migrations

### Frontend
- **Next.js 15** - React framework with App Router
- **TypeScript** - Type safety
- **Tailwind CSS v4** - Styling
- **React Query (TanStack Query v5)** - Data fetching and caching
- **React Hook Form** - Form management

### Infrastructure
- **Render** - Backend hosting
- **Supabase** - PostgreSQL database
- **GitHub Actions** - CI/CD
- **Prometheus + Grafana** - Monitoring

## Core Architectural Patterns

### 1. Repository Pattern (100% Implemented)
All data access goes through repositories for testability and separation of concerns:

```python
# ✅ CORRECT
class BookingService(BaseService):
    def create_booking(self, booking_data: dict) -> Booking:
        return self.repository.create_booking(booking_data)

# ❌ WRONG - Direct database access
def create_booking(booking_data: dict) -> Booking:
    return db.query(Booking).filter(...).first()
```

### 2. Service Layer Pattern
Business logic is encapsulated in services:

```python
class BookingService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.repository = BookingRepository(db)
        self.conflict_checker = ConflictChecker(db)

    @measure_operation
    def create_booking(self, booking_data: dict) -> Booking:
        # Validation, business rules, orchestration
        with self.transaction():
            return self.repository.create_booking(booking_data)
```

### 3. Dependency Injection
Services are injected via FastAPI's dependency system:

```python
@router.post("/bookings/", response_model=BookingResponse)
async def create_booking(
    booking_data: BookingCreate,
    booking_service: BookingService = Depends(get_booking_service)
):
    return booking_service.create_booking(booking_data.model_dump())
```

### 4. Response Models (Mandatory)
**ALL endpoints MUST use Pydantic response models** - enforced by automated testing:

```python
# ✅ CORRECT
@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int) -> UserResponse:
    return UserResponse(**user_data)

# ❌ WRONG - Will fail CI/CD
@router.get("/users/{user_id}")
async def get_user(user_id: int):
    return {"id": user_id, "name": "John"}  # Raw dict - FORBIDDEN
```

### 5. RBAC (Role-Based Access Control)
Permission-based access control throughout the system:

```python
# Use permissions, NOT roles
@router.get("/admin/dashboard")
async def admin_dashboard(
    current_user: User = Depends(require_permission(PermissionName.ACCESS_MONITORING))
):
    return dashboard_data
```

## Directory Structure

### Backend (`/backend`)
```
backend/
├── app/
│   ├── routes/          # FastAPI route handlers
│   ├── services/        # Business logic layer
│   ├── repositories/    # Data access layer
│   ├── models/          # SQLAlchemy database models
│   ├── schemas/         # Pydantic request/response models
│   ├── core/            # Configuration, constants, utilities
│   ├── middleware/      # Custom middleware (auth, rate limiting)
│   └── main.py          # FastAPI application setup
├── tests/               # Comprehensive test suite
├── scripts/             # Database setup, migration scripts
└── alembic/             # Database migration files
```

### Frontend (`/frontend`)
```
frontend/
├── src/
│   ├── app/             # Next.js App Router pages
│   ├── components/      # Reusable React components
│   ├── hooks/           # Custom React hooks
│   ├── lib/             # Utilities, API client, React Query setup
│   ├── types/           # TypeScript interfaces
│   └── utils/           # Helper functions
└── public/              # Static assets
```

## Development Workflow

### 1. Setting Up Development Environment

**Backend Setup:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Database setup (safe by default - uses INT database)
python scripts/prep_db.py

# Start backend
./run_backend.py  # Automatically uses STG database
```

**Frontend Setup:**
```bash
cd frontend
npm install
npm run dev
```

### 2. Making Changes

1. **Create feature branch:** `git checkout -b feature/your-feature`
2. **Write tests first:** Add tests in `/tests` directory
3. **Implement feature:** Follow architectural patterns
4. **Run tests:** `pytest -v` (uses INT database safely)
5. **Check API contracts:** `python -m tests.test_api_contracts`
6. **Commit:** Pre-commit hooks run automatically

### 3. Pre-commit Validation
The following run automatically on commit:
- Code formatting (Black, isort)
- Type checking (mypy)
- API contract validation
- Basic test validation

## Key Concepts

### Database Safety System
**Critical:** We use a three-tier database system to prevent production accidents:

1. **INT (Integration Test)** 🟢 - Default, safe for drops/resets
2. **STG (Staging)** 🟡 - Local development, preserves data
3. **PROD (Production)** 🔴 - Requires confirmation, protected

```bash
# Safe operations (default to INT)
pytest -v                    # Uses INT
python scripts/some_script.py # Uses INT

# Local development (use STG)
./run_backend.py             # Uses STG automatically

# Production (requires confirmation)
USE_PROD_DATABASE=true alembic upgrade head  # Prompts for confirmation
```

### Time-Based Booking Architecture
**No Slot IDs** - Bookings reference time directly:

```python
# ✅ CORRECT - Time-based
Booking(
    instructor_id=123,
    booking_date=date(2024, 1, 15),
    start_time=time(9, 0),
    end_time=time(10, 0)
)

# ❌ WRONG - Slot ID reference (old architecture)
Booking(availability_slot_id=456)  # This field doesn't exist
```

### React Query Caching (Frontend)
**Mandatory** - All API calls must use React Query:

```jsx
// ✅ CORRECT
const { data, isLoading } = useQuery({
  queryKey: queryKeys.instructors.search({ service: 'yoga' }),
  queryFn: () => queryFn('/api/instructors/search?service=yoga'),
  staleTime: 1000 * 60 * 5, // 5 minutes
});

// ❌ WRONG
useEffect(() => {
  fetch('/api/instructors/search?service=yoga')
    .then(res => res.json())
    .then(setData);
}, []);
```

## Common Tasks

### Adding a New API Endpoint

1. **Create Response Model:**
```python
# app/schemas/my_responses.py
class MyFeatureResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
```

2. **Add Route:**
```python
# app/routes/my_feature.py
@router.get("/my-feature/{id}", response_model=MyFeatureResponse)
async def get_my_feature(
    id: int,
    service: MyFeatureService = Depends(get_my_feature_service)
) -> MyFeatureResponse:
    data = service.get_feature(id)
    return MyFeatureResponse(**data)
```

3. **Test API Contract:**
```bash
python -m tests.test_api_contracts  # Should show 0 violations
```

### Adding a New Service

1. **Create Service:**
```python
# app/services/my_service.py
class MyService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db)
        self.repository = MyRepository(db)

    @measure_operation  # Required for monitoring
    def get_data(self, params: dict) -> dict:
        with self.transaction():  # Use for write operations
            return self.repository.get_data(params)
```

2. **Create Repository:**
```python
# app/repositories/my_repository.py
class MyRepository(BaseRepository):
    def get_data(self, params: dict) -> dict:
        return self.db.query(MyModel).filter(...).all()
```

3. **Add Dependency:**
```python
# app/dependencies/my_deps.py
def get_my_service(db: Session = Depends(get_db)) -> MyService:
    return MyService(db)
```

### Database Migrations

```bash
# Create migration
alembic revision -m "Add my_table"

# Apply migrations (safe - uses INT database)
alembic upgrade head

# For staging
USE_STG_DATABASE=true alembic upgrade head

# For production (requires confirmation)
USE_PROD_DATABASE=true alembic upgrade head
```

## Testing Strategy

### Test Organization
- **Unit Tests:** `tests/unit/` - Fast, isolated
- **Integration Tests:** `tests/integration/` - Database + services
- **Route Tests:** `tests/routes/` - API endpoint testing
- **Contract Tests:** `tests/test_api_contracts.py` - Response model compliance

### Running Tests
```bash
# All tests (uses INT database safely)
pytest -v

# Specific categories
pytest -m unit           # Unit tests only
pytest -m integration    # Integration tests only
pytest -k "booking"      # Tests matching "booking"

# With coverage
pytest --cov=app --cov-report=html
```

### Test Database Safety
Tests automatically use the INT database - **no production risk**.

## Deployment & Infrastructure

### Production Services (Render)
- **API:** instructly-backend (Web Service)
- **Redis:** instructly-redis ($7/month)
- **Celery Worker:** instructly-celery
- **Celery Beat:** instructly-celery-beat
- **Flower:** instructly-flower (monitoring)
- **Database:** Supabase PostgreSQL

### Monitoring
- **Performance:** `/ops/performance` endpoint
- **Redis Stats:** `/api/redis/stats`
- **Database Pool:** `/api/database/pool-status`
- **Health Checks:** `/health`, `/health/lite`
- **Prometheus:** `/metrics/prometheus`

### Key Environment Variables
```bash
# Database (production)
DATABASE_URL=postgresql://...

# Redis
REDIS_URL=redis://...

# API Keys
RESEND_API_KEY=...
OPENAI_API_KEY=...

# Security
SECRET_KEY=...
```

## Best Practices

### 1. Code Quality
- **Use type hints:** All functions should have proper typing
- **Follow naming conventions:** Snake_case for Python, camelCase for TypeScript
- **Document complex logic:** Add docstrings and comments
- **Keep functions small:** Single responsibility principle

### 2. Error Handling
```python
# Use proper HTTP exceptions
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found"
)

# Log errors appropriately
logger.error(f"Error processing request: {str(e)}", exc_info=True)
```

### 3. Security
- **Never log secrets:** Use appropriate log levels
- **Validate input:** Use Pydantic models for all inputs
- **Use permissions:** Not role-based checks
- **Rate limiting:** Implemented automatically

### 4. Performance
- **Use caching:** Redis for expensive operations
- **Optimize queries:** Avoid N+1 problems
- **Use pagination:** For large datasets
- **Monitor performance:** Use `@measure_operation` decorator

## Getting Help

### Documentation
- **API Guide:** `docs/api/instainstru-api-guide.md`
- **API Standards:** `docs/api/api-standards-guide.md`
- **Architecture Details:** `docs/architecture/`
- **CLAUDE.md:** Project-specific instructions

### Key Files for Reference
- **Service Patterns:** `app/services/booking_service.py` (excellent example)
- **Repository Pattern:** `app/repositories/booking_repository.py`
- **Route Structure:** `app/routes/bookings.py`
- **Response Models:** `app/schemas/booking_responses.py`
- **Testing Examples:** `tests/integration/services/test_booking_service.py`

### Common Pitfalls
1. **Don't bypass the repository pattern** - Always use `service.repository.method()`
2. **Don't return raw dictionaries** - Use response models (enforced by CI)
3. **Don't access production database accidentally** - Use database safety system
4. **Don't forget permissions** - Use `require_permission()` not role checks
5. **Don't skip testing** - Write tests for new functionality

Welcome to the team! This architecture is designed for scale, safety, and maintainability. When in doubt, follow the patterns shown in existing code and ask questions.
