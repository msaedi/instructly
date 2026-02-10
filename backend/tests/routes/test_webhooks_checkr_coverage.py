# backend/tests/routes/test_webhooks_checkr_coverage.py
from __future__ import annotations

import base64
from datetime import timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.core.exceptions import RepositoryException
from app.routes.v1 import webhooks_checkr as checkr_routes


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def _auth_headers(
    raw_body: bytes,
    *,
    user: str = "user",
    password: str = "pass",
    api_key: str = "secret",
    delivery_id: str = "delivery-1",
):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    signature = checkr_routes._compute_signature(api_key, raw_body)
    return {
        "Authorization": f"Basic {token}",
        "X-Checkr-Signature": signature,
        "X-Checkr-Delivery-Id": delivery_id,
    }


def test_result_label_variants():
    assert checkr_routes._result_label("clear") == "clear"
    assert checkr_routes._result_label("needs_review") == "consider"
    assert checkr_routes._result_label("canceled") == "canceled"
    assert checkr_routes._result_label("unknown") == "other"


def test_parse_timestamp_variants():
    assert checkr_routes._parse_timestamp(123) is None
    assert checkr_routes._parse_timestamp(" ") is None
    assert checkr_routes._parse_timestamp("not-a-date") is None

    parsed = checkr_routes._parse_timestamp("2024-01-01T10:00:00Z")
    assert parsed is not None
    assert parsed.tzinfo is not None

    parsed = checkr_routes._parse_timestamp("2024-01-01T10:00:00")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_basic_auth_requires_credentials(monkeypatch):
    request = checkr_routes.Request({"type": "http", "headers": [], "path": "/"})
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_user", None)
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_pass", None)
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._require_basic_auth(request)
    assert exc.value.status_code == 500


def test_basic_auth_rejects_invalid(monkeypatch):
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_user", _Secret("user"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_pass", _Secret("pass"))
    request = checkr_routes.Request(
        {"type": "http", "headers": [(b"authorization", b"Basic invalid")], "path": "/"}
    )
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._require_basic_auth(request)
    assert exc.value.status_code == 401


def test_basic_auth_missing_header(monkeypatch):
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_user", _Secret("user"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_pass", _Secret("pass"))
    request = checkr_routes.Request({"type": "http", "headers": [], "path": "/"})
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._require_basic_auth(request)
    assert exc.value.status_code == 401


def test_basic_auth_rejects_mismatch(monkeypatch):
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_user", _Secret("user"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_pass", _Secret("pass"))
    token = base64.b64encode(b"user:wrong").decode()
    request = checkr_routes.Request(
        {"type": "http", "headers": [(b"authorization", f"Basic {token}".encode())], "path": "/"}
    )
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._require_basic_auth(request)
    assert exc.value.status_code == 403


def test_verify_signature_rejects_missing(monkeypatch):
    request = checkr_routes.Request({"type": "http", "headers": [], "path": "/"})
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._verify_checkr_signature(request, b"{}")
    assert exc.value.status_code == 401


def test_verify_signature_rejects_placeholder(monkeypatch):
    request = checkr_routes.Request(
        {"type": "http", "headers": [(b"x-checkr-signature", checkr_routes._SIGNATURE_PLACEHOLDER.encode())], "path": "/"}
    )
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._verify_checkr_signature(request, b"{}")
    assert exc.value.status_code == 401


def test_verify_signature_requires_api_key(monkeypatch):
    monkeypatch.setattr(checkr_routes.settings, "checkr_api_key", _Secret(""))
    request = checkr_routes.Request(
        {"type": "http", "headers": [(b"x-checkr-signature", b"abc")], "path": "/"}
    )
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._verify_checkr_signature(request, b"{}")
    assert exc.value.status_code == 500


def test_verify_signature_empty_value(monkeypatch):
    monkeypatch.setattr(checkr_routes.settings, "checkr_api_key", _Secret("secret"))
    request = checkr_routes.Request(
        {"type": "http", "headers": [(b"x-checkr-signature", b"sha256=")], "path": "/"}
    )
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._verify_checkr_signature(request, b"{}")
    assert exc.value.status_code == 401


