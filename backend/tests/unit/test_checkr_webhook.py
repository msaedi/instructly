from hashlib import sha256
import hmac
import json

from pydantic import SecretStr
import pytest

from app.api.dependencies.services import get_background_check_service
from app.auth import get_password_hash
from app.core.config import settings
from app.integrations.checkr_client import CheckrClient
from app.main import fastapi_app as app
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_service import BackgroundCheckService


def _create_instructor_with_report(
    db, report_id: str, status: str = "pending"
) -> InstructorProfile:
    user = User(
        email="webhook-instructor@example.com",
        hashed_password=get_password_hash("WebhookPass123!"),
        first_name="Grace",
        last_name="Hopper",
        zip_code="11201",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = status
    profile.bgc_report_id = report_id
    db.add(profile)
    db.flush()
    persisted = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert persisted.bgc_report_id == report_id
    db.refresh(profile)
    return profile


def _sign_payload(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, sha256)
    return mac.hexdigest()


@pytest.fixture(autouse=True)
def configure_webhook_secret():
    original_secret = settings.checkr_webhook_secret
    original_api_key = settings.checkr_api_key
    settings.checkr_webhook_secret = SecretStr("whsec_test_secret")
    settings.checkr_api_key = SecretStr("sk_test_webhook")
    try:
        yield
    finally:
        settings.checkr_webhook_secret = original_secret
        settings.checkr_api_key = original_api_key


@pytest.fixture(autouse=True)
def override_background_check_service(db):
    def _override():
        repository = InstructorProfileRepository(db)
        client = CheckrClient(
            api_key=settings.checkr_api_key,
            base_url=settings.checkr_api_base,
        )
        return BackgroundCheckService(
            db,
            client=client,
            repository=repository,
            package=settings.checkr_package,
            env=settings.checkr_env,
        )

    app.dependency_overrides[get_background_check_service] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_background_check_service, None)


def test_report_completed_clear_updates_profile(client, db):
    profile = _create_instructor_with_report(db, report_id="rpt_clear")

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_clear", "result": "clear"}},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign_payload(body, settings.checkr_webhook_secret.get_secret_value())

    response = client.post(
        "/webhooks/checkr/",
        data=body,
        headers={"X-Checkr-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    updated = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert updated.bgc_status == "passed"
    assert updated.bgc_completed_at is not None

    # Idempotent retry
    response_retry = client.post(
        "/webhooks/checkr/",
        data=body,
        headers={"X-Checkr-Signature": signature, "Content-Type": "application/json"},
    )
    assert response_retry.status_code == 200

    updated_retry = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert updated_retry.bgc_status == "passed"
    assert updated_retry.bgc_completed_at is not None


def test_report_completed_consider_marks_review(client, db):
    profile = _create_instructor_with_report(db, report_id="rpt_consider")

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_consider", "result": "consider"}},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign_payload(body, settings.checkr_webhook_secret.get_secret_value())

    response = client.post(
        "/webhooks/checkr/",
        data=body,
        headers={"X-Checkr-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    updated = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert updated.bgc_status == "review"
    assert updated.bgc_completed_at is not None


def test_invalid_signature_returns_400(client):
    payload = {"type": "report.completed", "data": {"object": {"id": "rpt_invalid"}}}
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhooks/checkr/",
        data=body,
        headers={"X-Checkr-Signature": "bad-signature", "Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_unknown_report_id_is_noop(client, db):
    profile = _create_instructor_with_report(db, report_id="rpt_existing", status="pending")

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_unknown", "result": "clear"}},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign_payload(body, settings.checkr_webhook_secret.get_secret_value())

    response = client.post(
        "/webhooks/checkr/",
        data=body,
        headers={"X-Checkr-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    untouched = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert untouched.bgc_status == "pending"
    assert untouched.bgc_completed_at is None
