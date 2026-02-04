from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import communications


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def announcement_preview(self, **params):
        self.calls.append(("announcement_preview", params))
        return {"ok": True}

    async def announcement_execute(self, **params):
        self.calls.append(("announcement_execute", params))
        return {"ok": True}

    async def bulk_notification_preview(self, **params):
        self.calls.append(("bulk_preview", params))
        return {"ok": True}

    async def bulk_notification_execute(self, **params):
        self.calls.append(("bulk_execute", params))
        return {"ok": True}

    async def notification_history(self, **params):
        self.calls.append(("history", params))
        return {"ok": True}

    async def notification_templates(self, **params):
        self.calls.append(("templates", params))
        return {"ok": True}

    async def email_preview(self, **params):
        self.calls.append(("email_preview", params))
        return {"ok": True}


@pytest.mark.asyncio
async def test_announcement_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = communications.register_tools(mcp, client)

    result = await tools["instainstru_announcement_preview"](
        audience="all_users",
        channels=["email"],
        title="Title",
        body="Body",
        subject="Subject",
        schedule_at=None,
        high_priority=True,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "announcement_preview"
    assert params["audience"] == "all_users"
    assert params["high_priority"] is True


@pytest.mark.asyncio
async def test_announcement_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = communications.register_tools(mcp, client)

    result = await tools["instainstru_announcement_execute"](
        confirm_token="ctok",
        idempotency_key="idem",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "announcement_execute"
    assert params["confirm_token"] == "ctok"


@pytest.mark.asyncio
async def test_bulk_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = communications.register_tools(mcp, client)

    result = await tools["instainstru_bulk_notification_preview"](
        target={"user_type": "student"},
        channels=["in_app"],
        title="Title",
        body="Body",
        subject=None,
        variables={"foo": "bar"},
        schedule_at="2026-01-01T00:00:00Z",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "bulk_preview"
    assert params["target"]["user_type"] == "student"


@pytest.mark.asyncio
async def test_bulk_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = communications.register_tools(mcp, client)

    result = await tools["instainstru_bulk_notification_execute"](
        confirm_token="ctok",
        idempotency_key="idem",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "bulk_execute"
    assert params["idempotency_key"] == "idem"


@pytest.mark.asyncio
async def test_notification_history_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = communications.register_tools(mcp, client)

    result = await tools["instainstru_notification_history"](
        kind="announcement",
        channel="email",
        status="sent",
        start_date="2026-01-01T00:00:00Z",
        end_date="2026-01-31T00:00:00Z",
        creator_id="admin",
        limit=50,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "history"
    assert params["kind"] == "announcement"
    assert params["limit"] == 50


@pytest.mark.asyncio
async def test_notification_templates_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = communications.register_tools(mcp, client)

    result = await tools["instainstru_notification_templates"]()
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "templates"
    assert params == {}


@pytest.mark.asyncio
async def test_email_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = communications.register_tools(mcp, client)

    result = await tools["instainstru_email_preview"](
        template="email/auth/password_reset.html",
        variables={"reset_url": "https://example.com"},
        subject="Preview",
        test_send_to="test@example.com",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "email_preview"
    assert params["template"] == "email/auth/password_reset.html"
