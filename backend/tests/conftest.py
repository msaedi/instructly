# backend/tests/conftest.py
"""
Pytest configuration file with PRODUCTION DATABASE PROTECTION.
This file is automatically loaded by pytest and sets up the test environment.

CRITICAL: This file now includes safety checks to prevent accidental
production database usage during tests.

UPDATED FOR WORK STREAM #10: Single-table availability design.
All fixtures now create AvailabilitySlot objects directly with instructor_id and date.
"""

import os
import sys

# CRITICAL: Set testing mode BEFORE any app imports!
os.environ["is_testing"] = "true"
os.environ["rate_limit_enabled"] = "false"

# Add the backend directory to Python path so imports work
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# NOW we can set the settings
from app.core.config import settings

settings.is_testing = True
settings.rate_limit_enabled = False

from datetime import date, time, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.auth import get_password_hash

# Now we can import from app
from app.core.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.user import User, UserRole
from app.services.template_service import TemplateService

# ============================================================================
# PRODUCTION DATABASE PROTECTION
# ============================================================================


def _validate_test_database_url(database_url: str) -> None:
    """
    Validate that we're not using a production database for tests.

    Raises:
        RuntimeError: If the database URL appears to be a production database
    """
    if not database_url:
        raise RuntimeError("No database URL configured for tests!")

    # Check against known production database providers
    production_indicators = [
        "supabase.com",
        "supabase.co",
        "amazonaws.com",
        "cloud.google.com",
        "database.azure.com",
        "elephantsql.com",
        "bit.io",
        "neon.tech",
        "railway.app",
        "render.com",
        "aiven.io",
    ]

    url_lower = database_url.lower()

    for indicator in production_indicators:
        if indicator in url_lower:
            raise RuntimeError(
                f"\n\n" + "=" * 60 + "\n"
                f"CRITICAL ERROR: ATTEMPTING TO RUN TESTS ON PRODUCTION DATABASE!\n"
                f"=" * 60 + "\n"
                f"Database URL contains production indicator: '{indicator}'\n"
                f"URL: {database_url[:30]}...\n\n"
                f"Tests are configured to WIPE THE DATABASE after each test.\n"
                f"Running tests on production would DELETE ALL YOUR DATA!\n\n"
                f"To fix this:\n"
                f"1. Set TEST_DATABASE_URL to a local test database\n"
                f"2. Never use production database URLs for testing\n"
                f"3. Example: TEST_DATABASE_URL=postgresql://localhost/instainstru_test\n"
                f"=" * 60 + "\n"
            )

    # Warn if database doesn't have 'test' in the name
    test_indicators = ["test", "testing", "_test", "-test"]
    has_test_indicator = any(indicator in url_lower for indicator in test_indicators)

    if not has_test_indicator:
        print(
            f"\n⚠️  WARNING: Test database URL doesn't contain 'test' in its name.\n"
            f"   Consider using a clearly named test database to avoid confusion.\n"
            f"   Current: {database_url[:50]}...\n"
        )


# ============================================================================
# TEST DATABASE CONFIGURATION
# ============================================================================

# Force testing mode (lowercase to match settings)
os.environ["is_testing"] = "true"
settings.is_testing = True

# Get test database URL (lowercase to match settings)
TEST_DATABASE_URL = os.getenv("test_database_url", settings.test_database_url)

if not TEST_DATABASE_URL:
    # Try to use a default local test database if none configured
    TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/instainstru_test"
    print(
        f"\n⚠️  No test_database_url configured. Using default: {TEST_DATABASE_URL}\n"
        f"   Set test_database_url in your .env file for custom configuration.\n"
    )

# CRITICAL: Validate we're not using production
_validate_test_database_url(TEST_DATABASE_URL)

# Create test engine with the validated test database URL
test_engine = create_engine(
    TEST_DATABASE_URL,
    poolclass=None,  # Disable pooling for tests
)

