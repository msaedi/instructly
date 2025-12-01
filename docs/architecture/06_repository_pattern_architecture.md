# InstaInstru Repository Pattern Architecture
*Last Updated: November 2025 (Session v117)*

## 🏗️ Repository Pattern Overview

The Repository Pattern separates data access logic from business logic. **100% implemented** across all services with defensive measures preventing regression.

### Architecture Layers
```
┌─────────────────┐
│   API Routes    │
├─────────────────┤
│    Services     │ ← Business Logic & Transaction Management
├─────────────────┤
│  Repositories   │ ← Data Access Layer (100% implemented) ✅
├─────────────────┤
│   Database      │
└─────────────────┘
```

### Key Benefits
- ✅ Services focus on business logic, repositories handle data
- ✅ Easy to mock for unit tests
- ✅ Standardized patterns across all services
- ✅ Can change data source without affecting business logic
- ✅ Pre-commit hooks prevent architectural regression

## 📦 Repository Infrastructure

### BaseRepository (Abstract Foundation)
**Location**: `backend/app/repositories/base_repository.py`

```python
class BaseRepository(IRepository[T]):
    def __init__(self, db: Session, model: Type[T])

    # Core CRUD
    def get_by_id(id: int, load_relationships: bool = True) -> Optional[T]
    def create(**kwargs) -> T
    def update(id: int, **kwargs) -> Optional[T]
    def delete(id: int) -> bool

    # Query helpers
    def exists(**kwargs) -> bool
    def count(**kwargs) -> int
    def find_by(**kwargs) -> List[T]
    def find_one_by(**kwargs) -> Optional[T]

    # Bulk operations
    def bulk_create(entities: List[Dict]) -> List[T]
    def bulk_update(updates: List[Dict]) -> int
```

### RepositoryFactory
**Location**: `backend/app/repositories/factory.py`

Centralized creation of all repository instances:
- `create_slot_manager_repository()`
- `create_availability_repository()`
- `create_conflict_checker_repository()`
- `create_bulk_operation_repository()`
- `create_booking_repository()`
- `create_week_operation_repository()`
- `create_instructor_profile_repository()`
- `create_user_repository()`
- `create_privacy_repository()`
- `create_analytics_repository()`
- `create_permission_repository()`
- `create_favorites_repository()`
- `create_conversation_state_repository()`
- `create_message_repository()`

## 🔧 Implemented Repositories (13 Total)

### Core Business Repositories
1. **SlotManagerRepository** - 13 methods, 97% coverage
2. **AvailabilityRepository** - 15+ methods, 63% coverage
3. **ConflictCheckerRepository** - 13 methods, 99% coverage
4. **BulkOperationRepository** - 13 methods, 95% coverage
5. **BookingRepository** - Complete CRUD + specialized queries
6. **WeekOperationRepository** - 15 methods, 86% coverage
7. **InstructorProfileRepository** - Eager loading, N+1 prevention

### System Repositories
8. **UserRepository** - User management, timezone operations
9. **PrivacyRepository** - GDPR compliance, data retention
10. **AnalyticsRepository** - Event tracking, metrics
11. **PermissionRepository** - RBAC system, 30 permissions
12. **FavoritesRepository** - Student favorites management
13. **ConversationStateRepository** - Messaging archive/trash management (v117)
14. **MessageRepository** - Message persistence with delivered_at/read_by (v117)

## 📊 Service Coverage

### Services with Dedicated Repositories (13)
All services properly use repositories for data access

### Services Using BaseService Only (12)
These services only use inherited methods:
- AuthService, CacheService, CategoryService
- EmailService, LocationService, LoggingService
- MetricsService, NotificationService, PaymentService
- SearchService, StudentService, TokenService

## 🛡️ Defensive Measures

### Pre-commit Hook Protection
**File**: `.pre-commit-config.yaml`
**Script**: `backend/scripts/check_repository_pattern.py`

Automatically blocks commits with direct database queries:
```yaml
- id: check-repository-pattern
  name: Check Repository Pattern Compliance
  entry: backend/scripts/check_repository_pattern.py
```

### What's Blocked
```python
# ❌ These patterns are BLOCKED:
self.db.query(User).filter(...)
self.db.add(booking)
self.db.commit()
db.query(Model).all()

# ✅ Only these patterns allowed:
self.repository.get_user_by_id(user_id)
self.user_repository.find_by(role=role)
```

### Exception Markers
```python
# For legitimate database access:
# repo-pattern-ignore: Transaction management requires direct DB
with self.db.begin_nested():
    # Complex transaction logic
```

## 💡 Implementation Patterns

### DO ✅
- Keep repositories focused on data access only
- Use BaseRepository methods when possible
- Follow consistent naming patterns
- Handle errors with RepositoryException
- Test with mocks (unit) and real DB (integration)
- Use eager loading to prevent N+1 queries
- Add pre-commit hooks to prevent regression

### DON'T ❌
- Put business logic in repositories
- Commit transactions in repositories (flush only)
- Raise database exceptions directly
- Create repository methods for one-off queries
- Skip error handling
- Forget to flush after modifications
- Ignore N+1 query patterns

## 🚀 Adding New Repositories

When creating new services:
1. Extend BaseService for inherited repository usage
2. Create dedicated repository if needed
3. Never use direct `db.query()` calls
4. Add to RepositoryFactory if applicable
5. Update documentation
6. Verify with checking script

### Manual Checks
```bash
# Check for violations
python backend/scripts/check_repository_pattern.py

# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run check-repository-pattern --all-files
```

## 📊 Key Achievements
- **100% implementation** across all services
- **Zero violations** after comprehensive audit
- **Pre-commit enforcement** prevents regression
- **99.5% query reduction** via eager loading
- **No performance degradation**
- **Easier maintenance** with clear boundaries
