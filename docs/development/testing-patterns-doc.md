# InstaInstru Testing Patterns Guide
*Last Updated: December 2024*

## Overview

This guide documents the testing patterns established while achieving 96% test coverage for BookingService. These patterns should be followed when writing tests for other services.

## Table of Contents

1. [Test Organization](#test-organization)
2. [Fixture Strategy](#fixture-strategy)
3. [Mock Patterns](#mock-patterns)
4. [Test Coverage Goals](#test-coverage-goals)
5. [Common Testing Patterns](#common-testing-patterns)
6. [Edge Case Testing](#edge-case-testing)
7. [Running Tests](#running-tests)

## Test Organization

### File Structure
```
backend/tests/
├── conftest.py                 # Shared fixtures
├── unit/                       # Unit tests (isolated)
├── integration/                # Integration tests (with DB)
│   ├── test_<service>_comprehensive.py
│   └── test_<service>_edge_cases.py
└── e2e/                       # End-to-end tests
```

### Test Class Organization
Group related tests into classes for better organization:

```python
class TestBookingServiceCreation:
    """Test booking creation functionality."""

class TestBookingServiceCancellation:
    """Test booking cancellation functionality."""

class TestBookingServiceRetrieval:
    """Test booking retrieval functionality."""
```

## Fixture Strategy

### Database Fixtures (from conftest.py)
```python
@pytest.fixture
def test_student(db: Session) -> User:
    """Create a test student user."""
    # Fixture creates user with proper setup

@pytest.fixture
def test_instructor_with_availability(db: Session) -> User:
    """Create instructor with full setup including availability."""
    # Creates instructor + profile + services + availability
```

### Mock Fixtures
```python
@pytest.fixture
def mock_notification_service():
    """Create a mock notification service."""
    mock = Mock(spec=NotificationService)
    mock.send_booking_confirmation = AsyncMock()
    mock.send_cancellation_notification = AsyncMock()
    return mock
```

## Mock Patterns

### 1. Service Dependencies
Always mock external service dependencies:

```python
booking_service = BookingService(db, mock_notification_service)
```

### 2. Testing Error Scenarios
Test that operations succeed even when non-critical services fail:

```python
# Setup notification to fail
mock_notification_service.send_booking_confirmation.side_effect = Exception("Email service down")

# Should succeed despite notification failure
booking = await booking_service.create_booking(test_student, booking_data)
assert booking.id is not None
```

### 3. Verifying Mock Calls
```python
mock_notification_service.send_booking_confirmation.assert_called_once()
```

## Test Coverage Goals

### Service Coverage Targets
- **Minimum**: 75% for all services
- **Target**: 80%+ for critical services
- **Excellence**: 90%+ for core business logic

### What to Test
1. **Happy Path** - Normal successful operations
2. **Validation** - Input validation and business rules
3. **Error Handling** - Exception scenarios
4. **Edge Cases** - Boundary conditions
5. **Authorization** - Permission checks
6. **State Transitions** - Status changes

### What NOT to Test
- Database migrations
- Third-party library internals
- Configuration loading
- Simple getters/setters without logic

## Common Testing Patterns

### 1. Testing Async Methods
```python
@pytest.mark.asyncio
async def test_create_booking_success(self, db: Session, ...):
    booking = await booking_service.create_booking(student, booking_data)
    assert booking.status == BookingStatus.CONFIRMED
```

### 2. Testing Exceptions
```python
with pytest.raises(ValidationException, match="Only students can create bookings"):
    await booking_service.create_booking(instructor, booking_data)
```

### 3. Testing Database State
```python
# Create test data
booking = create_test_booking(db, student, instructor)

# Perform operation
cancelled = await booking_service.cancel_booking(booking.id, student, "reason")

# Verify database state
assert cancelled.status == BookingStatus.CANCELLED
assert cancelled.cancelled_at is not None
```

### 4. Testing Query Variations
```python
def test_get_bookings_with_filters(self, db: Session, ...):
    # Test with different filter combinations
    bookings = booking_service.get_bookings_for_user(
        user=student,
        status=BookingStatus.CONFIRMED,
        upcoming_only=True,
        limit=5
    )
```

## Edge Case Testing

### 1. Null/Missing Data
```python
def test_create_booking_without_optional_fields(self, ...):
    booking_data = BookingCreate(
        availability_slot_id=slot.id,
        service_id=service.id,
        location_type="neutral"
        # No meeting_location, student_note, etc.
    )
```

### 2. Boundary Conditions
```python
def test_minimum_advance_booking_hours_boundary(self, ...):
    # Set exactly at boundary
    profile.min_advance_booking_hours = 2

    # Try to book 1:59 hours ahead (should fail)
    # Try to book 2:01 hours ahead (should succeed)
```

### 3. Concurrent Operations
```python
def test_concurrent_booking_attempts(self, ...):
    # Two students try to book same slot
    # Only one should succeed
```

### 4. State Transition Edge Cases
```python
def test_cancel_already_cancelled_booking(self, ...):
    # Should raise appropriate exception
```

## Running Tests

### Basic Test Execution
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific service tests
pytest tests/integration/test_booking_service*.py
```

### Coverage Reports
```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html

# Check specific service coverage
pytest --cov=app.services.booking_service --cov-fail-under=90
```

### Test Running Script
Use the provided script for comprehensive testing:

```bash
python scripts/run_booking_service_tests.py
```

## Best Practices

### 1. Use Descriptive Test Names
```python
def test_create_booking_with_inactive_service_fails(self, ...):
    # Clear what is being tested
```

### 2. Arrange-Act-Assert Pattern
```python
def test_cancel_booking(self, ...):
    # Arrange: Set up test data
    booking = create_test_booking(db, student, instructor)

    # Act: Perform the operation
    result = await service.cancel_booking(booking.id, student)

    # Assert: Verify the outcome
    assert result.status == BookingStatus.CANCELLED
```

### 3. Test Data Builders
```python
def create_test_booking(
    db: Session,
    student: User,
    instructor: User,
    **overrides
) -> Booking:
    """Helper to create test bookings with defaults."""
```

### 4. Isolation
- Each test should be independent
- Use database transactions that rollback
- Don't rely on test execution order

### 5. Performance
- Mock expensive operations (email, external APIs)
- Use fixtures to share setup across tests
- Keep tests focused and fast

## Example: Complete Test Pattern

Here's a complete example following all patterns:

```python
class TestServiceOperation:
    """Test service operation functionality."""

    @pytest.mark.asyncio
    async def test_operation_success(
        self,
        db: Session,
        test_user: User,
        mock_dependency: Mock
    ):
        """Test successful operation with all validations."""
        # Arrange
        service = MyService(db, mock_dependency)
        input_data = OperationInput(
            field1="value1",
            field2="value2"
        )

        # Act
        result = await service.perform_operation(test_user, input_data)

        # Assert
        assert result.id is not None
        assert result.status == OperationStatus.SUCCESS
        mock_dependency.notify.assert_called_once()

    def test_operation_validation_error(
        self,
        db: Session,
        test_user: User,
        mock_dependency: Mock
    ):
        """Test operation fails with invalid input."""
        service = MyService(db, mock_dependency)
        invalid_data = OperationInput(field1="")  # Invalid

        with pytest.raises(ValidationException, match="field1 required"):
            await service.perform_operation(test_user, invalid_data)
```

## Checklist for New Service Tests

When testing a new service, ensure you cover:

- [ ] Service initialization
- [ ] All public methods
- [ ] Success scenarios (happy path)
- [ ] Validation errors
- [ ] Permission/authorization checks
- [ ] Not found scenarios
- [ ] Business rule violations
- [ ] Database constraint violations
- [ ] External service failures
- [ ] Edge cases and boundaries
- [ ] Query parameter variations
- [ ] Concurrent operation handling
- [ ] Performance with large datasets

## Conclusion

Following these patterns helps ensure:
- Consistent test quality across the codebase
- High confidence in code correctness
- Easy maintenance and updates
- Quick identification of issues
- Protection against regressions

Remember: Good tests are an investment in the project's future. They enable confident refactoring and feature additions.