# Verify we can connect and it's safe
try:
    with test_engine.connect() as conn:
        result = conn.execute(text("SELECT current_database()"))
        db_name = result.scalar()
        print(f"\n✅ Connected to test database: {db_name}")

        # Extra safety: check table count
        result = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables " "WHERE table_schema = 'public'"))
        table_count = result.scalar()

        if table_count > 20:  # Rough heuristic - test DB shouldn't have many tables initially
            response = input(
                f"\n⚠️  WARNING: Database '{db_name}' has {table_count} tables.\n"
                f"   This seems like a lot for a test database.\n"
                f"   Are you SURE this is a test database? (yes/no): "
            )
            if response.lower() != "yes":
                raise RuntimeError("Test run aborted for safety.")
except Exception as e:
    raise RuntimeError(f"Failed to connect to test database: {e}")

# Create test session factory
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def client(db: Session):
    """Create a test client with the test database."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Don't use context manager - create directly
    test_client = TestClient(app)

    yield test_client

    # Cleanup
    app.dependency_overrides.clear()
    test_client.close()  # Explicitly close the client


@pytest.fixture(scope="function")
def db():
    """
    Create a new database session for each test.
    This version works with TestClient.

    SAFETY: Only runs on validated test databases.
    """
    # Extra safety check before creating tables
    if settings.is_production_database(TEST_DATABASE_URL):
        raise RuntimeError("CRITICAL: Refusing to create tables in what appears to be a production database!")

    # Create tables
    Base.metadata.create_all(bind=test_engine)

    # Create a fresh session
    session = TestSessionLocal()

    yield session

    # Cleanup
    session.rollback()
    session.close()

    # Clean all test data after each test
    # SAFETY: We've already validated this is a test database
    cleanup_db = TestSessionLocal()
    try:
        # Log what we're doing for transparency
        if os.getenv("PYTEST_VERBOSE"):
            print("\n🧹 Cleaning up test data...")

        # Delete in dependency order to avoid FK violations
        cleanup_db.query(Booking).delete()
        cleanup_db.query(AvailabilitySlot).delete()
        cleanup_db.query(Service).delete()
        cleanup_db.query(InstructorProfile).delete()
        cleanup_db.query(User).delete()
        cleanup_db.commit()
    except Exception as e:
        print(f"\n⚠️  Error during test cleanup: {e}")
        cleanup_db.rollback()
    finally:
        cleanup_db.close()


# ============================================================================
# TEST FIXTURES (unchanged from original)
# ============================================================================


@pytest.fixture(scope="function")
def catalog_data(db: Session) -> dict:
    """Ensure service catalog data exists for tests."""
    # The YAML seeding has already loaded the catalog, just return it
    categories = db.query(ServiceCategory).all()
    services = db.query(ServiceCatalog).all()

    if not categories or not services:
        # If for some reason the catalog is empty, raise an error
        raise RuntimeError("Service catalog is empty - run scripts/seed_catalog_only.py first")

    return {"categories": categories, "services": services}


@pytest.fixture
def test_password():
    """Standard test password for all test users."""
    return "TestPassword123!"


@pytest.fixture
def test_student(db: Session, test_password: str) -> User:
    """Create a test student user."""
    student = User(
        email="test.student@example.com",
        hashed_password=get_password_hash(test_password),
        full_name="Test Student",
        is_active=True,
        role=UserRole.STUDENT,
    )
    db.add(student)
    db.flush()
    db.commit()
    return student


@pytest.fixture
def test_instructor(db: Session, test_password: str) -> User:
    """Create a test instructor user with profile and services."""
    # Create instructor user
    instructor = User(
        email="test.instructor@example.com",
        hashed_password=get_password_hash(test_password),
        full_name="Test Instructor",
        is_active=True,
        role=UserRole.INSTRUCTOR,
    )
    db.add(instructor)
    db.flush()

    # Create instructor profile
    profile = InstructorProfile(
        user_id=instructor.id,
        bio="Test instructor bio",
        areas_of_service="Manhattan, Brooklyn",
        years_experience=5,
        min_advance_booking_hours=2,
        buffer_time_minutes=15,
    )
    db.add(profile)
    db.flush()

    # Get catalog services - use actual services from seeded data
    catalog_services = (
        db.query(ServiceCatalog).filter(ServiceCatalog.slug.in_(["piano-lessons", "guitar-lessons"])).all()
    )

    print(f"Found {len(catalog_services)} catalog services")
    for cs in catalog_services:
        print(f"  - {cs.name} ({cs.slug})")

    # If no catalog services found, the catalog_data fixture may have failed
    if not catalog_services:
        print("WARNING: No catalog services found. Checking if any exist...")
        all_catalog = db.query(ServiceCatalog).all()
        print(f"Total catalog services in DB: {len(all_catalog)}")
        for cs in all_catalog[:5]:  # Show first 5
            print(f"  - {cs.name} ({cs.slug})")
        raise RuntimeError("Required catalog services (piano-lessons, guitar-lessons) not found")

    # Create instructor services linked to catalog
    services = []
    for catalog_service in catalog_services:
        if catalog_service.slug == "piano-lessons":
            hourly_rate = 50.0
            duration_options = [30, 60, 90]
        else:  # guitar-lessons
            hourly_rate = 45.0
            duration_options = [60]

        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=hourly_rate,
            description=catalog_service.description,
            duration_options=duration_options,
            is_active=True,
        )
        services.append(service)
    for service in services:
        db.add(service)

    db.flush()
    db.commit()
    return instructor


@pytest.fixture
def test_instructor_with_availability(db: Session, test_instructor: User) -> User:
    """
    Create a test instructor with availability for the next 7 days.

    UPDATED: Creates slots directly with instructor_id and date.
    """
    # Add availability for the next 7 days
    today = date.today()

    for i in range(7):
        target_date = today + timedelta(days=i)

        # Create time slots directly (9-12 and 14-17)
        slots = [
            AvailabilitySlot(
                instructor_id=test_instructor.id, specific_date=target_date, start_time=time(9, 0), end_time=time(12, 0)
            ),
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=target_date,
                start_time=time(14, 0),
                end_time=time(17, 0),
            ),
        ]
        for slot in slots:
            db.add(slot)

    db.flush()
    db.commit()
    return test_instructor


@pytest.fixture
def test_booking(db: Session, test_student: User, test_instructor_with_availability: User) -> Booking:
    """
    Create a test booking for tomorrow.

    UPDATED: Creates bookings without any reference to availability_slot_id,
    following the clean architecture from Session v56.
    """
    tomorrow = date.today() + timedelta(days=1)

    # Get instructor's profile and service
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor_with_availability.id).first()
    )

    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()

    # Get service name from catalog
    catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.id == service.service_catalog_id).first()
    service_name = catalog_service.name if catalog_service else "Test Service"

    # Create booking with self-contained time data (no slot reference!)
    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        # NO availability_slot_id - this field no longer exists!
        booking_date=tomorrow,
        start_time=time(9, 0),  # Self-contained time
        end_time=time(12, 0),  # Self-contained time
        service_name=service_name,  # From catalog
        hourly_rate=service.hourly_rate,
        total_price=service.hourly_rate * 3,  # 3 hour booking
        duration_minutes=180,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test Location",
        service_area="Manhattan",
    )
    db.add(booking)
    db.flush()
    return booking


@pytest.fixture
def auth_headers_student(test_student: User) -> dict:
    """Get auth headers for test student."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_student.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_instructor(test_instructor: User) -> dict:
    """Get auth headers for test instructor."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_instructor.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_instructor_with_bookings(db: Session, test_instructor_with_availability: User, test_student: User) -> User:
    """
    Create a test instructor with services that have bookings.

    UPDATED: Creates bookings without any reference to availability slots.
    """
    # Get instructor's profile
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor_with_availability.id).first()
    )

    if not profile:
        raise ValueError(f"No profile found for instructor {test_instructor_with_availability.id}")

    # Get the first service
    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()

    if not service:
        raise ValueError(f"No active service found for profile {profile.id}")

    # Get service name from catalog
    catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.id == service.service_catalog_id).first()
    service_name = catalog_service.name if catalog_service else "Test Service"

    # Create a booking for tomorrow (self-contained, no slot reference)
    tomorrow = date.today() + timedelta(days=1)

    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=service.id,
        # NO availability_slot_id!
        booking_date=tomorrow,
        start_time=time(9, 0),  # Direct time specification
        end_time=time(12, 0),  # Direct time specification
        service_name=service_name,  # From catalog
        hourly_rate=service.hourly_rate,
        total_price=service.hourly_rate * 3,  # 3 hour booking
        duration_minutes=180,
        status=BookingStatus.CONFIRMED,
        meeting_location="Test Location",
    )
    db.add(booking)
    db.flush()

    return test_instructor_with_availability


@pytest.fixture
def test_instructor_with_inactive_service(db: Session, test_instructor: User) -> User:
    """Create a test instructor with an inactive service."""
    # Get instructor's profile
    profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

    if not profile:
        raise ValueError(f"No profile found for instructor {test_instructor.id}")

    # Get a catalog service to link to - use any existing one
    catalog_service = db.query(ServiceCatalog).first()
    if not catalog_service:
        raise RuntimeError("No catalog services found - database not seeded properly")

    # Create an inactive service linked to catalog
    inactive_service = Service(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=60.0,
        description="This service is inactive",
        duration_options=[60],
        is_active=False,
    )
    db.add(inactive_service)
    db.flush()

    return test_instructor


# ============================================================================
# NOTIFICATION SERVICE FIXTURES
# ============================================================================


@pytest.fixture
def mock_cache():
    """Mock cache service for testing."""
    mock = Mock()
    mock.get = Mock(return_value=None)
    mock.set = Mock(return_value=True)
    mock.delete = Mock(return_value=True)
    mock.delete_pattern = Mock(return_value=0)
    return mock


@pytest.fixture
def email_service(db: Session, mock_cache):
    """Create EmailService with dependencies."""
    from app.services.email import EmailService

    service = EmailService(db, mock_cache)
    # Mock the actual sending to prevent real emails in tests
    service.send_email = Mock(return_value={"id": "test-email-id", "status": "sent"})
    return service


@pytest.fixture
def template_service(db: Session):
    """Create a TemplateService instance for testing."""
    return TemplateService(db, None)


@pytest.fixture
def notification_service(db: Session, template_service, email_service):
    """Create a NotificationService instance for testing."""
    from app.services.notification_service import NotificationService

    return NotificationService(db, None, template_service, email_service)


@pytest.fixture
def mock_email_service():
    """Mock email service to avoid sending real emails in tests."""
    mock = Mock()
    mock.send_email = Mock(return_value={"id": "test-email-id", "status": "sent"})
    return mock


@pytest.fixture
def mock_notification_service(db: Session, template_service, email_service):
    """
    Create a NotificationService with mocked email sending.
    This replaces the old mock_notification_service fixture.
    """
    from app.services.notification_service import NotificationService

    service = NotificationService(db, None, template_service, email_service)

    # The email service is already mocked in the email_service fixture
    # Also create async mocks for the main methods
    service.send_booking_confirmation = AsyncMock(return_value=True)
    service.send_cancellation_notification = AsyncMock(return_value=True)
    service.send_reminder_emails = AsyncMock(return_value=0)

    return service


@pytest.fixture
def notification_service_with_mocked_email(db: Session, template_service, email_service):
    """Create a NotificationService with real template rendering but mocked email sending."""
    from app.services.notification_service import NotificationService

    # email_service fixture already has mocked send_email
    return NotificationService(db, None, template_service, email_service)
