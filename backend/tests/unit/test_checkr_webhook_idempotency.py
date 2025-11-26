import base64
import json

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.api.dependencies.repositories import get_background_job_repo
from app.api.dependencies.services import get_background_check_workflow_service
from app.core.config import settings
from app.main import fastapi_app as app
from app.routes.v1.webhooks_checkr import _compute_signature, _delivery_cache


class _StubRepo:
    def bind_report_to_candidate(self, *_args, **_kwargs):
        return None

    def bind_report_to_invitation(self, *_args, **_kwargs):
        return None


class StubWorkflow:
    def __init__(self) -> None:
        self.report_completed_calls = 0
        self.repo = _StubRepo()

    def handle_report_completed(
        self,
        *,
        report_id: str,
        result: str,
        assessment: str | None = None,
        package: str | None,
        env: str,
        completed_at,
        candidate_id: str | None = None,
        invitation_id: str | None = None,
        includes_canceled: bool | None = None,
        **_kwargs,
    ):
        self.report_completed_calls += 1
        return result, None, False

    def handle_report_suspended(self, report_id: str) -> None:  # pragma: no cover - not used here
        pass


class StubJobRepository:
    def enqueue(self, **_kwargs):  # pragma: no cover - not exercised in this test
        return "job-id"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def configure_webhook_basic_auth():
    original_user = settings.checkr_webhook_user
    original_pass = settings.checkr_webhook_pass
    original_api_key = settings.checkr_api_key
    settings.checkr_webhook_user = SecretStr("hookuser")
    settings.checkr_webhook_pass = SecretStr("hookpass")
    settings.checkr_api_key = SecretStr("sk_test_webhook")
    try:
        yield
    finally:
        settings.checkr_webhook_user = original_user
        settings.checkr_webhook_pass = original_pass
        settings.checkr_api_key = original_api_key


def _auth_headers():
    token = base64.b64encode(b"hookuser:hookpass").decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _webhook_headers(body: bytes | str):
    headers = _auth_headers()
    secret_value = settings.checkr_api_key.get_secret_value()
    body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    headers["X-Checkr-Signature"] = _compute_signature(secret_value, body_bytes)
    return headers


def test_duplicate_delivery_is_ignored(monkeypatch, client):
    workflow = StubWorkflow()

    app.dependency_overrides[get_background_check_workflow_service] = lambda: workflow
    app.dependency_overrides[get_background_job_repo] = lambda: StubJobRepository()

    try:
        _delivery_cache.clear()

        payload = {
            "type": "report.completed",
            "data": {"object": {"id": "rpt_abc", "result": "clear", "package": "standard"}},
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        headers = _webhook_headers(body)
        headers["X-Checkr-Delivery-Id"] = "delivery-1"

        first = client.post("/api/v1/webhooks/checkr", content=body, headers=headers)
        assert first.status_code == 200
        assert workflow.report_completed_calls == 1

        second = client.post("/api/v1/webhooks/checkr", content=body, headers=headers)
        assert second.status_code == 200
        assert workflow.report_completed_calls == 1
    finally:
        app.dependency_overrides.pop(get_background_check_workflow_service, None)
        app.dependency_overrides.pop(get_background_job_repo, None)
        _delivery_cache.clear()
