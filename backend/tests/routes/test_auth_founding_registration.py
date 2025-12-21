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
