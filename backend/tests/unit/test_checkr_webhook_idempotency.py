import json

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies.repositories import get_background_job_repo
from app.api.dependencies.services import get_background_check_workflow_service
from app.main import fastapi_app as app
from app.routes.webhooks_checkr import _delivery_cache


class StubWorkflow:
    def __init__(self) -> None:
        self.report_completed_calls = 0

    def handle_report_completed(
        self,
        *,
        report_id: str,
        result: str,
        package: str | None,
        env: str,
        completed_at,
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


def test_duplicate_delivery_is_ignored(monkeypatch, client):
    workflow = StubWorkflow()

    app.dependency_overrides[get_background_check_workflow_service] = lambda: workflow
    app.dependency_overrides[get_background_job_repo] = lambda: StubJobRepository()

    monkeypatch.setattr(
        "app.routes.webhooks_checkr._verify_signature",
        lambda payload, signature: None,
    )

    try:
        _delivery_cache.clear()

        payload = {
            "type": "report.completed",
            "data": {"object": {"id": "rpt_abc", "result": "clear", "package": "standard"}},
        }
        body = json.dumps(payload)

        headers = {
            "X-Checkr-Delivery-Id": "delivery-1",
            "Content-Type": "application/json",
        }

        first = client.post("/webhooks/checkr/", content=body, headers=headers)
        assert first.status_code == 200
        assert workflow.report_completed_calls == 1

        second = client.post("/webhooks/checkr/", content=body, headers=headers)
        assert second.status_code == 200
        assert workflow.report_completed_calls == 1
    finally:
        app.dependency_overrides.pop(get_background_check_workflow_service, None)
        app.dependency_overrides.pop(get_background_job_repo, None)
        _delivery_cache.clear()
