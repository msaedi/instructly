from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import pytest

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.services import get_background_check_service
from app.auth import get_password_hash
from app.core.config import settings
from app.core.exceptions import ServiceException
from app.integrations.checkr_client import CheckrClient, CheckrError
from app.main import fastapi_app as app
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_service import BackgroundCheckService

CSRF_COOKIE = "csrftoken"
CSRF_HEADER = "X-CSRFToken"
CSRF_ORIGIN = "https://app.instainstru.com"


def _csrf_headers(client):
    token = "testtoken"
    client.cookies.set(CSRF_COOKIE, token)
    return {CSRF_HEADER: token, "Origin": CSRF_ORIGIN}


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


DISCLOSURE_VERSION = "v1.0.0"


def _record_consent(client, profile_id: str, headers):
    response = client.post(
        f"/api/v1/instructors/{profile_id}/bgc/consent",
        headers=headers,
        json={
            "consent_version": DISCLOSURE_VERSION,
            "disclosure_version": DISCLOSURE_VERSION,
            "user_agent": "pytest-client",
        },
    )
    assert response.status_code == 200


def test_consent_persists_disclosure_version(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)

    _record_consent(client, profile.id, headers)

    repo = InstructorProfileRepository(db)
    latest = repo.latest_consent(profile.id)
    assert latest is not None
    assert latest.consent_version == DISCLOSURE_VERSION


@pytest.fixture(autouse=True)
def override_background_check_service(db, monkeypatch):
    def _override():
        repository = InstructorProfileRepository(db)

        class DummyCheckr(CheckrClient):
            def create_candidate(  # type: ignore[override]
                self,
                *,
                idempotency_key: str | None = None,
                **payload,
            ):
                return {"id": "cand_test"}

            def create_invitation(self, **payload):  # type: ignore[override]
                return {
                    "id": "inv_test",
                    "report_id": "rpt_123",
                    **payload,
                }

        client = DummyCheckr(api_key="sk_test", base_url="https://api.checkr.com/v1")
        service = BackgroundCheckService(
            db,
            client=client,
            repository=repository,
            package="essential",
            env="sandbox",
        )
        return service

    monkeypatch.setattr(
        BackgroundCheckService,
        "_resolve_work_location",
        lambda self, _zip: {"country": "US", "state": "NY", "city": "New York"},
    )
    app.dependency_overrides[get_background_check_service] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_background_check_service, None)


