from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token, get_password_hash
from app.models.booking import Booking, BookingStatus
from app.models.review import Review
from app.services.review_service import ReviewService


@pytest.fixture
def student_client_and_db(client: TestClient, db):
    return client, db


def _create_completed_booking(db, student_id: str, instructor_id: str, service_id: str) -> Booking:
    b = Booking(
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=service_id,
        booking_date=datetime.now(timezone.utc).date(),
        start_time=(datetime.now(timezone.utc) - timedelta(hours=2)).time(),
        end_time=(datetime.now(timezone.utc) - timedelta(hours=1)).time(),
        service_name="Lesson",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(b)
    db.flush()
    return b


def test_ratings_batch_endpoint_returns_expected_shape(client: TestClient, db):
    payload = {"instructor_ids": ["01TESTINSTRUCTOR00000000000001", "01TESTINSTRUCTOR00000000000002"]}
    res = client.post("/api/reviews/ratings/batch", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert len(data["results"]) == 2
    for item in data["results"]:
        assert set(item.keys()) == {"instructor_id", "rating", "review_count"}
        assert item["instructor_id"] in payload["instructor_ids"]
        assert isinstance(item["review_count"], int)


def test_booking_existing_restricts_to_current_user(student_client_and_db):
    client, db = student_client_and_db

    # Create two students and an instructor user (zip_code/timezone required by model)
    from app.core.enums import RoleName
    from app.models.rbac import Role, UserRole
    from app.models.user import User

    s1 = User(
        first_name="Alice",
        last_name="A",
        email="a@example.com",
        hashed_password=get_password_hash("x"),
        zip_code="10001",
        timezone="America/New_York",
    )
    s2 = User(
        first_name="Bob",
        last_name="B",
        email="b@example.com",
        hashed_password=get_password_hash("x"),
        zip_code="10001",
        timezone="America/New_York",
    )
    db.add_all([s1, s2])
    db.flush()

    # Assign STUDENT role to both
    student_role = db.query(Role).filter_by(name=RoleName.STUDENT).first()
    db.add_all([UserRole(user_id=s1.id, role_id=student_role.id), UserRole(user_id=s2.id, role_id=student_role.id)])
    db.flush()

    # Use s1 as instructor profile owner and create/reuse an InstructorService
    from app.models.instructor import InstructorProfile
    from app.models.service_catalog import InstructorService as InstructorServiceModel
    from app.models.service_catalog import ServiceCatalog, ServiceCategory

    instr = InstructorProfile(user_id=s1.id, bio="bio")
    db.add(instr)
    db.flush()

    # Try to reuse existing 'piano' catalog, else create
    catalog = db.query(ServiceCatalog).filter_by(slug="piano").first()
    if not catalog:
        cat = db.query(ServiceCategory).filter_by(slug="music").first()
        if not cat:
            cat = ServiceCategory(name="Music", slug="music")
            db.add(cat)
            db.flush()
        catalog = ServiceCatalog(category_id=cat.id, name="Piano", slug="piano", is_active=True)
        db.add(catalog)
        db.flush()

    isvc = InstructorServiceModel(
        instructor_profile_id=instr.id,
        service_catalog_id=catalog.id,
        hourly_rate=50.0,
        description="",
        is_active=True,
        duration_options=[60],
    )
    db.add(isvc)
    db.flush()

    service_id = isvc.id  # valid 26-char ULID
    b1 = _create_completed_booking(db, s1.id, instr.user_id, service_id)
    b2 = _create_completed_booking(db, s2.id, instr.user_id, service_id)

    svc = ReviewService(db)
    svc.submit_review(student_id=b1.student_id, booking_id=b1.id, rating=5)

    # Authenticate as s1 via JWT and header
    token = create_access_token({"sub": s1.email})
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/api/reviews/booking/existing", json=[b1.id, b2.id], headers=headers)
    assert res.status_code == 200
    ids = res.json()
    assert b1.id in ids
    assert b2.id not in ids
