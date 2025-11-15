import base64
from datetime import datetime, timedelta, timezone
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
from app.models.instructor import BackgroundCheck, BackgroundJob, BGCWebhookLog, InstructorProfile
from app.models.user import User
from app.repositories.bgc_webhook_log_repository import BGCWebhookLogRepository
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


def _create_instructor_with_candidate(
    db: Session, candidate_id: str, *, status: str = "pending", invitation_id: str | None = None
) -> InstructorProfile:
    user = User(
        email=f"{candidate_id}@example.com",
        hashed_password=get_password_hash("WebhookPass123!"),
        first_name="Candidate",
        last_name="Test",
        zip_code="11201",
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(user_id=user.id)
    profile.bgc_status = status
    profile.checkr_candidate_id = candidate_id
    profile.checkr_invitation_id = invitation_id
    db.add(profile)
    db.flush()
    db.refresh(profile)
    return profile


@pytest.fixture(autouse=True)
def configure_webhook_auth() -> None:
    original_secret = settings.checkr_webhook_secret
    original_api_key = settings.checkr_api_key
    original_bgc_suppression = settings.bgc_suppress_adverse_emails
    original_user = settings.checkr_webhook_user
    original_pass = settings.checkr_webhook_pass
    settings.checkr_webhook_secret = SecretStr("whsec_test_secret")
    settings.checkr_api_key = SecretStr("sk_test_webhook")
    settings.checkr_webhook_user = SecretStr("hookuser")
    settings.checkr_webhook_pass = SecretStr("hookpass")
    try:
        yield
    finally:
        settings.checkr_webhook_secret = original_secret
        settings.checkr_api_key = original_api_key
        settings.bgc_suppress_adverse_emails = original_bgc_suppression
        settings.checkr_webhook_user = original_user
        settings.checkr_webhook_pass = original_pass


@pytest.fixture(autouse=True)
def override_instructor_repo(db):
    def _override() -> InstructorProfileRepository:
        return InstructorProfileRepository(db)

    app.dependency_overrides[get_instructor_repo] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_instructor_repo, None)


def _auth_headers(username: str = "hookuser", password: str = "hookpass") -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def test_report_completed_clear_updates_profile(client, db: Session) -> None:
    profile = _create_instructor_with_report(db, report_id="rpt_clear")

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_clear", "result": "clear"}},
    }
    body = json.dumps(payload).encode("utf-8")
    response = client.post(
        "/webhooks/checkr/",
        content=body,
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    updated = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert updated.bgc_status == "passed"
    assert updated.bgc_completed_at is not None

    # Idempotent retry
    response_retry = client.post("/webhooks/checkr/", content=body, headers=_auth_headers())
    assert response_retry.status_code == 200

    updated_retry = db.query(InstructorProfile).filter_by(id=profile.id).one()
    assert updated_retry.bgc_status == "passed"
    assert updated_retry.bgc_completed_at is not None


def test_report_completed_without_report_binding_uses_candidate(client, db: Session) -> None:
    profile = _create_instructor_with_candidate(db, candidate_id="cand_missing_report")

    payload = {
        "type": "report.completed",
        "data": {
            "object": {
                "id": "rpt_missing_report",
                "result": "clear",
                "candidate_id": "cand_missing_report",
                "completed_at": "2024-01-01T02:03:04Z",
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    response = client.post("/webhooks/checkr/", content=body, headers=_auth_headers())

    assert response.status_code == 200
    db.refresh(profile)
    assert profile.bgc_report_id == "rpt_missing_report"
    assert profile.bgc_status == "passed"
    assert profile.bgc_report_result == "clear"
    assert profile.bgc_completed_at is not None
    assert profile.bgc_valid_until is not None

    history = (
        db.query(BackgroundCheck)
        .filter(BackgroundCheck.instructor_id == profile.id)
        .all()
    )
    assert len(history) == 1
    assert history[0].result == "clear"


def test_report_created_binds_report_to_candidate(client, db: Session) -> None:
    profile = _create_instructor_with_candidate(db, candidate_id="cand_report_created")
    payload = {
        "type": "report.created",
        "data": {
            "object": {
                "id": "rpt_created_binding",
                "status": "pending",
                "candidate_id": "cand_report_created",
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    response = client.post("/webhooks/checkr/", content=body, headers=_auth_headers())

    assert response.status_code == 200
    db.refresh(profile)
    assert profile.bgc_report_id == "rpt_created_binding"
    assert profile.bgc_status == "pending"


def test_report_completed_unknown_candidate_enqueues_job(client, db: Session) -> None:
    _create_instructor_with_candidate(db, candidate_id="cand_existing_bound")
    db.query(BackgroundJob).delete()
    db.commit()

    payload = {
        "type": "report.completed",
        "data": {
            "object": {
                "id": "rpt_unknown_candidate",
                "result": "clear",
                "candidate_id": "cand_does_not_exist",
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    response = client.post("/webhooks/checkr/", content=body, headers=_auth_headers())

    assert response.status_code == 200
    jobs = db.query(BackgroundJob).filter(BackgroundJob.type == "webhook.report_completed").all()
    assert len(jobs) == 1
    assert jobs[0].payload.get("candidate_id") == "cand_does_not_exist"


def test_maps_completed_and_logs_delivery(client, db: Session) -> None:
    db.query(BGCWebhookLog).delete()
    db.commit()

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_log", "result": "clear", "object": "report"}},
    }
    body = json.dumps(payload).encode("utf-8")
    headers = _auth_headers()
    headers["X-Checkr-Delivery-Id"] = "delivery-log-1"
    headers["X-Checkr-Signature"] = "sig-log"

    response = client.post("/webhooks/checkr/", content=body, headers=headers)

    assert response.status_code == 200
    repo = BGCWebhookLogRepository(db)
    rows, _ = repo.list_filtered(limit=1)
    assert rows, "Expected webhook log entry"
    entry = rows[0]
    assert entry.event_type == "report.completed"
    assert entry.delivery_id == "delivery-log-1"
    assert entry.http_status == 200
    assert entry.signature == "sig-log"
    assert entry.payload_json.get("type") == "report.completed"


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

        response = client.post("/webhooks/checkr/", content=body, headers=_auth_headers())

        assert response.status_code == 200
        updated = db.query(InstructorProfile).filter_by(id=profile.id).one()
        assert updated.bgc_status == "review"
        assert updated.bgc_report_result == "consider"
        assert updated.bgc_completed_at is not None
        assert calls["profile_id"] == profile.id
    finally:
        app.dependency_overrides.pop(get_background_check_workflow_service, None)


def test_missing_basic_auth_returns_401(client):
    payload = {"type": "report.completed", "data": {"object": {"id": "rpt_invalid"}}}
    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/webhooks/checkr/",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401


def test_invalid_basic_auth_returns_403(client):
    payload = {"type": "report.completed", "data": {"object": {"id": "rpt_invalid"}}}
    body = json.dumps(payload).encode("utf-8")

    bad_headers = {
        "Authorization": "Basic " + base64.b64encode(b"wrong:creds").decode("utf-8"),
        "Content-Type": "application/json",
    }
    response = client.post("/webhooks/checkr/", content=body, headers=bad_headers)

    assert response.status_code == 403


def test_unknown_report_id_is_noop(client, db: Session) -> None:
    profile = _create_instructor_with_report(db, report_id="rpt_existing", status="pending")

    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rpt_unknown", "result": "clear"}},
    }
    body = json.dumps(payload).encode("utf-8")
    response = client.post(
        "/webhooks/checkr/",
        content=body,
        headers=_auth_headers(),
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
