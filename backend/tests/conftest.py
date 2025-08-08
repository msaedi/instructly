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

# CRITICAL: Mock Resend API globally to prevent real emails in ANY test
import unittest.mock

# Create global mock that persists for all tests
global_resend_mock = unittest.mock.patch("resend.Emails.send")
mocked_send = global_resend_mock.start()
mocked_send.return_value = {"id": "test-email-id", "status": "sent"}

# Additional safety: Mock the entire resend module if needed
import sys

if "resend" not in sys.modules:
    resend_module_mock = unittest.mock.MagicMock()
    resend_module_mock.Emails.send.return_value = {"id": "test-email-id", "status": "sent"}
    sys.modules["resend"] = resend_module_mock

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
from app.core.enums import RoleName
from app.database import Base, get_db
from app.main import fastapi_app as app  # Use FastAPI instance for tests
from app.models import SearchEvent, SearchHistory
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.user import User
from app.services.permission_service import PermissionService
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

# CRITICAL: Force INT database for all tests - ignore any environment flags
# This ensures tests ALWAYS use the INT database for safety
os.environ.pop("USE_STG_DATABASE", None)
os.environ.pop("USE_PROD_DATABASE", None)

# Get test database URL - this will now always use INT database
TEST_DATABASE_URL = settings.test_database_url

if not TEST_DATABASE_URL:
    # Try to use a default local test database if none configured
    TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/instainstru_int"
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

        # Extract expected database name from TEST_DATABASE_URL
        from urllib.parse import urlparse

        parsed_url = urlparse(TEST_DATABASE_URL)
        expected_db_name = parsed_url.path.lstrip("/")

        # Verify we're using the expected test database
        if db_name != expected_db_name:
            raise RuntimeError(
                f"SAFETY CHECK FAILED: Expected test database '{expected_db_name}' "
                f"(from TEST_DATABASE_URL), but connected to '{db_name}'. "
                f"Aborting to prevent data loss."
            )

        # Log table count for information (no prompt needed in pytest)
        if table_count > 20:
            print(f"   Note: Test database has {table_count} tables (migrations already applied)")
except Exception as e:
    raise RuntimeError(f"Failed to connect to test database: {e}")

# Create test session factory
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# ============================================================================
# Helper Functions
# ============================================================================


