from __future__ import annotations

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

DISCLOSURE_VERSION = "v1.0.0"


def _csrf_headers(client):
    token = "integrationtoken"
    client.cookies.set("csrftoken", token)
    return {"X-CSRFToken": token, "Origin": "https://app.instainstru.com"}


def _create_owner_and_profile(db, *, status: str | None = None):
    owner = User(
        email="integration-owner@example.com",
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
            async def create_candidate(  # type: ignore[override]
                self,
                *,
                idempotency_key: str | None = None,
                **payload,
            ):
                return {"id": "cand_test"}

            async def create_invitation(  # type: ignore[override]
                self,
                *,
                candidate_id: str,
                package: str,
                workflow: str | None = None,
                **_kwargs,
            ):
                return {
                    "id": "inv_test",
                    "report_id": "rpt_integration",
                    "candidate_id": candidate_id,
                    "package": package,
                    "workflow": workflow,
                }

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


@pytest.fixture
def owner_auth_override():
    def _apply(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user

    try:
        yield _apply
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _record_consent(client, profile_id: str, headers):
    response = client.post(
        f"/api/instructors/{profile_id}/bgc/consent",
        headers=headers,
        json={
            "consent_version": DISCLOSURE_VERSION,
            "disclosure_version": DISCLOSURE_VERSION,
            "user_agent": "integration-tests",
        },
    )
    assert response.status_code == 200


def test_invite_blocked_without_recent_consent(client, db, owner_auth_override):
    owner, profile = _create_owner_and_profile(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)

    response = client.post(
        f"/api/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload.get("detail") == "FCRA consent required"
    code = payload.get("code")
    if code is None:
        extra = payload.get("extra")
        if isinstance(extra, dict):
            code = extra.get("code")
    assert code == "bgc_consent_required"


def test_consent_persists_disclosure_version(client, db, owner_auth_override):
    owner, profile = _create_owner_and_profile(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)

    _record_consent(client, profile.id, headers)

    repo = InstructorProfileRepository(db)
    latest = repo.latest_consent(profile.id)
    assert latest is not None
    assert latest.consent_version == DISCLOSURE_VERSION
    assert latest.consented_at is not None


def test_invite_succeeds_after_recent_consent(client, db, owner_auth_override):
    owner, profile = _create_owner_and_profile(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)

    _record_consent(client, profile.id, headers)

    response = client.post(
        f"/api/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "pending"
    db.expire_all()
    refreshed = db.get(InstructorProfile, profile.id)
    assert refreshed is not None
    assert refreshed.bgc_status == "pending"
    assert refreshed.bgc_invited_at is not None
