from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.services import get_background_check_service
from app.auth import get_password_hash
from app.integrations.checkr_client import CheckrClient
from app.main import fastapi_app as app
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_service import BackgroundCheckService


def _create_instructor(db, *, status: str | None = None, report_id: str | None = None):
    owner = User(
        email="owner@example.com",
        hashed_password=get_password_hash("Passw0rd!"),
        first_name="Owner",
        last_name="Instructor",
        zip_code="10001",
    )
    db.add(owner)
    db.flush()

    profile = InstructorProfile(user_id=owner.id)
    if status:
        profile.bgc_status = status
    if report_id:
        profile.bgc_report_id = report_id
    db.add(profile)
    db.flush()
    db.commit()
    db.refresh(owner)
    db.refresh(profile)

    return owner, profile


@pytest.fixture(autouse=True)
def override_background_check_service(db):
    def _override():
        repository = InstructorProfileRepository(db)

        class DummyCheckr(CheckrClient):
            async def create_candidate(self, **payload):  # type: ignore[override]
                return {"id": "cand_test"}

            async def create_invitation(self, *, candidate_id: str, package: str):  # type: ignore[override]
                return {"id": "inv_test", "report_id": "rpt_123"}

        client = DummyCheckr(api_key="sk_test", base_url="https://api.checkr.com/v1")
        return BackgroundCheckService(
            db,
            client=client,
            repository=repository,
            package="essential",
            env="sandbox",
        )
    app.dependency_overrides[get_background_check_service] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_background_check_service, None)


@contextmanager
def auth_override(user: User):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_invite_creates_pending_status(client, db):
    owner, profile = _create_instructor(db, status="failed")
    with auth_override(owner):
        response = client.post(f"/api/instructors/{profile.id}/bgc/invite")

    refreshed = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert refreshed.bgc_status == "pending"
    assert refreshed.bgc_report_id == "rpt_123"
    assert refreshed.bgc_env == "sandbox"

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "pending", payload
    assert payload["report_id"] == "rpt_123"
    assert payload["already_in_progress"] is False


def test_invite_is_idempotent_when_pending(client, db):
    owner, profile = _create_instructor(db, status="pending", report_id="rpt_existing")

    with auth_override(owner):
        response = client.post(f"/api/instructors/{profile.id}/bgc/invite")

    assert response.status_code == 200
    payload = response.json()
    assert payload["already_in_progress"] is True
    assert payload["status"] == "pending"
    assert payload["report_id"] == "rpt_existing"


def test_invite_forbidden_for_other_users(client, db):
    owner, profile = _create_instructor(db, status="failed")
    other = User(
        email="other@example.com",
        hashed_password=get_password_hash("Passw0rd!"),
        first_name="Other",
        last_name="User",
        zip_code="10002",
    )
    db.add(other)
    db.flush()
    db.commit()
    db.refresh(other)

    with auth_override(other):
        response = client.post(f"/api/instructors/{profile.id}/bgc/invite")

    assert response.status_code == 403


def test_status_endpoint_returns_current_values(client, db):
    owner, profile = _create_instructor(db, status="review", report_id="rpt_status")
    profile.bgc_env = "sandbox"
    profile.bgc_completed_at = datetime.now(timezone.utc)
    db.flush()

    with auth_override(owner):
        response = client.get(f"/api/instructors/{profile.id}/bgc/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "review"
    assert payload["report_id"] == "rpt_status"
    assert payload["env"] == "sandbox"


def test_status_not_found(client, db):
    owner, _ = _create_instructor(db, status="failed")
    with auth_override(owner):
        response = client.get("/api/instructors/01NOTEXISTING/bgc/status")

    assert response.status_code == 404
