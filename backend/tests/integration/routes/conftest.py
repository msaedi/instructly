"""Conftest for integration/routes tests - seeds fixed accounts for booking-payment tests."""
from datetime import timedelta

from backend.tests._utils.bitmap_seed import seed_full_week
from backend.tests._utils.fixed_accounts import (
    FIXED_INSTRUCTOR_EMAIL,
    FIXED_STUDENT_EMAIL,
    ensure_future_windows_via_api,
    ensure_instructor_profile_and_service,
    ensure_user,
    next_monday,
)
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True, scope="function")
def _seed_booking_payment_routes(db: Session, client: TestClient, request):
    """Seed fixed users, services, and availability for booking-payment route tests."""
    # Skip seeding for tests that don't need booking/payment fixtures:
    # - strict schema tests only validate request shapes, not real booking flows
    # - booking_date_validation tests use a custom client fixture
    nodeid = request.node.nodeid
    if "_strict" in nodeid or "test_booking_date_validation" in nodeid:
        yield
        return

    # Fixed users with roles
    _ = ensure_user(db, FIXED_STUDENT_EMAIL, role="student")
    instructor = ensure_user(db, FIXED_INSTRUCTOR_EMAIL, role="instructor")

    # Instructor must have at least one active service with sane price floor
    ensure_instructor_profile_and_service(db, instructor, svc_name="Guitar", price=120.00)

    # Seed some future windows so booking creation succeeds
    mon = next_monday()
    tue = mon + timedelta(days=1)

    windows = {
        mon.isoformat(): [
            {"start_time": "09:00:00", "end_time": "10:00:00"},
            {"start_time": "14:00:00", "end_time": "15:30:00"},
        ],
        tue.isoformat(): [
            {"start_time": "11:00:00", "end_time": "12:00:00"},
        ],
    }

    # Get auth headers for instructor to seed availability
    from app.auth import create_access_token

    token = create_access_token(data={"sub": FIXED_INSTRUCTOR_EMAIL})
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Use the client directly with headers
    ensure_future_windows_via_api(client, mon, windows, auth_headers=auth_headers)

    yield

    # Cleanup (if needed) happens automatically via test isolation


@pytest.fixture(autouse=True, scope="function")
def _ensure_availability_for_class_instructor(db: Session, request):
    """
    Some modules/classes define an 'instructor_setup' fixture that creates an instructor
    without availability. Ensure availability is seeded for that instructor AFTER it exists.
    """
    # Strict schema tests don't need instructor availability
    if "_strict" in request.node.nodeid:
        yield
        return

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


@pytest.fixture
def auth_headers_student(db: Session):
    """Override auth_headers_student to use fixed student."""
    from app.auth import create_access_token
    from app.models.user import User

    # Get fixed student
    student = db.execute(
        select(User).where(User.email == FIXED_STUDENT_EMAIL)
    ).scalar_one()

    token = create_access_token(data={"sub": student.email})
    return {"Authorization": f"Bearer {token}"}
