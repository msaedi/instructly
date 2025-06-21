# backend/tests/conftest.py
"""
Pytest configuration file.
This file is automatically loaded by pytest and sets up the test environment.
"""

import os
import sys
from datetime import date, time, timedelta

# Add the backend directory to Python path so imports work
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.auth import get_password_hash

# Now we can import from app
from app.core.config import settings
from app.database import Base
from app.models.availability import AvailabilitySlot, InstructorAvailability
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


@pytest.fixture(scope="function")
def db():
    """
    Create a new database session for each test with proper rollback.

    This uses nested transactions to ensure complete isolation.
    """
    # Create tables if they don't exist
    Base.metadata.create_all(bind=test_engine)

    # Create a connection and transaction
    connection = test_engine.connect()
    transaction = connection.begin()

    # Create a session bound to this connection
    session = TestSessionLocal(bind=connection)

    # Start a nested transaction (savepoint)
    nested = connection.begin_nested()

    # If the session would roll back, start a new savepoint
    @event.listens_for(session, "after_transaction_end")
    def end_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    # Cleanup
    session.close()
    transaction.rollback()
    connection.close()


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
    return instructor


@pytest.fixture
def test_instructor_with_availability(db: Session, test_instructor: User) -> User:
    """Create a test instructor with availability for the next 7 days."""
    # Add availability for the next 7 days
    today = date.today()

    for i in range(7):
        target_date = today + timedelta(days=i)

        availability = InstructorAvailability(instructor_id=test_instructor.id, date=target_date, is_cleared=False)
        db.add(availability)
        db.flush()

        # Add time slots (9-12 and 14-17)
        slots = [
            AvailabilitySlot(availability_id=availability.id, start_time=time(9, 0), end_time=time(12, 0)),
            AvailabilitySlot(availability_id=availability.id, start_time=time(14, 0), end_time=time(17, 0)),
        ]
        for slot in slots:
            db.add(slot)

    db.flush()
    return test_instructor


@pytest.fixture
def test_booking(db: Session, test_student: User, test_instructor_with_availability: User) -> Booking:
    """Create a test booking for tomorrow."""
    tomorrow = date.today() + timedelta(days=1)

    # Get instructor's profile and service
    profile = (
        db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor_with_availability.id).first()
    )

    service = db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()

    # Get an available slot for tomorrow
    availability = (
        db.query(InstructorAvailability)
        .filter(
            InstructorAvailability.instructor_id == test_instructor_with_availability.id,
            InstructorAvailability.date == tomorrow,
        )
        .first()
    )

    slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability.id).first()

    # Create booking
    booking = Booking(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        service_id=service.id,
        availability_slot_id=slot.id,
        booking_date=tomorrow,
        start_time=slot.start_time,
        end_time=slot.end_time,
        service_name=service.skill,
        hourly_rate=service.hourly_rate,
        total_price=service.hourly_rate * ((slot.end_time.hour - slot.start_time.hour)),
        duration_minutes=(slot.end_time.hour - slot.start_time.hour) * 60,
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
    """Create a test instructor with services that have bookings."""
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

    # Get tomorrow's availability
    tomorrow = date.today() + timedelta(days=1)
    availability = (
        db.query(InstructorAvailability)
        .filter(
            InstructorAvailability.instructor_id == test_instructor_with_availability.id,
            InstructorAvailability.date == tomorrow,
        )
        .first()
    )

    if availability:
        slot = db.query(AvailabilitySlot).filter(AvailabilitySlot.availability_id == availability.id).first()

        if slot:
            # Create a booking for this service
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor_with_availability.id,
                service_id=service.id,
                availability_slot_id=slot.id,
                booking_date=tomorrow,
                start_time=slot.start_time,
                end_time=slot.end_time,
                service_name=service.skill,
                hourly_rate=service.hourly_rate,
                total_price=service.hourly_rate * 3,  # 3 hour slot
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
