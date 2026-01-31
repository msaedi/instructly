# InstaInstru Testing Infrastructure
*Last Updated: January 2026 (Session v129)*

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
- **CI/CD Integration**: Pre-commit hooks + GitHub Actions + Codecov

### Frontend Testing Stack
- **Framework**: Jest 30.2.0
- **Component Testing**: React Testing Library
- **E2E Testing**: Playwright (Complete)
- **Coverage**: Jest coverage with threshold enforcement

### MCP Server Testing Stack
- **Framework**: pytest
- **Coverage**: 100% enforced
- **Auth Testing**: Full OAuth2 M2M flow testing

## 📊 Current Test Status

### Test Metrics (v129)

| Stack | Tests | Coverage | CI Threshold |
|-------|-------|----------|--------------|
| **Backend** | 2,516+ | 95.45% | 95% (locked) |
| **Frontend** | 8,806+ | 95.08% | 92% |
| **MCP Server** | 163+ | 100% | 100% |
| **Total** | **11,485+** | 95%+ | CI enforced |

**Pass Rate**: 100%

### Coverage by Domain (Backend)

| Domain | Coverage |
|--------|----------|
| **Payments** | 98%+ |
| **Referrals** | 99.18% |
| **Notifications** | 97%+ |
| **Search** | 95%+ |
| **Booking** | 97%+ |
| **Instructors** | 96%+ |
| **Admin/Workflow** | 98%+ |
| **Schemas** | 95%+ |

### Coverage Evolution

| Session | Backend | Frontend | Total Tests |
|---------|---------|----------|-------------|
| v121 | 79% | ~45% | 3,090 |
| v126 | 92% | 92% | 11,254 |
| v129 | **95.45%** | **95.08%** | **11,485+** |

## 🔧 Test Configuration

### Backend (pytest.ini)
```python
[tool.pytest.ini_options]
addopts = "--import-mode=importlib"  # Prevents basename collisions
testpaths = ["tests"]
asyncio_mode = "auto"
```

### Frontend (jest.config.js)
```javascript
coverageThreshold: {
  global: {
    statements: 92,
    branches: 80,
    functions: 92,
    lines: 92,
  },
}
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
├── repositories/                  # Repository tests
└── ratelimit/                     # Rate limiter tests

mcp-server/tests/
├── test_auth_middleware.py        # 45+ auth tests
├── test_*.py                      # Tool-specific tests
└── conftest.py                    # MCP fixtures
```

## 🛠️ Test Commands

### Backend
```bash
pytest                           # All tests
pytest -v                        # Verbose output
pytest -m unit                   # Unit tests only
pytest -m integration            # Integration tests
pytest tests/test_file.py        # Single file
pytest -k "test_name"           # Single test
pytest --cov=app --cov-report=term-missing
pytest --cov=app --cov-fail-under=95  # CI threshold
```

### Frontend
```bash
npm test                         # All tests
npm run test:coverage            # With coverage
npm run test:e2e                 # Playwright E2E
```

### MCP Server
```bash
cd mcp-server
pytest tests/ -v
pytest --cov=src --cov-report=xml
```

## 📈 CI/CD Configuration

### Backend (GitHub Actions)
```yaml
pytest tests/ --cov=app --cov-report=xml --cov-fail-under=95
```

### Frontend
```yaml
npm run test:coverage
```

### Codecov Multi-Project
```yaml
# Separate uploads for backend + MCP server
- name: Upload backend coverage
  uses: codecov/codecov-action@v5
  with:
    flags: backend
    file: backend/coverage.xml

- name: Upload MCP coverage
  uses: codecov/codecov-action@v5
  with:
    flags: mcp
    file: mcp-server/coverage.xml
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

### Timing-Safe Tests
```python
# Avoid cross-midnight flakiness
from datetime import datetime, timedelta
future_date = datetime.now() + timedelta(days=7)  # Always in future
```

## 🎯 Testing Goals (Achieved)

- ✅ 100% test pass rate
- ✅ 11,485+ comprehensive tests
- ✅ 95%+ coverage (CI enforced)
- ✅ CI/CD fully operational
- ✅ Repository pattern testing complete
- ✅ NL Search fully tested
- ✅ Load testing complete (150 users)
- ✅ MCP server 100% covered
- ✅ Codecov multi-project reporting

## 🚨 Critical Notes

1. **Test Database Protection**: Tests use separate database (can't wipe production)
2. **Email Mocking**: All emails mocked globally (won't send real emails)
3. **Cache Mocking**: Redis auto-mocked in tests
4. **CI Database**: Custom image with PostGIS + pgvector required
5. **Import Mode**: `--import-mode=importlib` prevents basename collisions
6. **Coverage Carryforward**: Codecov tracks partial runs accurately
