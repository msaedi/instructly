from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import types

from pydantic import SecretStr
import pytest
from sqlalchemy.orm import Session
from tests.unit.services._adverse_helpers import ensure_adverse_schema
import ulid

from app.api.dependencies.repositories import get_instructor_repo
from app.api.dependencies.services import get_background_check_workflow_service
from app.auth import get_password_hash
from app.core.config import settings
from app.main import fastapi_app as app
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_workflow_service import BackgroundCheckWorkflowService


def _create_instructor_with_report(
    db: Session, report_id: str, status: str = "pending"
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
def configure_webhook_secret() -> None:
    original_secret = settings.checkr_webhook_secret
    original_api_key = settings.checkr_api_key
    original_bgc_suppression = settings.bgc_suppress_adverse_emails
    settings.checkr_webhook_secret = SecretStr("whsec_test_secret")
    settings.checkr_api_key = SecretStr("sk_test_webhook")
    try:
        yield
    finally:
        settings.checkr_webhook_secret = original_secret
        settings.checkr_api_key = original_api_key
        settings.bgc_suppress_adverse_emails = original_bgc_suppression


@pytest.fixture(autouse=True)
def override_instructor_repo(db):
    def _override() -> InstructorProfileRepository:
        return InstructorProfileRepository(db)

    app.dependency_overrides[get_instructor_repo] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_instructor_repo, None)


def test_report_completed_clear_updates_profile(client, db: Session) -> None:
    profile = _create_instructor_with_report(db, report_id="rpt_clear")

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_clear", "result": "clear"}},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign_payload(body, settings.checkr_webhook_secret.get_secret_value())

    response = client.post(
        "/webhooks/checkr/",
        content=body,
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
        content=body,
        headers={"X-Checkr-Signature": signature, "Content-Type": "application/json"},
    )
    assert response_retry.status_code == 200

    updated_retry = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert updated_retry.bgc_status == "passed"
    assert updated_retry.bgc_completed_at is not None


def test_report_completed_consider_marks_review(client, db: Session) -> None:
    profile = _create_instructor_with_report(db, report_id="rpt_consider")
    settings.bgc_suppress_adverse_emails = True

    repo = InstructorProfileRepository(db)
    workflow = BackgroundCheckWorkflowService(repo)
    calls: dict[str, str] = {}

    def fake_schedule(self, profile_id: str) -> None:
        calls["profile_id"] = profile_id

    workflow.schedule_final_adverse_action = types.MethodType(fake_schedule, workflow)

    app.dependency_overrides[get_background_check_workflow_service] = lambda: workflow
    try:
        payload = {
            "type": "report.completed",
            "data": {"object": {"id": "rpt_consider", "result": "consider"}},
        }
        body = json.dumps(payload).encode("utf-8")
        signature = _sign_payload(body, settings.checkr_webhook_secret.get_secret_value())

        response = client.post(
            "/webhooks/checkr/",
            content=body,
            headers={"X-Checkr-Signature": signature, "Content-Type": "application/json"},
        )

        assert response.status_code == 200
        updated = db.query(InstructorProfile).filter_by(id=profile.id).one()
        assert updated.bgc_status == "review"
        assert updated.bgc_completed_at is not None
        assert calls["profile_id"] == profile.id
    finally:
        app.dependency_overrides.pop(get_background_check_workflow_service, None)


def test_invalid_signature_returns_400(client):
    payload = {"type": "report.completed", "data": {"object": {"id": "rpt_invalid"}}}
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhooks/checkr/",
        content=body,
        headers={"X-Checkr-Signature": "bad-signature", "Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_unknown_report_id_is_noop(client, db: Session) -> None:
    profile = _create_instructor_with_report(db, report_id="rpt_existing", status="pending")

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_unknown", "result": "clear"}},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign_payload(body, settings.checkr_webhook_secret.get_secret_value())

    response = client.post(
        "/webhooks/checkr/",
        content=body,
        headers={"X-Checkr-Signature": signature, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    untouched = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert untouched.bgc_status == "pending"
    assert untouched.bgc_completed_at is None


def test_execute_final_adverse_action_changes_status(db: Session) -> None:
    settings.bgc_suppress_adverse_emails = True
    ensure_adverse_schema(db)
    profile = _create_instructor_with_report(db, report_id="rpt_final", status="review")
    profile.bgc_completed_at = None

    sent_at = datetime.now(timezone.utc)
    notice_id = str(ulid.ULID())
    profile.bgc_pre_adverse_notice_id = notice_id
    profile.bgc_pre_adverse_sent_at = sent_at
    db.commit()

    repo = InstructorProfileRepository(db)
    workflow = BackgroundCheckWorkflowService(repo)
    scheduled_at = sent_at + timedelta(days=5)
    workflow.execute_final_adverse_action(profile.id, notice_id, scheduled_at)

    db.expire_all()
    refreshed = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert refreshed.bgc_status == "failed"
    assert refreshed.bgc_completed_at is not None