def _ensure_rbac_roles():
    """Ensure RBAC roles exist in the test database."""
    from app.models.rbac import Role

    session = TestSessionLocal()
    try:
        # Check if roles already exist
        existing_roles = session.query(Role).count()
        if existing_roles > 0:
            return

        # Create standard roles
        roles = [
            Role(name=RoleName.ADMIN, description="Administrator with full access"),
            Role(name=RoleName.INSTRUCTOR, description="Instructor who can manage their profile and availability"),
            Role(name=RoleName.STUDENT, description="Student who can book lessons"),
        ]

        for role in roles:
            session.add(role)

        session.commit()
        print(f"✅ Created {len(roles)} RBAC roles")
    except Exception as e:
        print(f"❌ Error creating RBAC roles: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_catalog_data():
    """Ensure catalog data is seeded for tests."""
    # Import here to avoid circular imports
    from scripts.seed_catalog_only import seed_catalog

    # Create a separate session to check
    session = TestSessionLocal()
    try:
        # Check if catalog already exists
        existing_categories = session.query(ServiceCategory).count()
        existing_services = session.query(ServiceCatalog).count()

        if existing_categories == 0 or existing_services == 0:
            print("\n🌱 Seeding catalog data for tests...")
            # Close session before seeding (seed_catalog creates its own)
            session.close()

            # Seed using the test database URL
            seed_catalog(db_url=TEST_DATABASE_URL, verbose=False)

            # Verify seeding worked
            session = TestSessionLocal()
            categories_count = session.query(ServiceCategory).count()
            services_count = session.query(ServiceCatalog).count()

            # Verify critical services exist
            piano = session.query(ServiceCatalog).filter_by(slug="piano").first()
            guitar = session.query(ServiceCatalog).filter_by(slug="guitar").first()

            if not piano or not guitar:
                raise RuntimeError("Critical catalog services (piano, guitar) not found after seeding")

            print(f"✅ Seeded {categories_count} categories and {services_count} services")
    except Exception as e:
        print(f"\n❌ Error seeding catalog data: {e}")
        raise
    finally:
        session.close()


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

    # Seed catalog data if needed
    _ensure_catalog_data()
    # Seed RBAC roles
    _ensure_rbac_roles()

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
        cleanup_db.query(Service).delete()  # This is InstructorService

        # Clean up service catalog test data
        # Only delete services with test patterns - preserve all seeded catalog data
        from app.models.service_catalog import ServiceAnalytics

        # Don't delete by ID anymore - we have 250+ services
        # Only delete services that match test patterns
        cleanup_db.query(ServiceCatalog).filter(
            (ServiceCatalog.name.like("Test%"))
            | (ServiceCatalog.name.like("%Test Service%"))
            | (ServiceCatalog.slug.like("test-%"))
        ).delete()

        # Clean up analytics for deleted services
        from sqlalchemy import select

        # Create explicit select() to avoid SQLAlchemy warning
        existing_catalog_ids = select(ServiceCatalog.id)
        cleanup_db.query(ServiceAnalytics).filter(
            ~ServiceAnalytics.service_catalog_id.in_(existing_catalog_ids)
        ).delete(synchronize_session=False)

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
    # Check if user already exists and delete it
    existing_user = db.query(User).filter(User.email == "test.student@example.com").first()
    if existing_user:
        db.delete(existing_user)
        db.commit()

    student = User(
        email="test.student@example.com",
        hashed_password=get_password_hash(test_password),
        full_name="Test Student",
        is_active=True,
    )
    db.add(student)
    db.flush()

    # Assign student role
    permission_service = PermissionService(db)
    permission_service.assign_role(student.id, RoleName.STUDENT)
    db.refresh(student)
    db.commit()
    return student


@pytest.fixture
def test_instructor(db: Session, test_password: str) -> User:
    """Create a test instructor user with profile and services."""
    # Check if user already exists and delete it
    existing_user = db.query(User).filter(User.email == "test.instructor@example.com").first()
    if existing_user:
        # Delete profile first if it exists (cascade will handle services)
        if hasattr(existing_user, "instructor_profile") and existing_user.instructor_profile:
            db.delete(existing_user.instructor_profile)
        db.delete(existing_user)
        db.commit()

    # Create instructor user
    instructor = User(
        email="test.instructor@example.com",
        hashed_password=get_password_hash(test_password),
        full_name="Test Instructor",
        is_active=True,
    )
    db.add(instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(instructor.id, RoleName.INSTRUCTOR)
    db.refresh(instructor)

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
    catalog_services = db.query(ServiceCatalog).filter(ServiceCatalog.slug.in_(["piano", "guitar"])).all()

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
        raise RuntimeError("Required catalog services (piano, guitar) not found")

    # Create instructor services linked to catalog
    services = []
    for catalog_service in catalog_services:
        if catalog_service.slug == "piano":
            hourly_rate = 50.0
            duration_options = [30, 60, 90]
        else:  # guitar
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
    db.refresh(instructor)
    return instructor


@pytest.fixture
def test_instructor_2(db: Session, test_password: str) -> User:
    """Create a second test instructor user with profile."""
    # Check if user already exists and delete it
    existing_user = db.query(User).filter(User.email == "test.instructor2@example.com").first()
    if existing_user:
        # Delete profile first if it exists (cascade will handle services)
        if hasattr(existing_user, "instructor_profile") and existing_user.instructor_profile:
            db.delete(existing_user.instructor_profile)
        db.delete(existing_user)
        db.commit()

    # Create instructor user
    instructor = User(
        email="test.instructor2@example.com",
        hashed_password=get_password_hash(test_password),
        full_name="Test Instructor 2",
        is_active=True,
    )
    db.add(instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(instructor.id, RoleName.INSTRUCTOR)
    db.refresh(instructor)

    # Create instructor profile
    profile = InstructorProfile(
        user_id=instructor.id,
        bio="Second test instructor bio",
        areas_of_service="Queens, Bronx",
        years_experience=3,
        min_advance_booking_hours=1,
        buffer_time_minutes=10,
    )
    db.add(profile)
    db.commit()
    db.refresh(instructor)
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
def auth_headers_instructor_2(test_instructor_2: User) -> dict:
    """Get auth headers for second test instructor."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_instructor_2.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(test_student: User) -> dict:
    """Get auth headers for test student (default auth headers)."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": test_student.email})
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


@pytest.fixture
def sample_categories(db: Session) -> list[ServiceCategory]:
    """Create sample service categories for testing."""
    categories = [
        ServiceCategory(
            id=1,
            name="Music",
            slug="music",
            subtitle="Instrument Voice Theory",
            description="Musical instruction",
            display_order=1,
        ),
        ServiceCategory(
            id=2,
            name="Sports & Fitness",
            slug="sports-fitness",
            subtitle="",
            description="Physical fitness and sports",
            display_order=2,
        ),
        ServiceCategory(
            id=3,
            name="Language",
            slug="language",
            subtitle="Learn new languages",
            description="Language instruction",
            display_order=3,
        ),
    ]

    for category in categories:
        existing = db.query(ServiceCategory).filter(ServiceCategory.id == category.id).first()
        if not existing:
            db.add(category)

    db.commit()
    return categories


@pytest.fixture
def sample_catalog_services(db: Session, sample_categories: list[ServiceCategory]) -> list[ServiceCatalog]:
    """Create sample catalog services for testing."""
    services = [
        # Music services
        ServiceCatalog(
            id=101,
            category_id=1,
            name="Piano Lessons",
            slug="piano-lessons",
            description="Learn piano",
            search_terms=["piano", "keyboard"],
            display_order=1,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
        ServiceCatalog(
            id=102,
            category_id=1,
            name="Guitar Lessons",
            slug="guitar-lessons",
            description="Learn guitar",
            search_terms=["guitar", "acoustic", "electric"],
            display_order=2,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
        ServiceCatalog(
            id=103,
            category_id=1,
            name="Violin Lessons",
            slug="violin-lessons",
            description="Learn violin",
            search_terms=["violin", "strings"],
            display_order=3,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
        # Sports & Fitness services
        ServiceCatalog(
            id=201,
            category_id=2,
            name="Yoga",
            slug="yoga",
            description="Yoga instruction",
            search_terms=["yoga", "meditation"],
            display_order=1,
            online_capable=True,
            requires_certification=True,
            is_active=True,
        ),
        ServiceCatalog(
            id=202,
            category_id=2,
            name="Personal Training",
            slug="personal-training",
            description="One-on-one fitness training",
            search_terms=["fitness", "training", "gym"],
            display_order=2,
            online_capable=False,
            requires_certification=True,
            is_active=True,
        ),
        # Language services
        ServiceCatalog(
            id=301,
            category_id=3,
            name="Spanish",
            slug="spanish",
            description="Learn Spanish",
            search_terms=["spanish", "espanol"],
            display_order=1,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        ),
    ]

    for service in services:
        existing = db.query(ServiceCatalog).filter(ServiceCatalog.id == service.id).first()
        if not existing:
            db.add(service)

    db.commit()
    return services


@pytest.fixture
def sample_instructors_with_services(db: Session, test_password: str) -> list[User]:
    """Create sample instructors with services linked to catalog."""
    from app.models.service_catalog import ServiceAnalytics

    instructors = []

    # Import unique data generator
    from tests.fixtures.unique_test_data import unique_data

    # Piano instructor - use unique email to avoid conflicts
    piano_email = unique_data.unique_email("piano.instructor")

    piano_instructor = User(
        email=piano_email,
        hashed_password=get_password_hash(test_password),
        is_active=True,
        full_name=unique_data.unique_name("Piano Teacher"),
    )
    db.add(piano_instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(piano_instructor.id, RoleName.INSTRUCTOR)
    db.refresh(piano_instructor)
    db.commit()

    piano_profile = InstructorProfile(
        user_id=piano_instructor.id, bio="Expert piano teacher", years_experience=10, min_advance_booking_hours=24
    )
    db.add(piano_profile)
    db.commit()

    # Find piano service from catalog
    piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "piano").first()
    if not piano_catalog:
        raise RuntimeError("Piano service not found in catalog")

    piano_service = Service(
        instructor_profile_id=piano_profile.id,
        service_catalog_id=piano_catalog.id,
        description="Expert piano instruction",
        hourly_rate=75.0,
        duration_options=[30, 60, 90],
        is_active=True,
    )
    db.add(piano_service)
    db.commit()  # Commit to ensure service is created

    # Update analytics for Piano
    piano_analytics = db.query(ServiceAnalytics).filter(ServiceAnalytics.service_catalog_id == piano_catalog.id).first()
    if not piano_analytics:
        piano_analytics = ServiceAnalytics(service_catalog_id=piano_catalog.id)
        db.add(piano_analytics)
    piano_analytics.active_instructors = 1
    piano_analytics.search_count_30d = 100  # This will result in demand_score ~= 85
    piano_analytics.booking_count_30d = 17  # These values affect the computed demand_score
    piano_analytics.search_count_7d = 30  # For trending calculation

    instructors.append(piano_instructor)

    # Yoga instructor - use unique email to avoid conflicts
    yoga_email = unique_data.unique_email("yoga.instructor")

    yoga_instructor = User(
        email=yoga_email,
        hashed_password=get_password_hash(test_password),
        is_active=True,
        full_name=unique_data.unique_name("Yoga Teacher"),
    )
    db.add(yoga_instructor)
    db.flush()

    # Assign instructor role
    permission_service = PermissionService(db)
    permission_service.assign_role(yoga_instructor.id, RoleName.INSTRUCTOR)
    db.refresh(yoga_instructor)
    db.commit()

    yoga_profile = InstructorProfile(
        user_id=yoga_instructor.id, bio="Certified yoga instructor", years_experience=5, min_advance_booking_hours=24
    )
    db.add(yoga_profile)
    db.commit()

    # Find yoga service from catalog
    yoga_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "yoga").first()
    if not yoga_catalog:
        raise RuntimeError("Yoga service not found in catalog")

    yoga_service = Service(
        instructor_profile_id=yoga_profile.id,
        service_catalog_id=yoga_catalog.id,
        description="Professional yoga instruction",
        hourly_rate=60.0,
        duration_options=[60, 90],
        is_active=True,
    )
    db.add(yoga_service)
    db.commit()  # Commit to ensure service is created

    # Update analytics for Yoga
    yoga_analytics = db.query(ServiceAnalytics).filter(ServiceAnalytics.service_catalog_id == yoga_catalog.id).first()
    if not yoga_analytics:
        yoga_analytics = ServiceAnalytics(service_catalog_id=yoga_catalog.id)
        db.add(yoga_analytics)
    yoga_analytics.active_instructors = 1
    yoga_analytics.search_count_30d = 120  # This will result in higher demand_score
    yoga_analytics.booking_count_30d = 18  # These values affect the computed demand_score
    yoga_analytics.search_count_7d = 40  # For trending calculation

    instructors.append(yoga_instructor)

    db.commit()
    return instructors


@pytest.fixture
def mock_cache_service():
    """Create a mock cache service for testing."""
    mock = Mock()
    mock.get = Mock(return_value=None)
    mock.set = Mock(return_value=True)
    mock.delete = Mock(return_value=True)
    return mock


# Privacy Service Test Fixtures
@pytest.fixture
def sample_user_for_privacy(db):
    """Create a sample user with related data for privacy testing."""
    from datetime import datetime, timezone

    user = User(
        email="privacy_test@example.com",
        full_name="Privacy Test User",
        hashed_password="hashed_password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Add search history
    search = SearchHistory(
        user_id=user.id,
        search_query="math tutoring",
        normalized_query="math tutoring",  # Required field
        results_count=5,
        search_count=3,
        first_searched_at=datetime.now(timezone.utc),
        last_searched_at=datetime.now(timezone.utc),
    )
    db.add(search)

    # Add search events
    event = SearchEvent(
        user_id=user.id,
        search_query="math",
        results_count=10,
        search_context={},
    )
    db.add(event)

    # Note: AlertHistory doesn't have user_id - it's for system alerts

    db.commit()
    return user


@pytest.fixture
def sample_instructor_for_privacy(db):
    """Create a sample instructor user with profile for privacy testing."""
    user = User(
        email="privacy_instructor@example.com",
        full_name="Privacy Test Instructor",
        hashed_password="hashed_password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Add instructor profile
    instructor = InstructorProfile(
        user_id=user.id,
        bio="Experienced math tutor",
        years_experience=5,
    )
    db.add(instructor)
    db.commit()

    return user


@pytest.fixture
def sample_admin_for_privacy(db):
    """Create a sample admin user for privacy testing."""
    user = User(
        email="privacy_admin@example.com",
        full_name="Privacy Admin User",
        hashed_password="hashed_password",
    )
    db.add(user)
    db.commit()
    return user


def pytest_sessionfinish(session, exitstatus):
    """Cleanup after all tests are done."""
    # Stop the global Resend mock
    global_resend_mock.stop()