@pytest.fixture(autouse=True)
def force_local_site_mode(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")


@pytest.fixture(autouse=True)
def mock_geocoding_provider(monkeypatch):
    previous = settings.geocoding_provider
    settings.geocoding_provider = "mock"
    try:
        yield
    finally:
        settings.geocoding_provider = previous


@pytest.fixture
def owner_auth_override():
    def _apply(user: User) -> None:
        app.dependency_overrides[get_current_user] = lambda: user

    try:
        yield _apply
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@contextmanager
def auth_override(user: User):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_invite_creates_pending_status(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)
    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

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


def test_invite_is_idempotent_when_pending(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="pending", report_id="rpt_existing")

    owner_auth_override(owner)
    headers = _csrf_headers(client)
    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["already_in_progress"] is True
    assert payload["status"] == "pending"
    assert payload["report_id"] == "rpt_existing"


def test_invite_requires_recent_consent(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)

    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert response.status_code == 400
    detail_payload = response.json()["detail"]
    if isinstance(detail_payload, dict):
        detail_message = detail_payload.get("message")
    else:
        detail_message = detail_payload
    assert detail_message == "FCRA consent required"

    _record_consent(client, profile.id, headers)


def test_invite_returns_specific_error_on_checkr_auth_failure(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    class AuthFailureService:
        config_error = None
        package = "essential"

        def invite(self, *_args, **_kwargs):
            err = CheckrError("Unauthorized", status_code=401, error_type="auth_error")
            raise ServiceException("Checkr rejected credentials") from err

    previous_service = app.dependency_overrides[get_background_check_service]
    app.dependency_overrides[get_background_check_service] = lambda: AuthFailureService()
    try:
        response = client.post(
            f"/api/v1/instructors/{profile.id}/bgc/invite",
            headers=headers,
            json={},
        )
    finally:
        app.dependency_overrides[get_background_check_service] = previous_service

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "checkr_auth_error"
    assert payload["title"] == "Checkr authentication failed"


def test_recheck_returns_specific_error_on_checkr_auth_failure(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="passed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    class AuthFailureService:
        config_error = None

        def invite(self, *_args, **_kwargs):
            err = CheckrError("Unauthorized", status_code=401, error_type="auth_error")
            raise ServiceException("Checkr rejected credentials") from err

    previous_service = app.dependency_overrides[get_background_check_service]
    app.dependency_overrides[get_background_check_service] = lambda: AuthFailureService()
    try:
        response = client.post(
            f"/api/v1/instructors/{profile.id}/bgc/recheck",
            headers=headers,
            json={},
        )
    finally:
        app.dependency_overrides[get_background_check_service] = previous_service

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "checkr_auth_error"
    assert payload["title"] == "Checkr authentication failed"


def test_invite_returns_specific_error_on_package_not_found(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    class PackageFailureService:
        config_error = None
        package = "missing_package"

        def invite(self, *_args, **_kwargs):
            err = CheckrError(
                "Package not found",
                status_code=404,
                error_type="not_found",
                error_body={"error": "Package not found"},
            )
            raise ServiceException("Invalid package") from err

    previous_service = app.dependency_overrides[get_background_check_service]
    app.dependency_overrides[get_background_check_service] = lambda: PackageFailureService()
    try:
        response = client.post(
            f"/api/v1/instructors/{profile.id}/bgc/invite",
            headers=headers,
            json={},
        )
    finally:
        app.dependency_overrides[get_background_check_service] = previous_service

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "checkr_package_not_found"
    assert payload["title"] == "Checkr package misconfigured"
    assert "package slug does not exist" in payload["detail"]


def test_recheck_returns_specific_error_on_package_not_found(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="passed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    class PackageFailureService:
        config_error = None

        def invite(self, *_args, **_kwargs):
            err = CheckrError(
                "Package not found",
                status_code=404,
                error_type="not_found",
                error_body="Package not found",
            )
            raise ServiceException("Invalid package") from err

    previous_service = app.dependency_overrides[get_background_check_service]
    app.dependency_overrides[get_background_check_service] = lambda: PackageFailureService()
    try:
        response = client.post(
            f"/api/v1/instructors/{profile.id}/bgc/recheck",
            headers=headers,
            json={},
        )
    finally:
        app.dependency_overrides[get_background_check_service] = previous_service

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "checkr_package_not_found"
    assert payload["title"] == "Checkr package misconfigured"


def test_invite_includes_work_location_payloads(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)
    owner.zip_code = "10036"
    db.add(owner)
    db.commit()

    captured: dict[str, dict[str, Any]] = {}

    def _override():
        repository = InstructorProfileRepository(db)

        class CaptureCheckr(CheckrClient):
            def create_candidate(  # type: ignore[override]
                self,
                *,
                idempotency_key: str | None = None,
                **payload,
            ):
                captured["candidate"] = payload
                return {"id": "cand_cap"}

            def create_invitation(self, **payload):  # type: ignore[override]
                captured["invitation"] = payload
                return {
                    "id": "inv_cap",
                    "report_id": "rpt_cap",
                    **payload,
                }

        client_obj = CaptureCheckr(api_key="sk_test", base_url="https://api.checkr.com/v1")
        return BackgroundCheckService(
            db,
            client=client_obj,
            repository=repository,
            package="essential",
            env="sandbox",
        )

    app.dependency_overrides[get_background_check_service] = _override
    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    candidate_payload = captured["candidate"]
    invitation_payload = captured["invitation"]
    assert candidate_payload["zipcode"] == "10036"
    assert candidate_payload["work_location"]["state"] == "NY"
    assert candidate_payload["work_location"]["city"] == "New York"
    assert invitation_payload["work_locations"][0]["state"] == "NY"
    assert invitation_payload["work_locations"][0]["city"] == "New York"


def test_invite_returns_error_when_zip_missing(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)
    owner.zip_code = ""
    db.add(owner)
    db.commit()

    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "invalid_work_location"
    assert payload["title"] == "Invalid work location"
    assert (
        payload["detail"]
        == "We couldn't verify your primary teaching ZIP code. Please check it and try again."
    )


def test_invite_returns_specific_error_on_checkr_work_location_failure(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    class WorkLocationFailureService:
        config_error = None
        package = "essential"

        def invite(self, *_args, **_kwargs):
            err = CheckrError(
                "work_locations is invalid",
                status_code=400,
                error_type="invalid_request_error",
                error_body="work_locations is invalid",
            )
            raise ServiceException("Work location rejected") from err

    original_service = app.dependency_overrides[get_background_check_service]
    app.dependency_overrides[get_background_check_service] = lambda: WorkLocationFailureService()
    try:
        response = client.post(
            f"/api/v1/instructors/{profile.id}/bgc/invite",
            headers=headers,
            json={},
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload["code"] == "checkr_work_location_error"
        assert payload["title"] == "Checkr work location error"
    finally:
        app.dependency_overrides[get_background_check_service] = original_service

    valid_response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert valid_response.status_code == 200


def test_invite_returns_provider_error_when_geocoder_unavailable(client, db, owner_auth_override, monkeypatch):
    owner, profile = _create_instructor(db, status="failed")
    owner.zip_code = "10036"
    db.add(owner)
    db.commit()
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    def error_resolver(self, zip_code: str):
        raise ServiceException(
            "Geocoding provider unavailable",
            code="geocoding_provider_error",
            details={
                "zip_code": zip_code,
                "provider": "mapbox",
                "provider_status": "REQUEST_DENIED",
            },
        )

    monkeypatch.setattr(BackgroundCheckService, "_resolve_work_location", error_resolver)

    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "geocoding_provider_error"
    assert payload["title"] == "Location lookup unavailable"
    provider_error = payload.get("provider_error") or {}
    assert provider_error.get("status") == "REQUEST_DENIED"
    assert provider_error.get("zip") == "10036"


def test_invite_returns_invalid_work_location_for_unresolvable_zip(
    client, db, owner_auth_override, monkeypatch
):
    owner, profile = _create_instructor(db, status="failed")
    owner.zip_code = "99999"
    db.add(owner)
    db.commit()
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    def zero_result_resolver(self, zip_code: str):
        raise ServiceException(
            "Unable to resolve work location",
            code="invalid_work_location",
            details={
                "zip_code": zip_code,
                "reason": "zero_results",
                "provider": "mapbox",
            },
        )

    monkeypatch.setattr(BackgroundCheckService, "_resolve_work_location", zero_result_resolver)

    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "invalid_work_location"
    assert payload["title"] == "Invalid work location"
    assert "99999" in payload["detail"]
    debug_info = payload.get("debug") or {}
    assert debug_info.get("reason") == "zero_results"
    assert debug_info.get("zip") == "99999"


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

    def _override_other() -> None:
        app.dependency_overrides[get_current_user] = lambda: other

    try:
        _override_other()
        headers = _csrf_headers(client)
        response = client.post(
            f"/api/v1/instructors/{profile.id}/bgc/invite",
            headers=headers,
            json={},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403


def test_invite_200_json(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    headers["Origin"] = "http://localhost:3000"
    _record_consent(client, profile.id, headers)

    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "pending"
    assert response.headers.get("access-control-allow-origin") == headers["Origin"]


def test_invite_4xx_single_send_cors(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    headers["Origin"] = "http://beta-local.instainstru.com:3000"
    _record_consent(client, profile.id, headers)

    original_override = app.dependency_overrides.get(get_background_check_service)

    class ErroringService:
        config_error = None
        package = "essential"

        def invite(self, *_args, **_kwargs):
            raise ServiceException(
                "Failed to initiate instructor background check"
            ) from CheckrError(
                "Checkr API responded with status 422",
                status_code=422,
                error_type="validation_error",
            )

    app.dependency_overrides[get_background_check_service] = lambda: ErroringService()
    try:
        response = client.post(
            f"/api/v1/instructors/{profile.id}/bgc/invite",
            headers=headers,
            json={},
        )
    finally:
        if original_override is None:
            app.dependency_overrides.pop(get_background_check_service, None)
        else:
            app.dependency_overrides[get_background_check_service] = original_override

    assert response.status_code == 400
    problem = response.json()
    assert problem["code"] == "bgc_invite_failed"
    assert problem["checkr_error"]["http_status"] == 422
    assert response.headers.get("access-control-allow-origin") == headers["Origin"]


def test_status_endpoint_returns_current_values(client, db):
    owner, profile = _create_instructor(db, status="review", report_id="rpt_status")
    profile.bgc_env = "sandbox"
    profile.bgc_completed_at = datetime.now(timezone.utc)
    db.flush()

    with auth_override(owner):
        response = client.get(f"/api/v1/instructors/{profile.id}/bgc/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "review"
    assert payload["report_id"] == "rpt_status"
    assert payload["env"] == "sandbox"


def test_status_not_found(client, db):
    owner, _ = _create_instructor(db, status="failed")
    with auth_override(owner):
        response = client.get("/api/v1/instructors/01NOTEXISTING/bgc/status")

    assert response.status_code == 404


def test_invite_returns_specific_error_when_rate_limited(client, db, owner_auth_override):
    owner, profile = _create_instructor(db, status="failed")
    owner_auth_override(owner)
    headers = _csrf_headers(client)
    _record_consent(client, profile.id, headers)

    # Manually set a recent invited_at
    profile.bgc_invited_at = datetime.now(timezone.utc)
    db.add(profile)
    db.commit()

    response = client.post(
        f"/api/v1/instructors/{profile.id}/bgc/invite",
        headers=headers,
        json={},
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["code"] == "bgc_invite_rate_limited"
    assert payload["title"] == "Background check recently requested"
    assert "wait up to 24 hours" in payload["detail"]