def test_verify_signature_rejects_mismatch(monkeypatch):
    monkeypatch.setattr(checkr_routes.settings, "checkr_api_key", _Secret("secret"))
    request = checkr_routes.Request(
        {"type": "http", "headers": [(b"x-checkr-signature", b"sha256=bad")], "path": "/"}
    )
    with pytest.raises(checkr_routes.HTTPException) as exc:
        checkr_routes._verify_checkr_signature(request, b"{}")
    assert exc.value.status_code == 401


def test_delivery_cache_tracking():
    checkr_routes._delivery_cache.clear()
    assert checkr_routes._delivery_seen(None) is False
    checkr_routes._mark_delivery("delivery-1")
    assert checkr_routes._delivery_seen("delivery-1") is True


def test_delivery_cache_expiration_and_eviction(monkeypatch):
    checkr_routes._delivery_cache.clear()
    checkr_routes._delivery_cache["old"] = 0.0
    monkeypatch.setattr(checkr_routes, "_WEBHOOK_CACHE_TTL_SECONDS", 0)
    assert checkr_routes._delivery_seen("old") is False

    checkr_routes._delivery_cache.clear()
    monkeypatch.setattr(checkr_routes, "_WEBHOOK_CACHE_MAX_SIZE", 1)
    checkr_routes._mark_delivery("first")
    checkr_routes._mark_delivery("second")
    assert "first" not in checkr_routes._delivery_cache


def test_mark_delivery_ignores_empty_key():
    checkr_routes._delivery_cache.clear()
    checkr_routes._mark_delivery(None)
    assert checkr_routes._delivery_cache == {}


def test_resolve_resource_id_variants():
    assert checkr_routes._resolve_resource_id("report.completed", {"report_id": "rep_1"}) == "rep_1"
    assert checkr_routes._resolve_resource_id("invitation.created", {"invitation_id": "inv_1"}) == "inv_1"
    assert checkr_routes._resolve_resource_id("other", {"id": "obj_1"}) == "obj_1"
    assert checkr_routes._resolve_resource_id("report.updated", {}) is None


def test_extract_helpers():
    assert checkr_routes._extract_reason({"reason": " delayed "}) == "delayed"
    assert checkr_routes._extract_reason({"status": " "}) is None
    assert checkr_routes._extract_candidate_id({"candidate_id": "cand_2"}) == "cand_2"
    assert checkr_routes._extract_candidate_id({"candidate": {"id": "cand_1"}}) == "cand_1"
    assert checkr_routes._extract_invitation_id({"invitation": {"id": "inv_1"}}) == "inv_1"
    assert checkr_routes._extract_invitation_id({"invitation_id": "inv_2"}) == "inv_2"
    assert checkr_routes._format_note("report.suspended", None) == "report.suspended"


def test_bind_report_to_profile():
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return "profile-1"

    result = checkr_routes._bind_report_to_profile(
        _Repo(), report_id="rep_1", candidate_id="cand_1", invitation_id="inv_1", env="sandbox"
    )
    assert result == "profile-1"


def test_bind_report_to_profile_requires_report_id():
    repo = SimpleNamespace(
        bind_report_to_candidate=AsyncMock(),
        bind_report_to_invitation=AsyncMock(),
    )
    result = checkr_routes._bind_report_to_profile(
        repo,
        report_id=None,
        candidate_id="cand_1",
        invitation_id="inv_1",
        env="sandbox",
    )
    assert result is None


