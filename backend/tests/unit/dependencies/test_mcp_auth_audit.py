from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.dependencies import mcp_auth
from app.principal import ServicePrincipal, UserPrincipal


class DummyUrl:
    def __init__(self, path: str):
        self.path = path


class DummyRequest:
    def __init__(self, path: str, method: str = "GET"):
        self.url = DummyUrl(path)
        self.method = method
        self.headers = {}
        self.client = SimpleNamespace(host="203.0.113.5")


def test_mcp_action_from_path() -> None:
    assert mcp_auth._mcp_action_from_path("/api/v1/admin/mcp") == "mcp.root"
    assert (
        mcp_auth._mcp_action_from_path("/api/v1/admin/mcp/audit/search")
        == "mcp.audit.search"
    )
    assert mcp_auth._mcp_action_from_path("/api/v1/other") == "mcp.unknown"


def test_mcp_resource_id_detection() -> None:
    assert (
        mcp_auth._mcp_resource_id("/api/v1/admin/mcp/instructors/01HXY1234567890ABCDEFGHJKL")
        == "01HXY1234567890ABCDEFGHJKL"
    )
    assert mcp_auth._mcp_resource_id("/api/v1/admin/mcp/ops/users/123456") == "123456"
    assert mcp_auth._mcp_resource_id("/api/v1/admin/mcp/audit/search") is None
    assert mcp_auth._mcp_resource_id("/api/v1/admin/mcp") is None


@pytest.mark.asyncio
async def test_audit_mcp_request_logs_success(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_log(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        calls.append(kwargs)

    @contextmanager
    def fake_session():
        yield SimpleNamespace()

    monkeypatch.setattr(mcp_auth.AuditService, "log", fake_log)
    monkeypatch.setattr(mcp_auth, "get_db_session", fake_session)

    request = DummyRequest("/api/v1/admin/mcp/audit/search", method="GET")
    principal = UserPrincipal(user_id="user-123", email="admin@example.com")

    gen = mcp_auth.audit_mcp_request(request, principal)
    await gen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()

    assert calls
    payload = calls[0]
    assert payload["action"] == "mcp.audit.search"
    assert payload["resource_type"] == "mcp"
    assert payload["actor_type"] == "mcp"
    assert payload["actor_id"] == "user-123"
    assert payload["actor_email"] == "admin@example.com"
    assert payload["status"] == "success"
    assert payload["metadata"]["method"] == "GET"


@pytest.mark.asyncio
async def test_audit_mcp_request_logs_failure(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_log(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        calls.append(kwargs)

    @contextmanager
    def fake_session():
        yield SimpleNamespace()

    monkeypatch.setattr(mcp_auth.AuditService, "log", fake_log)
    monkeypatch.setattr(mcp_auth, "get_db_session", fake_session)

    request = DummyRequest("/api/v1/admin/mcp/ops/users/123456", method="POST")
    principal = ServicePrincipal(client_id="svc-1", org_id="org", scopes=("mcp:read",))

    gen = mcp_auth.audit_mcp_request(request, principal)
    await gen.__anext__()
    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("boom"))

    assert calls
    payload = calls[0]
    assert payload["status"] == "failed"
    assert payload["error_message"] == "boom"
    assert payload["actor_email"] is None
