# InstaInstru Architecture Decisions
*Last Updated: August 2025*

## Core Architecture Decisions

| Decision | Status | Implementation | Impact |
|----------|--------|---------------|---------|
| **One-Way Relationships** | ✅ Active | Bookings reference slots (nullable), slots don't reference bookings | Prevents circular dependencies, cleaner transactions |
| **Service Layer Pattern** | ✅ Active | All business logic in services, thin routes | 100% routes use services, clean separation |
| **Repository Pattern** | ✅ Active | All data access via repositories, no direct DB in services | 100% implementation, pre-commit enforcement |
| **Soft Delete Strategy** | ✅ Active | `is_active` flag for services with bookings | Preserves referential integrity |
| **Cache Strategy** | ✅ Active | Redis with cache-aside pattern, circuit breaker | 80%+ hit rate, <2ms reads |
| **No PostgreSQL Enums** | ✅ Active | VARCHAR with CHECK constraints | Avoids SQLAlchemy issues |
| **Stay Synchronous** | ✅ Active | No async migration, 124ms adequate | Simpler codebase, easier debugging |
| **Layer Independence** | ✅ Active | Availability operations never check bookings | True architectural separation |
| **Single-Table Availability** | ✅ Active | Just availability_slots table | No InstructorAvailability table, simpler queries |
| **ULID Architecture** | ✅ Active | All IDs are 26-char strings | Better sortability than UUIDs |
| **RBAC System** | ✅ Active | 30 permissions, not role-based | `require_permission()` not role checks |
| **Database Safety** | ✅ Active | 3-tier INT/STG/PROD | Default to INT, production requires confirmation |
| **Clean Break Philosophy** | ✅ Active | No backward compatibility during dev | Edit existing migrations, don't create new |
| **Time-Based Booking** | ✅ Active | No slot IDs, just time ranges | `{instructor_id, date, start_time, end_time}` |
| **No Singletons** | ✅ Active | Dependency injection everywhere | All services use DI pattern |
| **Schema-Owned Privacy** | ✅ Active | Schemas handle privacy transformation | `InstructorInfo.from_user()` returns "FirstName L." |
| **React Query Mandatory** | ✅ Active | All frontend data fetching uses React Query | No fetch() or useEffect for API calls |

## Defensive Measures (Preventing Regression)

| Hook | Purpose | Enforcement |
|------|---------|-------------|
| **check-repository-pattern** | Blocks `db.query()` in services | Pre-commit + CI/CD |
| **check-timezone-usage** | Blocks `date.today()` in user code | Pre-commit + CI/CD |
| **api-contracts** | Ensures Pydantic response models | Pre-commit + CI/CD |

## Key Implementation Patterns

### Repository Pattern
```python
# ✅ CORRECT
self.repository.get_user_by_id(user_id)

# ❌ BLOCKED by pre-commit
self.db.query(User).filter(...)
```

### Service Pattern
```python
class BookingService(BaseService):
    def __init__(self, db, repository=None):
        self.repository = repository or BookingRepository(db)

    @measure_operation
    def create_booking(self, data):
        with self.transaction():
            # Business logic here
```

### Time-Based Booking
```python
# No slot IDs, just time ranges
booking = {
    "instructor_id": instructor_id,
    "booking_date": date,
    "start_time": "09:00",
    "end_time": "10:00",
    "service_id": service_id
}
```

### Privacy Pattern
```python
class InstructorInfo:
    @classmethod
    def from_user(cls, user):
        # Never expose full last name
        return cls(
            first_name=user.first_name,
            last_initial=user.last_name[0] if user.last_name else ""
        )
```

## Migration Strategy

- **Development Phase**: Modify existing migrations in `alembic/versions/`
- **No New Migrations**: Don't use `alembic revision` until production
- **Clean History**: Squash migrations to show ideal path
- **Test with INT**: `python scripts/prep_db.py int`

## Infrastructure Decisions

| Component | Choice | Reason |
|-----------|--------|--------|
| **Database** | PostgreSQL via Supabase | PostGIS + pgvector support |
| **Cache** | Single Redis instance | Handles cache + Celery + sessions |
| **Background Jobs** | Celery + Beat | Async processing, scheduled tasks |
| **Email** | Resend API | Simple, reliable |
| **Assets** | Cloudflare R2 | 80% bandwidth reduction |
| **Hosting** | Render + Vercel | $53/month total |
| **CI Database** | Custom image with PostGIS + pgvector | Required for spatial + NL search |

## Critical Rules

1. **ALL IDs are ULIDs** - 26-character strings, never integers
2. **No fetch() in frontend** - React Query only
3. **No db.query() in services** - Repositories only
4. **No date.today() in user code** - Use timezone-aware utilities
5. **No slot IDs** - Time-based booking only
6. **No new migrations during dev** - Modify existing files
7. **Default to INT database** - Production requires explicit confirmation