def test_update_report_status_skips_without_report_id():
    class _Repo:
        def update_bgc_by_report_id(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

    checkr_routes._update_report_status(_Repo(), None, status="pending", note=None)


def test_record_webhook_event_handles_repo_error():
    class _Repo:
        def record(self, **_kwargs):
            raise RepositoryException("db down")

    checkr_routes._record_webhook_event(
        _Repo(),
        event_type="report.created",
        resource_id="rep_1",
        payload={},
        delivery_id="delivery-1",
        signature="sig",
        http_status=200,
    )


def _client_with_overrides(monkeypatch, workflow_service):
    app = FastAPI()
    app.include_router(checkr_routes.router, prefix="/api/v1/webhooks/checkr")
    checkr_routes._delivery_cache.clear()

    class _JobRepo:
        def __init__(self):
            self.calls = []

        def enqueue(self, **payload):
            self.calls.append(payload)

    class _LogRepo:
        def record(self, **_kwargs):
            return None

    job_repo = _JobRepo()
    log_repo = _LogRepo()

    app.dependency_overrides[checkr_routes.get_background_check_workflow_service] = lambda: workflow_service
    app.dependency_overrides[checkr_routes.get_background_job_repo] = lambda: job_repo
    app.dependency_overrides[checkr_routes.get_bgc_webhook_log_repo] = lambda: log_repo

    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_user", _Secret("user"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_pass", _Secret("pass"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_api_key", _Secret("secret"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_env", "sandbox")

    return TestClient(app), job_repo


def test_handle_webhook_invitation_event(monkeypatch):
    class _Repo:
        def update_bgc_by_invitation(self, *_args, **_kwargs):
            return {"id": "profile-1"}

        def update_bgc_by_candidate(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {"type": "invitation.created", "data": {"object": {"id": "inv_1"}}}
    body = json.dumps(payload).encode()
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body))
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_handle_webhook_invitation_event_candidate_path(monkeypatch):
    class _Repo:
        def __init__(self):
            self.candidate_calls = 0

        def update_bgc_by_invitation(self, *_args, **_kwargs):
            return None

        def update_bgc_by_candidate(self, *_args, **_kwargs):
            self.candidate_calls += 1
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {"type": "invitation.completed", "data": {"object": {"candidate_id": "cand_1"}}}
    body = json.dumps(payload).encode()
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-11"))
    assert response.status_code == 200


def test_handle_webhook_report_updated_queues_on_repo_error(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_eta_updated(self, *_args, **_kwargs):
            raise RepositoryException("db timeout")

    client, job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.updated",
        "data": {
            "object": {
                "id": "rep_1",
                "estimated_completion_time": "2024-01-01T10:00:00Z",
                "candidate_id": "cand_1",
            }
        },
    }
    body = json.dumps(payload).encode()
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body))
    assert response.status_code == 200
    assert any(call["type"] == "webhook.report_eta" for call in job_repo.calls)


def test_handle_webhook_report_updated_success(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_eta_updated(self, *_args, **_kwargs):
            return None

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.updated",
        "data": {
            "object": {
                "id": "rep_2",
                "estimated_completion_time": "2024-01-01T11:00:00Z",
                "candidate_id": "cand_2",
            },
            "previous_attributes": {"estimated_completion_time": "2024-01-01T10:00:00Z"},
        },
    }
    body = json.dumps(payload).encode()
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-12"))
    assert response.status_code == 200


