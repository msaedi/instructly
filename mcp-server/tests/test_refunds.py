from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import refunds


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def refund_preview(self, **params):
        self.calls.append(("preview", params))
        return {"ok": True}

    async def refund_execute(self, **params):
        self.calls.append(("execute", params))
        return {"ok": True}


@pytest.mark.asyncio
async def test_refund_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = refunds.register_tools(mcp, client)

    result = await tools["instainstru_refund_preview"](
        booking_id="01BOOK",
        reason_code="GOODWILL",
        amount_type="partial",
        amount_value=25.0,
        note="testing",
    )

    assert result == {"ok": True}
    assert client.calls[0][0] == "preview"
    assert client.calls[0][1]["booking_id"] == "01BOOK"
    assert client.calls[0][1]["reason_code"] == "GOODWILL"
    assert client.calls[0][1]["amount_type"] == "partial"
    assert client.calls[0][1]["amount_value"] == 25.0
    assert client.calls[0][1]["note"] == "testing"


@pytest.mark.asyncio
async def test_refund_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = refunds.register_tools(mcp, client)

    result = await tools["instainstru_refund_execute"](
        confirm_token="ctok_123",
        idempotency_key="idem_123",
    )

    assert result == {"ok": True}
    assert client.calls[0][0] == "execute"
    assert client.calls[0][1]["confirm_token"] == "ctok_123"
    assert client.calls[0][1]["idempotency_key"] == "idem_123"


@pytest.mark.asyncio
async def test_refund_preview_requires_amount_value_for_partial():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = refunds.register_tools(mcp, client)

    with pytest.raises(ValueError, match="amount_value is required"):
        await tools["instainstru_refund_preview"](
            booking_id="01BOOK",
            reason_code="GOODWILL",
            amount_type="partial",
            amount_value=None,
        )
