from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import fastapi_app as app
from app.models.webhook_event import WebhookEvent
from app.routes.v1.payments import get_stripe_service
from app.routes.v1.webhooks_checkr import (
    get_background_check_workflow_service,
    get_background_job_repo,
    get_bgc_webhook_log_repo,
)
from app.services.webhook_ledger_service import WebhookLedgerService


class _DummyStripeService:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls = 0

    def handle_webhook_event(self, _payload):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("stripe failure")


@contextmanager
def _override_webhook_dependencies(stripe_service):
    overrides = {
        get_stripe_service: lambda: stripe_service,
        get_background_check_workflow_service: lambda: object(),
        get_background_job_repo: lambda: object(),
        get_bgc_webhook_log_repo: lambda: object(),
    }
    previous = {dep: app.dependency_overrides.get(dep) for dep in overrides}
    app.dependency_overrides.update(overrides)
    try:
        yield
    finally:
        for dep, value in previous.items():
            if value is None:
                app.dependency_overrides.pop(dep, None)
            else:
                app.dependency_overrides[dep] = value


def test_webhooks_list_returns_summary(client: TestClient, db, mcp_service_headers):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_1"},
    )
    service.mark_processed(
        event,
        related_entity_type="booking",
        related_entity_id="bk_1",
        duration_ms=120,
    )

    res = client.get("/api/v1/admin/mcp/webhooks", headers=mcp_service_headers)
    assert res.status_code == 200

    payload = res.json()
    assert payload["meta"]["returned_count"] == 1
    assert payload["summary"]["by_status"]["processed"] == 1
    assert payload["summary"]["by_source"]["stripe"] == 1

    item = payload["events"][0]
    assert item["id"] == event.id
    assert item["related_entity"] == "booking/bk_1"


def test_webhooks_failed_includes_error(client: TestClient, db, mcp_service_headers):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_2"},
    )
    service.mark_failed(event, error="boom")

    res = client.get("/api/v1/admin/mcp/webhooks/failed?source=stripe", headers=mcp_service_headers)
    assert res.status_code == 200

    payload = res.json()
    assert payload["meta"]["returned_count"] == 1
    assert payload["events"][0]["processing_error"] == "boom"
    assert payload["events"][0]["status"] == "failed"


def test_webhook_detail_returns_payload(client: TestClient, db, mcp_service_headers):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_3"},
        headers={"stripe-signature": "sig", "X-Test": "ok"},
        idempotency_key="idemp_1",
    )

    res = client.get(f"/api/v1/admin/mcp/webhooks/{event.id}", headers=mcp_service_headers)
    assert res.status_code == 200

    payload = res.json()
    detail = payload["event"]
    assert detail["payload"]["id"] == "evt_3"
    assert detail["headers"]["stripe-signature"] == "***"
    assert detail["headers"]["X-Test"] == "ok"
    assert detail["idempotency_key"] == "idemp_1"


def test_webhook_detail_not_found(client: TestClient, mcp_service_headers):
    res = client.get(
        "/api/v1/admin/mcp/webhooks/01HZZZZZZZZZZZZZZZZZZZZZZ",
        headers=mcp_service_headers,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "webhook_not_found"


def test_webhook_replay_dry_run(client: TestClient, db, mcp_service_headers):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_4"},
    )

    res = client.post(
        f"/api/v1/admin/mcp/webhooks/{event.id}/replay?dry_run=true",
        headers=mcp_service_headers,
    )
    assert res.status_code == 200

    payload = res.json()
    assert payload["meta"]["dry_run"] is True
    assert payload["note"] == "dry_run_only"
    assert payload["event"]["id"] == event.id


def test_webhook_replay_not_found(client: TestClient, mcp_service_headers):
    res = client.post(
        "/api/v1/admin/mcp/webhooks/01HZZZZZZZZZZZZZZZZZZZZZZ/replay?dry_run=false",
        headers=mcp_service_headers,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "webhook_not_found"


def test_webhook_replay_unsupported_source_marks_failed(client: TestClient, db, mcp_service_headers):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="acme",
        event_type="custom.event",
        payload={"id": "evt_5"},
    )

    stripe_service = _DummyStripeService()
    with _override_webhook_dependencies(stripe_service):
        res = client.post(
            f"/api/v1/admin/mcp/webhooks/{event.id}/replay?dry_run=false",
            headers=mcp_service_headers,
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["result"]["status"] == "failed"
    assert payload["result"]["error"] == "unsupported_source:acme"

    replay_id = payload["result"]["replay_event_id"]
    replay = db.query(WebhookEvent).filter(WebhookEvent.id == replay_id).first()
    assert replay is not None
    assert replay.status == "failed"
    assert replay.processing_error == "unsupported_source:acme"


def test_webhook_replay_stripe_failure_marks_failed(client: TestClient, db, mcp_service_headers):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.failed",
        payload={"id": "evt_7"},
    )

    stripe_service = _DummyStripeService(should_fail=True)
    with _override_webhook_dependencies(stripe_service):
        res = client.post(
            f"/api/v1/admin/mcp/webhooks/{event.id}/replay?dry_run=false",
            headers=mcp_service_headers,
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["result"]["status"] == "failed"
    assert payload["result"]["error"] == "stripe failure"
    assert stripe_service.calls == 1

    replay_id = payload["result"]["replay_event_id"]
    replay = db.query(WebhookEvent).filter(WebhookEvent.id == replay_id).first()
    assert replay is not None
    assert replay.status == "failed"
    assert replay.processing_error == "stripe failure"


def test_webhook_replay_checkr_path_invokes_processor(
    client: TestClient, db, mcp_service_headers, monkeypatch
):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="checkr",
        event_type="report.completed",
        payload={"data": {"object": ["not-a-dict"]}},
        headers={"X-Checkr-Delivery-Id": "delivery-replay"},
    )

    captured: dict[str, object] = {}

    async def _fake_processor(*, event_type, data_object, payload, headers, **kwargs):
        captured["event_type"] = event_type
        captured["data_object"] = data_object
        captured["payload"] = payload
        captured["headers"] = headers
        captured["skip_dedup"] = kwargs.get("skip_dedup")
        return None

    monkeypatch.setattr(
        "app.routes.v1.admin.mcp.webhooks._process_checkr_payload",
        _fake_processor,
    )

    stripe_service = _DummyStripeService()
    with _override_webhook_dependencies(stripe_service):
        res = client.post(
            f"/api/v1/admin/mcp/webhooks/{event.id}/replay?dry_run=false",
            headers=mcp_service_headers,
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["result"]["status"] == "replayed"
    assert captured["event_type"] == "report.completed"
    assert captured["data_object"] == {}
    assert isinstance(captured["headers"], dict)
    assert captured["skip_dedup"] is True

def test_webhook_replay_stripe_success(client: TestClient, db, mcp_service_headers):
    service = WebhookLedgerService(db)
    event = service.log_received(
        source="stripe",
        event_type="payment_intent.succeeded",
        payload={"id": "evt_6"},
    )

    stripe_service = _DummyStripeService()
    with _override_webhook_dependencies(stripe_service):
        res = client.post(
            f"/api/v1/admin/mcp/webhooks/{event.id}/replay?dry_run=false",
            headers=mcp_service_headers,
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["result"]["status"] == "replayed"
    assert stripe_service.calls == 1

    replay_id = payload["result"]["replay_event_id"]
    replay = db.query(WebhookEvent).filter(WebhookEvent.id == replay_id).first()
    assert replay is not None
    assert replay.status == "replayed"
    assert replay.processed_at is not None