def test_handle_webhook_report_updated_short_circuits(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_eta_updated(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.updated",
        "data": {
            "object": {"id": "rep_3", "estimated_completion_time": "2024-01-01T11:00:00Z"},
            "previous_attributes": {"estimated_completion_time": "2024-01-01T11:00:00Z"},
        },
    }
    body = json.dumps(payload).encode()
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-13"))
    assert response.status_code == 200


def test_handle_webhook_report_completed_success(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_completed(self, *_args, **_kwargs):
            return "clear", SimpleNamespace(id="profile-1"), False

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rep_1", "result": "clear", "package": "pkg"}},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-3")
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_handle_webhook_report_completed_follow_up(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_completed(self, *_args, **_kwargs):
            return "consider", SimpleNamespace(id="profile-1"), True

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rep_2", "result": "consider", "package": "pkg"}},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-4")
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_handle_webhook_report_completed_queues_on_repo_error(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_completed(self, *_args, **_kwargs):
            raise RepositoryException("db down")

    client, job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.completed",
        "data": {"object": {"id": "rep_3", "result": "clear", "package": "pkg"}},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-5")
    )
    assert response.status_code == 200
    assert any(call["type"] == "webhook.report_completed" for call in job_repo.calls)


def test_handle_webhook_report_canceled_success_and_queue(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()
            self.calls = 0

        def handle_report_canceled(self, *_args, **_kwargs):
            self.calls += 1
            return None

    client, job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.canceled",
        "data": {"object": {"id": "rep_c", "canceled_at": "2024-01-01T10:00:00Z"}},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-6")
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    class _WorkflowQueued:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_canceled(self, *_args, **_kwargs):
            raise RepositoryException("db down")

    client, job_repo = _client_with_overrides(monkeypatch, _WorkflowQueued())
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-7")
    )
    assert response.status_code == 200
    assert any(call["type"] == "webhook.report_canceled" for call in job_repo.calls)


def test_handle_webhook_report_suspended_paths(monkeypatch):
    class _Repo:
        pass

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_suspended(self, *_args, **_kwargs):
            return None

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.suspended",
        "data": {"object": {"id": "rep_s", "reason": "review"}},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-8")
    )
    assert response.status_code == 200

    class _WorkflowRepoError:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_suspended(self, *_args, **_kwargs):
            raise RepositoryException("db down")

    client, _job_repo = _client_with_overrides(monkeypatch, _WorkflowRepoError())
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-9")
    )
    assert response.status_code == 200


def test_handle_webhook_report_status_updates(monkeypatch):
    class _Repo:
        def __init__(self):
            self.calls = []

        def update_bgc_by_report_id(self, *_args, **_kwargs):
            self.calls.append(("update", _args, _kwargs))

        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {
        "type": "report.created",
        "data": {"object": {"id": "rep_created", "reason": "pending"}},
    }
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-10")
    )
    assert response.status_code == 200


def test_handle_webhook_invalid_json(monkeypatch):
    class _Workflow:
        def __init__(self):
            self.repo = object()

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    body = b"{bad json"
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body))
    assert response.status_code == 400


