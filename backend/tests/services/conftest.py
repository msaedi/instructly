"""Conftest for services tests - seeds fixed accounts for booking-payment service tests."""
from backend.tests._utils.bitmap_seed import seed_full_week
from backend.tests._utils.fixed_accounts import (
    FIXED_INSTRUCTOR_EMAIL,
    FIXED_STUDENT_EMAIL,
    ensure_instructor_profile_and_service,
    ensure_user,
)
import pytest
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True, scope="function")
def _seed_booking_payment_services(db: Session):
    """Seed fixed users and services for booking-payment service tests."""
    _ = ensure_user(db, FIXED_STUDENT_EMAIL, role="student")
    instructor = ensure_user(db, FIXED_INSTRUCTOR_EMAIL, role="instructor")

    ensure_instructor_profile_and_service(db, instructor, svc_name="Guitar", price=120.00)

    yield

    # Cleanup (if needed) happens automatically via test isolation


@pytest.fixture(autouse=True, scope="function")
def _ensure_availability_for_service_instructor(db: Session, request):
    """
    Some modules/classes define an 'instructor_setup' fixture that creates an instructor
    without availability. Ensure availability is seeded for that instructor AFTER it exists.
    """
    # Try to get the fixture value - this will trigger it if it exists
    # We catch exceptions to be resilient
    try:
        # Check if this is a class-based test that might have its own instructor_setup
        # Class fixtures take precedence, so we'll get the class fixture if it exists
        inst = request.getfixturevalue("instructor_setup")
        # Handle tuple (instructor, profile, service) or object
        if isinstance(inst, tuple):
            instructor = inst[0]
        else:
            instructor = inst

        instructor_id = getattr(instructor, "id", None) or (instructor.get("id") if isinstance(instructor, dict) else None)

        if instructor_id:
            # Only seed if this instructor doesn't have the fixed email (i.e., it's a class-created instructor)
            instructor_email = getattr(instructor, "email", None) or (instructor.get("email") if isinstance(instructor, dict) else None)
            if instructor_email != FIXED_INSTRUCTOR_EMAIL:
                seed_full_week(db, instructor_id, start="09:00:00", end="18:00:00", weeks=2)
    except (pytest.FixtureLookupError, KeyError, AttributeError):
        # Fixture doesn't exist or isn't requested - that's fine
        pass
    except Exception:
        # Other errors - log but don't crash
        pass

    yield
