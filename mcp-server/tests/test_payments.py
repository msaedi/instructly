from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import payments


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def get_payment_timeline(self, **params):
        self.calls.append(("get_payment_timeline", params))
        return {"ok": True}


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
        await tools["instainstru_payment_timeline"](
            booking_id="01BOOK",
            start_time="2026-02-01T00:00:00Z",
        )
