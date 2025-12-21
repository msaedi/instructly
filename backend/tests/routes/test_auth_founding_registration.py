from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.beta import BetaInvite
from app.models.instructor import InstructorProfile
from app.services.config_service import ConfigService


def _create_invite(db: Session, *, code: str, email: str, grant_founding_status: bool) -> None:
    invite = BetaInvite(
        code=code,
        email=email,
        role="instructor_beta",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        grant_founding_status=grant_founding_status,
    )
    db.add(invite)
    db.commit()


def _register_instructor(
    client: TestClient, *, email: str, invite_code: str
) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "TestPass123!",
            "first_name": "Founding",
            "last_name": "Instructor",
            "phone": "+12125550000",
            "zip_code": "10001",
            "role": "instructor",
            "metadata": {"invite_code": invite_code},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_founding_status_set_on_signup_with_founding_invite(
    client: TestClient, db: Session
) -> None:
    email = f"founder-{uuid.uuid4().hex[:8]}@example.com"
    invite_code = f"FOUND{uuid.uuid4().hex[:4].upper()}"
    _create_invite(db, code=invite_code, email=email, grant_founding_status=True)

    user_data = _register_instructor(client, email=email, invite_code=invite_code)

    instructor = db.query(InstructorProfile).filter_by(user_id=user_data["id"]).first()
    assert instructor is not None
    assert instructor.is_founding_instructor is True
    assert instructor.founding_granted_at is not None


def test_founding_status_not_set_when_invite_has_false(
    client: TestClient, db: Session
) -> None:
    email = f"regular-{uuid.uuid4().hex[:8]}@example.com"
    invite_code = f"REG{uuid.uuid4().hex[:5].upper()}"
    _create_invite(db, code=invite_code, email=email, grant_founding_status=False)

    user_data = _register_instructor(client, email=email, invite_code=invite_code)

    instructor = db.query(InstructorProfile).filter_by(user_id=user_data["id"]).first()
    assert instructor is not None
    assert instructor.is_founding_instructor is False


def test_founding_cap_enforced(
    client: TestClient, db: Session, test_instructor
) -> None:
    profile = test_instructor.instructor_profile
    profile.is_founding_instructor = True
    profile.founding_granted_at = datetime.now(timezone.utc)
    db.flush()

    config_service = ConfigService(db)
    config, _ = config_service.get_pricing_config()
    config["founding_instructor_cap"] = 1
    config_service.set_pricing_config(config)
    db.commit()

    email = f"second-{uuid.uuid4().hex[:8]}@example.com"
    invite_code = f"SEC{uuid.uuid4().hex[:5].upper()}"
    _create_invite(db, code=invite_code, email=email, grant_founding_status=True)

    user_data = _register_instructor(client, email=email, invite_code=invite_code)

    instructor = db.query(InstructorProfile).filter_by(user_id=user_data["id"]).first()
    assert instructor is not None
    assert instructor.is_founding_instructor is False


def test_registration_response_includes_founding_status_when_granted(
    client: TestClient, db: Session
) -> None:
    """Registration response should include founding_instructor_granted=True when granted."""
    email = f"response-founder-{uuid.uuid4().hex[:8]}@example.com"
    invite_code = f"RESP{uuid.uuid4().hex[:4].upper()}"
    _create_invite(db, code=invite_code, email=email, grant_founding_status=True)

    user_data = _register_instructor(client, email=email, invite_code=invite_code)

    # Response should include founding status field
    assert "founding_instructor_granted" in user_data
    assert user_data["founding_instructor_granted"] is True


def test_registration_response_includes_founding_status_none_when_not_attempted(
    client: TestClient, db: Session
) -> None:
    """Registration response should include founding_instructor_granted=None when not attempted."""
    email = f"response-regular-{uuid.uuid4().hex[:8]}@example.com"
    invite_code = f"NOFND{uuid.uuid4().hex[:4].upper()}"
    _create_invite(db, code=invite_code, email=email, grant_founding_status=False)

    user_data = _register_instructor(client, email=email, invite_code=invite_code)

    # Response should include founding status field
    assert "founding_instructor_granted" in user_data
    assert user_data["founding_instructor_granted"] is None  # Not attempted


def test_registration_response_includes_founding_status_false_when_cap_reached(
    client: TestClient, db: Session, test_instructor
) -> None:
    """When cap is reached, response should have founding_instructor_granted=False."""
    # Set up existing founding instructor at cap
    profile = test_instructor.instructor_profile
    profile.is_founding_instructor = True
    profile.founding_granted_at = datetime.now(timezone.utc)
    db.flush()

    config_service = ConfigService(db)
    config, _ = config_service.get_pricing_config()
    config["founding_instructor_cap"] = 1
    config_service.set_pricing_config(config)
    db.commit()

    email = f"response-cap-{uuid.uuid4().hex[:8]}@example.com"
    invite_code = f"CAP{uuid.uuid4().hex[:5].upper()}"
    _create_invite(db, code=invite_code, email=email, grant_founding_status=True)

    user_data = _register_instructor(client, email=email, invite_code=invite_code)

    # Response should show founding status was not granted
    assert "founding_instructor_granted" in user_data
    assert user_data["founding_instructor_granted"] is False


def test_student_registration_response_has_null_founding_status(
    client: TestClient, db: Session
) -> None:
    """Student registration should have founding_instructor_granted=None."""
    email = f"student-{uuid.uuid4().hex[:8]}@example.com"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "Student",
            "phone": "+12125550001",
            "zip_code": "10001",
            "role": "student",
        },
    )

    assert response.status_code == 201
    user_data = response.json()

    # Students shouldn't have founding status (should be None)
    assert "founding_instructor_granted" in user_data
    assert user_data["founding_instructor_granted"] is None