def test_handle_webhook_empty_type_and_duplicate(monkeypatch):
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

        def update_bgc_by_report_id(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {"type": "", "data": {"object": []}}
    body = json.dumps(payload).encode()
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-14"))
    assert response.status_code == 200

    payload = {"type": "report.created", "data": {"object": {"id": "rep_dup"}}}
    body = json.dumps(payload).encode()
    headers = _auth_headers(body, delivery_id="delivery-15")
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=headers)
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    [
        "report.updated",
        "report.completed",
        "report.canceled",
        "report.suspended",
        "report.created",
    ],
)
async def test_process_payload_missing_report_id_early_return(event_type):
    class _Repo:
        def update_bgc_by_report_id(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_eta_updated(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

        def handle_report_completed(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

        def handle_report_canceled(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

        def handle_report_suspended(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

    workflow = _Workflow()
    job_repo = SimpleNamespace(enqueue=lambda **_kwargs: None)
    log_repo = SimpleNamespace(record=lambda **_kwargs: None)
    payload = {"type": event_type, "data": {"object": {}}}

    error, outcome = await checkr_routes._process_checkr_payload(
        event_type=event_type,
        data_object={},
        payload=payload,
        headers={},
        workflow_service=workflow,
        job_repository=job_repo,
        log_repository=log_repo,
        resource_id=None,
        skip_dedup=True,
    )

    assert error is None
    assert outcome == "processed"


@pytest.mark.asyncio
async def test_process_payload_report_updated_no_eta_short_circuit():
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_eta_updated(self, *_args, **_kwargs):
            raise AssertionError("should not be called")

    workflow = _Workflow()
    payload = {"type": "report.updated", "data": {"object": {"id": "rep_nop"}}}
    error, outcome = await checkr_routes._process_checkr_payload(
        event_type="report.updated",
        data_object={"id": "rep_nop"},
        payload=payload,
        headers={},
        workflow_service=workflow,
        job_repository=SimpleNamespace(enqueue=lambda **_kwargs: None),
        log_repository=SimpleNamespace(record=lambda **_kwargs: None),
        resource_id="rep_nop",
        skip_dedup=True,
    )
    assert error is None
    assert outcome == "processed"


@pytest.mark.asyncio
async def test_process_payload_unsupported_event_branch():
    class _Workflow:
        def __init__(self):
            self.repo = SimpleNamespace()

    error, outcome = await checkr_routes._process_checkr_payload(
        event_type="candidate.created",
        data_object={"id": "cand_1"},
        payload={"type": "candidate.created", "data": {"object": {"id": "cand_1"}}},
        headers={},
        workflow_service=_Workflow(),
        job_repository=SimpleNamespace(enqueue=lambda **_kwargs: None),
        log_repository=SimpleNamespace(record=lambda **_kwargs: None),
        resource_id="cand_1",
        skip_dedup=True,
    )
    assert error is None
    assert outcome == "processed"


def test_handle_webhook_non_dict_object_payload(monkeypatch):
    class _Workflow:
        def __init__(self):
            self.repo = SimpleNamespace()

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {"type": "report.created", "data": {"object": []}}
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr",
        content=body,
        headers=_auth_headers(body, delivery_id="delivery-nondict"),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_handle_webhook_returns_early_for_processed_ledger_event(monkeypatch):
    app = FastAPI()
    app.include_router(checkr_routes.router, prefix="/api/v1/webhooks/checkr")

    class _Workflow:
        def __init__(self):
            self.repo = SimpleNamespace(db=object())

    class _JobRepo:
        db = object()

        def enqueue(self, **_kwargs):
            return None

    class _LogRepo:
        db = object()

        def record(self, **_kwargs):
            return None

    app.dependency_overrides[checkr_routes.get_background_check_workflow_service] = lambda: _Workflow()
    app.dependency_overrides[checkr_routes.get_background_job_repo] = lambda: _JobRepo()
    app.dependency_overrides[checkr_routes.get_bgc_webhook_log_repo] = lambda: _LogRepo()

    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_user", _Secret("user"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_pass", _Secret("pass"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_api_key", _Secret("secret"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_env", "sandbox")

    class _Ledger:
        def __init__(self, _db):
            pass

        def log_received(self, **_kwargs):
            return SimpleNamespace(id="evt_1", retry_count=1, status="processed")

    monkeypatch.setattr(checkr_routes, "WebhookLedgerService", _Ledger)
    monkeypatch.setattr(
        checkr_routes,
        "_process_checkr_payload",
        AsyncMock(side_effect=AssertionError("should not process payload when already processed")),
    )

    client = TestClient(app)
    payload = {"id": "evt_1", "type": "report.created", "data": {"object": {"id": "rep_early"}}}
    body = json.dumps(payload).encode()
    response = client.post("/api/v1/webhooks/checkr", content=body, headers=_auth_headers(body, delivery_id="delivery-ledger"))
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_handle_webhook_truthy_non_dict_object_payload(monkeypatch):
    class _Workflow:
        def __init__(self):
            self.repo = SimpleNamespace()

    client, _job_repo = _client_with_overrides(monkeypatch, _Workflow())
    payload = {"type": "report.created", "data": {"object": "non-dict"}}
    body = json.dumps(payload).encode()
    response = client.post(
        "/api/v1/webhooks/checkr",
        content=body,
        headers=_auth_headers(body, delivery_id="delivery-nondict-truthy"),
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_handle_webhook_marks_ledger_failed_on_processing_error(monkeypatch):
    request = checkr_routes.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/webhooks/checkr",
            "headers": [
                (b"authorization", f"Basic {base64.b64encode(b'user:pass').decode()}".encode()),
                (b"x-checkr-signature", b"sig"),
                (b"x-checkr-delivery-id", b"delivery-ledger-fail"),
            ],
        }
    )
    request._body = b'{"id":"evt-fail","type":"report.created","data":{"object":{"id":"rep_1"}}}'

    class _Workflow:
        def __init__(self):
            self.repo = SimpleNamespace(db=object())

    class _Repo:
        db = object()

    class _Ledger:
        def __init__(self, _db):
            self.mark_failed_calls = []

        def log_received(self, **_kwargs):
            return SimpleNamespace(id="evt-fail", retry_count=0, status="received")

        def mark_failed(self, event, **kwargs):
            self.mark_failed_calls.append((event, kwargs))

        def mark_processed(self, *_args, **_kwargs):
            raise AssertionError("should not mark processed")

    ledger = _Ledger(object())

    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_user", _Secret("user"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_webhook_pass", _Secret("pass"))
    monkeypatch.setattr(checkr_routes.settings, "checkr_api_key", _Secret("secret"))
    monkeypatch.setattr(
        checkr_routes,
        "_verify_checkr_signature",
        lambda _request, _body: None,
    )
    monkeypatch.setattr(checkr_routes, "WebhookLedgerService", lambda _db: ledger)
    monkeypatch.setattr(
        checkr_routes,
        "_process_checkr_payload",
        AsyncMock(return_value=("db down", "failed")),
    )

    response = await checkr_routes.handle_checkr_webhook(
        request,
        workflow_service=_Workflow(),
        job_repository=_Repo(),
        log_repository=_Repo(),
    )

    assert response.ok is True
    assert ledger.mark_failed_calls
    assert ledger.mark_failed_calls[0][1]["error"] == "db down"


@pytest.mark.asyncio
async def test_process_payload_invitation_repo_exception_sets_failed():
    class _Repo:
        def update_bgc_by_invitation(self, *_args, **_kwargs):
            raise RepositoryException("invite update failed")

        def update_bgc_by_candidate(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

    error, outcome = await checkr_routes._process_checkr_payload(
        event_type="invitation.created",
        data_object={"id": "inv_1"},
        payload={"type": "invitation.created", "data": {"object": {"id": "inv_1"}}},
        headers={},
        workflow_service=_Workflow(),
        job_repository=SimpleNamespace(enqueue=lambda **_kwargs: None),
        log_repository=SimpleNamespace(record=lambda **_kwargs: None),
        resource_id="inv_1",
        skip_dedup=True,
    )
    assert outcome == "failed"
    assert "invite update failed" in (error or "")


@pytest.mark.asyncio
async def test_process_payload_report_suspended_non_retryable_branch():
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

        def handle_report_suspended(self, *_args, **_kwargs):
            raise checkr_routes.NonRetryableError("profile not linked")

    error, outcome = await checkr_routes._process_checkr_payload(
        event_type="report.suspended",
        data_object={"id": "rep_suspend"},
        payload={"type": "report.suspended", "data": {"object": {"id": "rep_suspend"}}},
        headers={},
        workflow_service=_Workflow(),
        job_repository=SimpleNamespace(enqueue=lambda **_kwargs: None),
        log_repository=SimpleNamespace(record=lambda **_kwargs: None),
        resource_id="rep_suspend",
        skip_dedup=True,
    )
    assert outcome == "unmatched"
    assert "profile not linked" in (error or "")


@pytest.mark.asyncio
async def test_process_payload_report_status_repo_exception_sets_failed():
    class _Repo:
        def bind_report_to_candidate(self, *_args, **_kwargs):
            return None

        def bind_report_to_invitation(self, *_args, **_kwargs):
            return None

        def update_bgc_by_report_id(self, *_args, **_kwargs):
            raise RepositoryException("status write failed")

    class _Workflow:
        def __init__(self):
            self.repo = _Repo()

    error, outcome = await checkr_routes._process_checkr_payload(
        event_type="report.created",
        data_object={"id": "rep_status"},
        payload={"type": "report.created", "data": {"object": {"id": "rep_status"}}},
        headers={},
        workflow_service=_Workflow(),
        job_repository=SimpleNamespace(enqueue=lambda **_kwargs: None),
        log_repository=SimpleNamespace(record=lambda **_kwargs: None),
        resource_id="rep_status",
        skip_dedup=True,
    )
    assert outcome == "failed"
    assert "status write failed" in (error or "")
