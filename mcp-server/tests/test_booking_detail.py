from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.client import BackendNotFoundError
from instainstru_mcp.tools import booking_detail


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def get_booking_detail(self, **params):
        self.calls.append(params)
        return {"ok": True}


@pytest.mark.asyncio
async def test_booking_detail_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_detail.register_tools(mcp, client)

    result = await tools["instainstru_booking_detail"](
        booking_id="01BOOK",
        include_messages_summary=True,
        include_webhooks=False,
        include_trace_links=True,
    )

    assert result == {"ok": True}
    assert client.calls[0]["booking_id"] == "01BOOK"
    assert client.calls[0]["include_messages_summary"] is True
    assert client.calls[0]["include_webhooks"] is False
    assert client.calls[0]["include_trace_links"] is True


@pytest.mark.asyncio
async def test_booking_detail_defaults():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_detail.register_tools(mcp, client)

    await tools["instainstru_booking_detail"](booking_id="01BOOK")

    assert client.calls[0]["include_messages_summary"] is False
    assert client.calls[0]["include_webhooks"] is True
    assert client.calls[0]["include_trace_links"] is False


@pytest.mark.asyncio
async def test_booking_detail_not_found_returns_structured_response():
    class NotFoundClient(FakeClient):
        async def get_booking_detail(self, **params):
            raise BackendNotFoundError("backend_not_found")

    client = NotFoundClient()
    mcp = FastMCP("test")
    tools = booking_detail.register_tools(mcp, client)

    result = await tools["instainstru_booking_detail"](booking_id="01BOOK404")

    assert result == {
        "found": False,
        "error": "booking_not_found",
        "message": "Booking not found.",
        "booking": None,
    }
