# backend/tests/conftest.py
"""
Pytest configuration file.
This file is automatically loaded by pytest and sets up the test environment.

UPDATED FOR WORK STREAM #10: Single-table availability design.
All fixtures now create AvailabilitySlot objects directly with instructor_id and date.
"""

import os
import sys
from datetime import date, time, timedelta

# Add the backend directory to Python path so imports work
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth import get_password_hash

# Now we can import from app
from app.core.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User, UserRole

# Create a test engine with proper transaction handling
test_engine = create_engine(
    settings.database_url,
    poolclass=None,  # Disable pooling for tests
)

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
    """
    # Create tables
    Base.metadata.create_all(bind=test_engine)

    # Create a fresh session
    session = TestSessionLocal()

    yield session

    # Cleanup
    session.rollback()
    session.close()

    # Clean all test data after each test
    cleanup_db = TestSessionLocal()
    try:
        # Delete in dependency order to avoid FK violations
        cleanup_db.query(Booking).delete()
        cleanup_db.query(AvailabilitySlot).delete()
        cleanup_db.query(Service).delete()
        cleanup_db.query(InstructorProfile).delete()
        cleanup_db.query(User).delete()
        cleanup_db.commit()
    except Exception:
        cleanup_db.rollback()
    finally:
        cleanup_db.close()


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

    # Create services
    services = [
        Service(
            instructor_profile_id=profile.id,
            skill="Test Piano",
            hourly_rate=50.0,
            description="Test piano lessons",
            is_active=True,
        ),
        Service(
            instructor_profile_id=profile.id,
            skill="Test Guitar",
            hourly_rate=45.0,
            description="Test guitar lessons",
            is_active=True,
        ),
    ]
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

    # Create booking with self-contained time data (no slot reference!)
    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        service_id=service.id,
        # NO availability_slot_id - this field no longer exists!
        booking_date=tomorrow,
        start_time=time(9, 0),  # Self-contained time
        end_time=time(12, 0),  # Self-contained time
        service_name=service.skill,
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

    # Create a booking for tomorrow (self-contained, no slot reference)
    tomorrow = date.today() + timedelta(days=1)

    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        service_id=service.id,
        # NO availability_slot_id!
        booking_date=tomorrow,
        start_time=time(9, 0),  # Direct time specification
        end_time=time(12, 0),  # Direct time specification
        service_name=service.skill,
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

    # Create an inactive service
    inactive_service = Service(
        instructor_profile_id=profile.id,
        skill="Inactive Test Service",
        hourly_rate=60.0,
        description="This service is inactive",
        is_active=False,
    )
    db.add(inactive_service)
    db.flush()

    return test_instructor
