# InstaInstru Testing Infrastructure
*Last Updated: August 2025*

## 🧪 Testing Framework & Tools

### Backend Testing Stack
- **Framework**: pytest 8.4.0
- **Coverage**: pytest-cov 6.2.1
- **Async Testing**: pytest-asyncio 1.0.0
- **HTTP Client**: httpx 0.23.3 (specifically this version for compatibility)
- **Test Client**: FastAPI TestClient
- **Mocking**: unittest.mock (with global email mocking)
- **Database**: PostgreSQL (same as production) for tests
- **Fixtures**: Comprehensive conftest.py
- **CI/CD Integration**: Pre-commit hooks + GitHub Actions

### Frontend Testing Stack
- **Framework**: Jest
- **Component Testing**: React Testing Library
- **E2E Testing**: Playwright (COMPLETE)

## 📊 Current Test Status

### Test Metrics
- **Total Tests**: ~1,450
- **Pass Rate**: 100%
- **Code Coverage**: 79%+
- **CI/CD**: Fully operational with PostgreSQL 17 + Redis 7

### Coverage by Priority

#### Excellent Coverage (95%+)
- ConflictChecker: 99%
- BaseService: 98%
- SlotManager: 97%
- BookingService: 97%
- BulkOperationService: 95%

#### Medium Coverage (60-79%)
- AvailabilityService: 63%
- NotificationService: 69%
- Auth Dependencies: 64%

#### Low Coverage (<60%)
- Repositories: 36-54% (normal for abstraction layers)
- CacheService: 45%
- Routes: 27-38% (covered by integration tests)

## 🔧 Test Configuration

### Database Setup
```python
# Test database with transaction isolation
test_engine = create_engine(
    settings.test_database_url,  # NOT production URL!
    poolclass=None,  # Disable pooling for tests
)
```

### Core Fixtures (conftest.py)
- `test_instructor` - Instructor with profile and services
- `test_student` - Basic student user
- `test_booking` - Sample booking
- `auth_headers_student/instructor` - Pre-authenticated headers
- `mock_notification_service` - Email mock
- `mock_redis` - Cache mock (auto-applied)

## 📁 Test Organization

```
backend/tests/
├── conftest.py                    # Test configuration
├── helpers/                       # Test utilities
├── unit/                          # Pure unit tests (no DB)
│   └── services/                  # Service logic tests
├── integration/                   # Tests requiring DB/external
│   ├── api/                       # API endpoint tests
│   ├── cache/                     # Cache integration
│   ├── repository_patterns/       # SQL pattern documentation
│   └── services/                  # Service integration tests
├── routes/                        # Route tests
├── models/                        # Model tests
└── repositories/                  # Repository tests
```

## 🛠️ Test Commands

### Basic Execution
```bash
pytest                           # All tests
pytest -v                        # Verbose output
pytest -m unit                   # Unit tests only
pytest -m integration            # Integration tests
pytest tests/test_file.py        # Single file
pytest -k "test_name"           # Single test
```

### Coverage
```bash
pytest --cov=app --cov-report=term-missing
pytest --cov=app --cov-report=html
pytest --cov=app --cov-fail-under=79
```

### Debugging
```bash
pytest -x                        # Stop on first failure
pytest -s                        # Show print statements
pytest --tb=long                 # Full traceback
pytest --pdb                     # Drop into debugger
```

## 🔍 Common Test Patterns

### Repository Mocking
```python
from unittest.mock import Mock
from app.repositories.booking_repository import BookingRepository

mock_repository = Mock(spec=BookingRepository)
service.repository = mock_repository
mock_repository.create.return_value = mock_booking
result = service.create_booking(...)
mock_repository.create.assert_called_once()
```

### Unique Test Data (Prevents Conflicts)
```python
from tests.fixtures.unique_test_data import unique_data
email = unique_data.unique_email("instructor")  # instructor.abc123@example.com
```

### Common Fixes for Test Failures
- **Missing specific_date**: Use `specific_date=target_date` not `date=`
- **Import errors**: `BaseRepositoryService` → `BaseService`
- **Method renames**: `get_booked_slots_for_date` → `get_booked_times_for_date`

## 📈 Testing Best Practices

### Unit Tests
- Mock all dependencies
- Test business logic only
- Use repository mocks, not database

### Integration Tests
- Use real database with transactions
- Test complete workflows
- Verify side effects (cache, notifications)

### Test Data
- Use UUID-based unique data generation
- Never hardcode IDs or emails
- Clean up after tests

## 🎯 Testing Goals

### Current State
- ✅ 100% test pass rate
- ✅ 1450+ comprehensive tests
- ✅ CI/CD fully operational
- ✅ Repository pattern testing complete

### Target State
- Maintain 100% pass rate
- Increase coverage to 85%+
- Add more E2E tests
- Load testing before launch

## 🚨 Critical Notes

1. **Test Database Protection**: Tests use separate database (can't wipe production)
2. **Email Mocking**: All emails mocked globally (won't send real emails)
3. **Cache Mocking**: Redis auto-mocked in tests
4. **CI Database**: Custom image with PostGIS + pgvector required
