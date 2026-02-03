from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import payments


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.lookup_calls: list[str] = []

    async def get_payment_timeline(self, **params):
        self.calls.append(("get_payment_timeline", params))
        return {"ok": True, "meta": {}}

    async def lookup_user(self, identifier: str):
        self.lookup_calls.append(identifier)
        if identifier == "missing@example.com":
            return {"found": False, "user": None}
        return {
            "found": True,
            "user": {"user_id": "01USER", "email": identifier, "name": "Sarah C."},
        }


@pytest.mark.asyncio
async def test_payment_timeline_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = payments.register_tools(mcp, client)

    await tools["instainstru_payment_timeline"](
        booking_id="01BOOK",
        since_days=30,
        start_time="2026-02-01T00:00:00Z",
        end_time="2026-02-02T00:00:00Z",
    )

    assert client.calls[0][0] == "get_payment_timeline"
    assert client.calls[0][1]["booking_id"] == "01BOOK"
    assert client.calls[0][1]["start_time"] == "2026-02-01T00:00:00Z"
    assert client.calls[0][1]["end_time"] == "2026-02-02T00:00:00Z"


@pytest.mark.asyncio
async def test_payment_timeline_validation():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = payments.register_tools(mcp, client)

    with pytest.raises(ValueError):
        await tools["instainstru_payment_timeline"]()

    with pytest.raises(ValueError):
        await tools["instainstru_payment_timeline"](booking_id="01BOOK", user_id="01USER")

    with pytest.raises(ValueError):
        await tools["instainstru_payment_timeline"](booking_id="01BOOK", email="user@example.com")

    with pytest.raises(ValueError):
        await tools["instainstru_payment_timeline"](
            booking_id="01BOOK",
            start_time="2026-02-01T00:00:00Z",
        )


@pytest.mark.asyncio
async def test_payment_timeline_email_resolves_user():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = payments.register_tools(mcp, client)

    response = await tools["instainstru_payment_timeline"](
        email="sarah.chen@example.com",
        since_days=30,
    )

    assert client.lookup_calls == ["sarah.chen@example.com"]
    assert client.calls[0][1]["user_id"] == "01USER"
    assert response["meta"]["resolved_user"]["email_provided"] == "sarah.chen@example.com"


@pytest.mark.asyncio
async def test_payment_timeline_email_not_found_returns_error():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = payments.register_tools(mcp, client)

    response = await tools["instainstru_payment_timeline"](
        email="missing@example.com",
        since_days=30,
    )

    assert response["error"] == "user_not_found"
    assert client.calls == []
