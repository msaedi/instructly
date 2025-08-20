# InstaInstru Architecture State
*Last Updated: August 2025*

## 🗏 Service Layer Architecture (100% COMPLETE)

Service layer fully implemented with complete separation of concerns. All routes use services for business logic, all services use repositories for data access.

### Service Excellence Metrics
- **16 services** at 8.5/10 average quality
- **All singletons eliminated** - 100% dependency injection
- **98 performance metrics** added (79% coverage)
- **All methods under 50 lines**
- **Test coverage**: 79%

### Service Directory Structure
```
backend/app/services/
├── base.py                    # BaseService with transaction management
├── instructor_service.py      # Instructor profile CRUD
├── availability_service.py    # Week-based availability management
├── booking_service.py         # Full booking lifecycle
├── cache_service.py           # Redis/DragonflyDB integration
├── notification_service.py    # Email notifications via Resend
├── conflict_checker.py        # Booking conflict detection
├── slot_manager.py           # Time slot CRUD
├── week_operation_service.py  # Week copy and patterns
├── bulk_operation_service.py  # Bulk availability updates
├── auth_service.py           # Authentication operations
├── password_reset_service.py  # Password reset flow
└── [other services...]
```

### Key Service Features
1. **BaseService Class**: Transaction management, error handling, repository integration
2. **Dependency Injection**: All services via FastAPI dependencies
3. **Business Logic**: Routes only handle HTTP, services handle logic
4. **Performance Monitoring**: @measure_operation decorator, slow query detection

## 🗄️ Repository Layer (100% COMPLETE)

Repository Pattern fully implemented across all services with pre-commit enforcement.

### Repository Status
- **12 repositories** implemented
- **100% service coverage**
- **Zero direct DB queries** in services
- **Pre-commit hooks** prevent regression

### Core Repositories
- SlotManagerRepository (13 methods, 97% coverage)
- AvailabilityRepository (15+ methods)
- ConflictCheckerRepository (13 methods, 99% coverage)
- BookingRepository (Complete CRUD)
- UserRepository (User + timezone management)
- PermissionRepository (RBAC with 30 permissions)
- FavoritesRepository (Student favorites)

## 🎨 Frontend Architecture (SERVICE-FIRST COMPLETE)

### Current State
- **270+ services** operational
- **Service-first architecture** implemented
- **React Query mandatory** for all data fetching
- **Technical debt eliminated**

### Service Pattern
```typescript
export const availabilityService = {
  getWeek: (instructorId, date) => api.get(`/availability/week/${instructorId}/${date}`),
  saveWeek: (data) => api.post('/availability/week', data)
};
```

### Key Features
- Natural Language Search (10x accuracy improvement)
- Global useAuth hook for authentication
- Search history system with tracking
- Optimistic UI updates throughout

## 📊 Database Schema Architecture

### Current Migrations (7 Total)
1. **001_initial_schema** - Users, auth, indexes
2. **002_instructor_system** - Profiles, services (soft delete)
3. **003_availability_system** - Single-table design (no InstructorAvailability)
4. **004_booking_system** - Bookings, password reset (no FK to slots)
5. **005_performance_indexes** - Composite indexes
6. **006_final_constraints** - Check constraints
7. **007_remove_booking_slot_dependency** - True layer independence

### Key Architectural Decisions
1. **One-Way Relationships** - Bookings reference slots (nullable), not vice versa
2. **Single-Table Availability** - Just availability_slots table
3. **Time-Based Booking** - No slot IDs, just {instructor_id, date, start_time, end_time}
4. **Soft Delete** - Services have is_active flag
5. **No PostgreSQL Enums** - VARCHAR with CHECK constraints
6. **ULID IDs** - All IDs are 26-character strings

### Database Relationships
```
Users (1) ──────> (0..1) InstructorProfile
  │                              │
  │                              ├─> (0..*) Services
  │                              │
  ├─> (0..*) Bookings            └─> (0..*) AvailabilitySlots
  │                                         (no relationship)
  ├─> (0..*) PasswordResetTokens
  └─> (0..*) UserFavorites
```

## 📌 API Architecture

### Route Organization
```
backend/app/routes/
├── auth.py                 # Registration, login, current user
├── instructors.py          # Instructor profiles and services
├── availability_windows.py # Availability management
├── bookings.py            # Booking operations
├── public_availability.py # Public API endpoints (no auth)
└── [other routes...]
```

### Request/Response Flow
```
Client Request
     ↓
Route Handler (thin controller)
     ↓
Service Layer (business logic)
     ↓
Repository Layer (data access)
     ↓
Database/Cache Layer
     ↓
Response Model (Pydantic)
     ↓
Client Response
```

## 🛏 Architectural Patterns

### Implemented Patterns
1. **Service Layer Pattern** - Business logic centralization
2. **Repository Pattern** - Data access abstraction
3. **Factory Pattern** - Repository creation
4. **Circuit Breaker** - Cache failure protection
5. **Cache-Aside** - Check cache, load on miss
6. **Layer Independence** - Availability and bookings separate
7. **Dependency Injection** - No global instances
8. **Service-First Frontend** - 270+ services

## 🔐 Security & Privacy

### Security Implementation
- **bcrypt** password hashing
- **JWT authentication** with RBAC (30 permissions)
- **Pydantic validation** on all inputs
- **Rate limiting** across endpoints
- **SSL/HTTPS** in production
- **Database safety** - 3-tier protection (INT/STG/PROD)

### Privacy Framework
- **GDPR compliance** with data export
- **Right to be Forgotten** implementation
- **Automated retention** via Celery
- **IP hashing** for analytics
- **Schema-owned privacy** transformation

## 📈 Performance Architecture

### Current Optimizations
- **Database indexes** on common queries
- **Redis caching** with 80%+ hit rate
- **Eager loading** prevents N+1 queries
- **Connection pooling** optimized
- **Response times** <100ms average
- **Query monitoring** with slow query alerts

### Infrastructure
- **Backend**: Render ($25/month)
- **Frontend**: Vercel
- **Database**: Supabase PostgreSQL
- **Cache**: Redis ($7/month)
- **Celery**: Background workers
- **Total Cost**: $53/month

## 🚨 Critical Architecture Issues

### Resolved ✅
- **Layer Independence** (Work Stream #9) - Complete
- **Single-Table Design** (Work Stream #10) - Backend complete
- **Public API** (Work Stream #12) - Complete
- **Repository Pattern** - 100% implementation
- **Frontend Technical Debt** - Service-first transformation complete

### Remaining Issues
- **Frontend components** still assume slot IDs exist in some places
- **Payment integration** not implemented
- **Reviews/ratings** system missing

## 🎯 Architecture Maturity

### Backend: A+ Grade
- Service Layer ✅
- Repository Pattern ✅
- Database Schema ✅
- Caching Strategy ✅
- Authentication/RBAC ✅
- Error Handling ✅
- Test Infrastructure ✅
- Performance Monitoring ✅

### Frontend: B+ Grade
- Service-First Architecture ✅
- React Query Integration ✅
- Natural Language Search ✅
- Some slot ID assumptions remain ⚠️

## 📝 Architecture Decision Records

Key decisions documented:
1. One-Way Relationship Design
2. Repository Pattern Implementation
3. Soft Delete Strategy
4. Cache Strategy
5. Layer Independence
6. Single-Table Design
7. Time-Based Booking
8. No Singletons - DI Only
9. RBAC over Role-Based
10. Database Safety 3-Tier
11. Privacy-First Analytics
12. PostgreSQL UPSERT for Race Conditions
13. Render Redis Migration
