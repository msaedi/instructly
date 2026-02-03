from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import webhooks


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def get_webhooks(self, **params):
        self.calls.append(("get_webhooks", params))
        return {"ok": True}

    async def get_failed_webhooks(self, **params):
        self.calls.append(("get_failed_webhooks", params))
        return {"ok": True}

    async def get_webhook_detail(self, event_id: str):
        self.calls.append(("get_webhook_detail", {"event_id": event_id}))
        return {"ok": True}

    async def replay_webhook(self, event_id: str, dry_run: bool = True):
        self.calls.append(("replay_webhook", {"event_id": event_id, "dry_run": dry_run}))
        return {"ok": True}


@pytest.mark.asyncio
async def test_webhooks_list_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = webhooks.register_tools(mcp, client)

    await tools["instainstru_webhooks_list"](
        source="stripe",
        status="failed",
        event_type="payment_intent.failed",
        since_hours=12,
        limit=5,
    )

    assert client.calls[0][0] == "get_webhooks"
    assert client.calls[0][1]["source"] == "stripe"


@pytest.mark.asyncio
async def test_webhooks_failed_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = webhooks.register_tools(mcp, client)

    await tools["instainstru_webhooks_failed"](source="checkr", since_hours=48, limit=10)

    assert client.calls[0][0] == "get_failed_webhooks"
    assert client.calls[0][1]["source"] == "checkr"


@pytest.mark.asyncio
async def test_webhook_detail_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = webhooks.register_tools(mcp, client)

    await tools["instainstru_webhook_detail"]("evt_123")

    assert client.calls[0] == ("get_webhook_detail", {"event_id": "evt_123"})


@pytest.mark.asyncio
async def test_webhook_replay_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = webhooks.register_tools(mcp, client)

    await tools["instainstru_webhook_replay"]("evt_456", dry_run=False)

    assert client.calls[0] == (
        "replay_webhook",
        {"event_id": "evt_456", "dry_run": False},
    )
