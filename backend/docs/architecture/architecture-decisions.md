# InstaInstru Architecture Decisions
*Last Updated: July 6, 2025 - Post Session v63 & Work Stream #12 Completion*

## Overview

This document consolidates all architectural decisions made during the development of InstaInstru. Each decision includes context, rationale, implementation details, and consequences.

## Table of Contents

1. [One-Way Relationship Design (Bookings → Slots)](#1-one-way-relationship-design)
2. [Service Layer Architecture](#2-service-layer-architecture)
3. [Repository Pattern Implementation](#3-repository-pattern-implementation)
4. [Soft Delete Strategy](#4-soft-delete-strategy)
5. [Cache Strategy with DragonflyDB](#5-cache-strategy)
6. [PostgreSQL Enum Avoidance](#6-postgresql-enum-avoidance)
7. [Sync vs Async Architecture](#7-sync-vs-async-architecture)
8. [Migration Squashing Strategy](#8-migration-squashing-strategy)
9. [Layer Independence (Availability-Booking Separation)](#9-layer-independence)
10. [Single-Table Availability Design](#10-single-table-availability-design)
11. [Frontend Architecture Discovery](#11-frontend-architecture-discovery)
12. [Public API Design](#12-public-api-design)

---

## 1. One-Way Relationship Design

**Date**: December 21, 2024
**Status**: Evolved (see Work Stream #9)

### Context
When designing the relationship between bookings and availability slots, we faced a decision about bidirectional vs one-way relationships.

### Decision
Implement a **one-way relationship** where:
- Bookings reference availability slots via `bookings.availability_slot_id`
- Availability slots do NOT reference bookings
- **Evolution**: Work Stream #9 later removed even this FK constraint for true independence

### Rationale
1. **Single Source of Truth**: Bookings table is the only source for whether a slot is booked
2. **Cleaner Transactions**: Only one table to update when creating/cancelling bookings
3. **Better Performance**: Simple indexed lookup for slot availability
4. **Flexibility**: Booking status belongs to the booking, not the slot
5. **No Circular Dependencies**: Avoids SQLAlchemy relationship complexities

### Implementation
```python
# Booking model has:
availability_slot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

# AvailabilitySlot model has NO booking reference
```

### Consequences
- ✅ Simpler data model
- ✅ No data synchronization issues
- ✅ Better transaction isolation
- ❌ Cannot directly access booking from slot (must query)

---

## 2. Service Layer Architecture

**Date**: Early December 2024
**Status**: Implemented

### Context
Routes were becoming thick with business logic, making testing and maintenance difficult.

### Decision
Implement a comprehensive **Service Layer** pattern where:
- All business logic lives in service classes
- Routes are thin controllers that only handle HTTP concerns
- Services manage transactions and coordinate operations

### Rationale
1. **Separation of Concerns**: HTTP handling separate from business logic
2. **Testability**: Services can be tested without HTTP context
3. **Reusability**: Business logic can be called from multiple endpoints
4. **Transaction Management**: Centralized in services

### Implementation
```python
# Route (thin controller)
@router.post("/bookings")
async def create_booking(data: BookingCreate, user: User = Depends(get_current_user)):
    return BookingService(db).create_booking(user, data)

# Service (business logic)
class BookingService(BaseService):
    def create_booking(self, user: User, data: BookingCreate):
        # All business logic here
```

### Consequences
- ✅ Clean architecture
- ✅ 100% of routes use services
- ✅ Easier unit testing
- ✅ Consistent patterns

---

## 3. Repository Pattern Implementation

**Date**: Sessions v35-v41, completed v59
**Status**: Implemented (100% coverage)

### Context
Services were mixing business logic with data access, making them hard to test and maintain.

### Decision
Implement the **Repository Pattern** for all data access:
- Repositories handle all database queries
- Services focus on business logic only
- Repository pattern provides abstraction over data source

### Rationale
1. **Clean Separation**: Business logic vs data access
2. **Testability**: Easy to mock repositories
3. **Flexibility**: Can change data source without affecting business logic
4. **Consistency**: Standardized data access patterns

### Implementation
```python
class BookingService(BaseService):
    def __init__(self, db: Session, repository: Optional[BookingRepository] = None):
        self.repository = repository or RepositoryFactory.create_booking_repository(db)

    def create_booking(self, user: User, data: BookingCreate):
        # Use repository for data access
        slot = self.repository.get_slot(data.slot_id)
```

### Consequences
- ✅ 100% implementation across all 7 services
- ✅ Improved test coverage
- ✅ Cleaner service code
- ✅ Future flexibility for data source changes
- ✅ Fixed N+1 query problem (99.5% improvement via InstructorProfileRepository)

---

## 4. Soft Delete Strategy

**Date**: December 2024
**Status**: Implemented

### Context
When instructors update profiles and remove services, we need to handle services that have existing bookings.

### Decision
Implement **soft delete** using `is_active` flag:
- Services with bookings: Set `is_active = false`
- Services without bookings: Hard delete from database
- Unique constraint only on active services

### Rationale
1. **Referential Integrity**: Preserves booking history
2. **Data Consistency**: No orphaned bookings
3. **Audit Trail**: Can see historical services
4. **Reactivation**: Services can be re-enabled

### Implementation
```python
class Service(Base):
    is_active: Mapped[bool] = mapped_column(default=True)

    # Partial unique index
    __table_args__ = (
        Index('unique_instructor_skill_active', 'instructor_profile_id', 'skill',
              unique=True, postgresql_where=text('is_active = true')),
    )
```

### Consequences
- ✅ Maintains data integrity
- ✅ Preserves booking history
- ✅ Allows service reactivation
- ❌ Slightly more complex queries (must filter by is_active)

---

## 5. Cache Strategy with DragonflyDB

**Date**: December 2024
**Status**: Implemented

### Context
Database queries were taking 15-40ms, impacting user experience for frequently accessed data.

### Decision
Implement caching with **DragonflyDB** (Redis-compatible):
- Cache-aside pattern
- Circuit breaker for resilience
- Automatic cache warming after updates
- TTL tiers based on data volatility

### Rationale
1. **Performance**: Sub-2ms reads for cached data
2. **DragonflyDB Benefits**: More memory efficient than Redis
3. **Resilience**: Circuit breaker prevents cascade failures
4. **Compatibility**: Drop-in Redis replacement

### Implementation
```python
class CacheService:
    def __init__(self):
        self.cache = redis.Redis(...)
        self.circuit_breaker = CircuitBreaker(threshold=5, timeout=60)

    def get(self, key: str) -> Optional[Any]:
        if self.circuit_breaker.is_open:
            return None
        # Cache logic...
```

### Results
- ✅ 91.67% cache hit rate
- ✅ 0.7-1.5ms read latency
- ✅ 45% reduction in response time
- ✅ Graceful degradation on cache failure

---

## 6. PostgreSQL Enum Avoidance

**Date**: December 2024
**Status**: Implemented

### Context
PostgreSQL ENUMs cause issues with SQLAlchemy migrations and serialization.

### Decision
Use **VARCHAR with CHECK constraints** instead of ENUMs:
- User roles as VARCHAR(10)
- Booking status as VARCHAR(20)
- All enums implemented as strings with constraints

### Rationale
1. **Migration Flexibility**: Can add/remove values easily
2. **SQLAlchemy Compatibility**: No serialization issues
3. **Simplicity**: Standard string handling
4. **Database Agnostic**: Works across different databases

### Implementation
```sql
CREATE TABLE users (
    role VARCHAR(10) NOT NULL CHECK (role IN ('student', 'instructor'))
);
```

### Consequences
- ✅ Easier migrations
- ✅ No SQLAlchemy enum issues
- ✅ Simple value additions
- ❌ Slightly more storage (negligible)

---

## 7. Sync vs Async Architecture

**Date**: Work Stream #6
**Status**: Decided - Stay Synchronous

### Context
Evaluated whether to migrate from sync to async for performance improvements.

### Decision
**Stay with synchronous architecture**:
- Current 124ms average response time is adequate
- Complexity of async not justified
- Performance gains would be minimal

### Rationale
1. **Current Performance Adequate**: 124ms is good for user experience
2. **Complexity Cost**: Async adds significant complexity
3. **Bottleneck Analysis**: Database is bottleneck, not Python
4. **Team Familiarity**: Team knows sync patterns well

### Benchmarks
- Sync: 124ms average
- Async estimate: 80-100ms
- Improvement: ~20-35% (not worth complexity)

### Consequences
- ✅ Simpler codebase
- ✅ Easier debugging
- ✅ Lower learning curve
- ❌ Some performance left on table

---

## 8. Migration Squashing Strategy

**Date**: December 2024, July 2025
**Status**: Implemented (twice)

### Context
Database migrations accumulated technical debt and showed our learning journey rather than ideal path.

### Decision
**Squash migrations** to show ideal schema evolution:
- First squash: 20 → 6 migrations
- Second squash (planned): Incorporate all learnings

### Rationale
1. **Clean History**: Shows intended design, not journey
2. **Faster Deployment**: Fewer migrations to run
3. **Better Documentation**: Clear progression
4. **No Production Data**: Can recreate from scratch

### Implementation Process
1. Analyze final schema state
2. Create logical groupings
3. Write migrations as if we knew final design
4. Archive original migrations

### Results
- ✅ Deployment time: 30s → 10s
- ✅ Clearer schema evolution
- ✅ Easier onboarding
- ✅ No evolutionary artifacts

---

## 9. Layer Independence (Availability-Booking Separation)

**Date**: Work Stream #9 (July 2025)
**Status**: Implemented ✅

### Context
System incorrectly coupled availability and booking operations, violating architectural principles.

### Decision
Implement **complete layer independence**:
- Availability operations NEVER check bookings
- Bookings exist independently of availability changes
- Remove FK constraint between bookings and availability_slots

### Rationale
1. **Architectural Purity**: Layers should be independent
2. **Business Logic**: Bookings are commitments that persist
3. **Simplicity**: No complex conflict checking
4. **User Trust**: Bookings remain valid

### "Rug and Person" Mental Model
```
Time:   9:00   9:30   10:00  10:30  11:00
Rug:    [======][======][======][======]
People:        [PERSON]

After removing rug:
Rug:    [======]              [======]
People:        [PERSON] ← Still there!
```

### Implementation
- Removed FK constraint via migration
- Updated all services to not check bookings
- Fixed 500+ tests to match new behavior

### Consequences
- ✅ True layer independence
- ✅ Simpler operations
- ✅ Bookings always honored
- ✅ Eliminated class of bugs

---

## 10. Single-Table Availability Design

**Date**: Work Stream #10 (July 2025)
**Status**: Backend Complete ✅, Frontend Pending

### Context
Two-table design (InstructorAvailability + AvailabilitySlots) causing bugs and complexity.

### Decision
Move to **single-table design**:
- Just availability_slots table
- Contains instructor_id, date, start_time, end_time
- No separate date-level entries

### Rationale
1. **Bug Prevention**: Eliminates duplicate key errors
2. **Simplicity**: No two-step operations
3. **Performance**: No joins needed
4. **Clear Semantics**: Has slots = available

### Current Problems Solved
- v49 duplicate key bug
- Complex cleanup operations
- Confusing empty states
- Unnecessary joins

### Implementation Status
- ✅ Backend: Fully migrated
- ❌ Frontend: Still uses old mental model

### Expected Benefits
- ✅ 40% less code in repositories
- ✅ Faster queries (no joins)
- ✅ Impossible to reproduce v49 bug
- ✅ Clearer mental model

---

## 11. Frontend Architecture Discovery

**Date**: Architecture Audit (July 2025)
**Status**: Discovered, Cleanup Planned

### Context
Work Stream #11 revealed the frontend carries massive technical debt and a critical misunderstanding about student features.

### Discovery
**Student features were never built** (not broken):
- Development pivoted to backend robustness before implementing student features
- Frontend has 3,000+ lines of technical debt from wrong mental model
- Missing public API endpoint for students

### Frontend Mental Model Problem
**Frontend Believes** (Wrong):
- Slots are database entities with IDs
- Complex operations needed for changes
- 600+ lines for what should be ~50

**Backend Reality** (Correct):
- Time ranges are simple data
- Direct saves work
- No tracking needed

### Decision
Create Work Stream #13 for **Frontend Technical Debt Cleanup**:
- Clean up instructor features
- Remove operation pattern
- Prepare for student features

### Consequences
- 🚨 Platform earns ZERO megawatts (no student booking)
- ✅ Clear path forward identified
- ✅ Backend excellence validated
- ❌ 5x slower development velocity

---

## 12. Public API Design

**Date**: July 2025
**Status**: Implemented ✅ (Work Stream #12)

### Context
All availability endpoints required authentication, preventing students from viewing instructor availability.

### Decision
Create **public availability endpoints** with configurable detail levels:
- `GET /api/public/instructors/{instructor_id}/availability`
- `GET /api/public/instructors/{instructor_id}/next-available`
- No authentication required
- Configurable privacy levels
- Cached for performance

### Rationale
1. **Core Functionality**: Students must see availability to book
2. **Quick Win**: 1-2 days to implement
3. **Unblocks Everything**: Enables A-Team testing
4. **Standard Practice**: Public data should have public endpoints

### Implementation Details
**Configurable Detail Levels**:
- **Full**: Complete time slots with start/end times
- **Summary**: Morning/afternoon/evening availability
- **Minimal**: Just yes/no availability boolean

**Configuration via Environment Variables**:
```bash
PUBLIC_AVAILABILITY_DAYS=30  # How many days to show (1-90)
PUBLIC_AVAILABILITY_DETAIL_LEVEL=full  # full/summary/minimal
PUBLIC_AVAILABILITY_SHOW_INSTRUCTOR_NAME=true
PUBLIC_AVAILABILITY_CACHE_TTL=300  # Cache duration in seconds
```

**Key Design Decisions**:
- No slot IDs exposed (enforces correct mental model)
- 5-minute caching balances freshness vs performance
- Excludes partial bookings for clarity
- Repository pattern maintained

### Results
- ✅ Students can view availability without account
- ✅ Unblocks student feature development
- ✅ Enables A-Team to design booking flow
- ✅ 37 tests passing with full coverage
- ✅ Platform can start earning megawatts!

---

## Meta-Decisions

### Documentation Strategy
- Consolidate related decisions into single documents
- Archive journey artifacts, keep only final state
- Document the "why" not just the "what"

### Technical Debt Approach
- Address before launch while no production data
- Prefer fundamental fixes over patches
- Use bugs as signals for architectural issues

### Quality Standards
- Launch when AMAZING, not when adequate
- Every decision must improve the platform
- Test coverage proves architectural soundness

### Communication Between Teams
- X-Team provides technical constraints
- A-Team provides UX decisions
- Neither team makes the other's decisions

---

## Current Platform State (Post v63)

### What's Working ✅
- **Backend Architecture**: A+ grade, clean and scalable
- **Instructor Features**: Beautiful UI with functionality
- **Repository Pattern**: 100% implementation
- **Performance**: 124ms average response time
- **Test Infrastructure**: 636 tests (73.6% passing)
- **Public API**: Students can view availability (Work Stream #12 complete)

### What's Missing ❌
- **Student Features**: 0% - never built (but no longer blocked!)
- **Frontend Architecture**: 3,000+ lines of technical debt
- **Complete Platform**: Only ~65% done (up from 60%)

### Critical Work Streams

**Completed**:
- Work Streams #1-11: All backend architecture complete
- Work Stream #12: Public Availability Endpoint ✅

**Active**:
- Work Stream #13: Frontend Technical Debt Cleanup (3-4 weeks)
- Work Stream #14: A-Team Collaboration (can now proceed with testing)

---

## Future Considerations

1. **API Versioning**: Will need strategy before v2 features
2. **Event Sourcing**: Consider for audit requirements
3. **Microservices**: Monolith works well for now
4. **Multi-tenancy**: If expanding beyond single market
5. **Metrics Expansion**: Only 1 method has decorator currently
6. **Production Hardening**: Rate limiting, monitoring, security audit

---

## Conclusion

These architectural decisions form the foundation of InstaInstru's technical excellence. Each decision was made considering long-term maintainability, developer experience, system performance, and business requirements.

**Critical Insight**: The discovery that student features were never built (not broken) fundamentally reframes our work. We have excellent backend architecture and working instructor features, but the platform cannot fulfill its core purpose without student booking capability.

**The Path Forward**:
1. ~~Create public API endpoint~~ ✅ COMPLETE (unblocked everything)
2. Clean up frontend technical debt (enables velocity)
3. Collaborate with A-Team (get UX decisions)
4. Build student features (complete the vision)

**Remember**: We're building for MEGAWATTS! A platform that only serves instructors earns ZERO energy. The architecture is sound, but incomplete. Excellence in execution will earn our energy allocation. ⚡🚀
