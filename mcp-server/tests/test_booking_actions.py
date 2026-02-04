from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import booking_actions


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def booking_force_cancel_preview(self, **params):
        self.calls.append(("force_cancel_preview", params))
        return {"ok": True}

    async def booking_force_cancel_execute(self, **params):
        self.calls.append(("force_cancel_execute", params))
        return {"ok": True}

    async def booking_force_complete_preview(self, **params):
        self.calls.append(("force_complete_preview", params))
        return {"ok": True}

    async def booking_force_complete_execute(self, **params):
        self.calls.append(("force_complete_execute", params))
        return {"ok": True}

    async def booking_resend_notification(self, **params):
        self.calls.append(("resend_notification", params))
        return {"ok": True}

    async def booking_add_note(self, **params):
        self.calls.append(("add_note", params))
        return {"ok": True}


@pytest.mark.asyncio
async def test_force_cancel_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_actions.register_tools(mcp, client)

    result = await tools["instainstru_booking_force_cancel_preview"](
        booking_id="01BOOK",
        reason_code="ADMIN_DISCRETION",
        note="note",
        refund_preference="FULL_CARD",
    )

    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "force_cancel_preview"
    assert params["booking_id"] == "01BOOK"
    assert params["reason_code"] == "ADMIN_DISCRETION"
    assert params["note"] == "note"
    assert params["refund_preference"] == "FULL_CARD"


@pytest.mark.asyncio
async def test_force_cancel_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_actions.register_tools(mcp, client)

    result = await tools["instainstru_booking_force_cancel_execute"](
        booking_id="01BOOK",
        confirm_token="ctok_123",
        idempotency_key="idem_123",
    )

    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "force_cancel_execute"
    assert params["booking_id"] == "01BOOK"
    assert params["confirm_token"] == "ctok_123"
    assert params["idempotency_key"] == "idem_123"


@pytest.mark.asyncio
async def test_force_complete_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_actions.register_tools(mcp, client)

    result = await tools["instainstru_booking_force_complete_preview"](
        booking_id="01BOOK",
        reason_code="ADMIN_VERIFIED",
        note="note",
    )

    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "force_complete_preview"
    assert params["booking_id"] == "01BOOK"
    assert params["reason_code"] == "ADMIN_VERIFIED"
    assert params["note"] == "note"


@pytest.mark.asyncio
async def test_force_complete_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_actions.register_tools(mcp, client)

    result = await tools["instainstru_booking_force_complete_execute"](
        booking_id="01BOOK",
        confirm_token="ctok_123",
        idempotency_key="idem_123",
    )

    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "force_complete_execute"
    assert params["booking_id"] == "01BOOK"
    assert params["confirm_token"] == "ctok_123"
    assert params["idempotency_key"] == "idem_123"


@pytest.mark.asyncio
async def test_resend_notification_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_actions.register_tools(mcp, client)

    result = await tools["instainstru_booking_resend_notification"](
        booking_id="01BOOK",
        notification_type="booking_confirmation",
        recipient="both",
        note="note",
    )

    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "resend_notification"
    assert params["booking_id"] == "01BOOK"
    assert params["notification_type"] == "booking_confirmation"
    assert params["recipient"] == "both"
    assert params["note"] == "note"


@pytest.mark.asyncio
async def test_add_note_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = booking_actions.register_tools(mcp, client)

    result = await tools["instainstru_booking_add_note"](
        booking_id="01BOOK",
        note="note",
        visibility="internal",
        category="general",
    )

    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "add_note"
    assert params["booking_id"] == "01BOOK"
    assert params["note"] == "note"
    assert params["visibility"] == "internal"
    assert params["category"] == "general"
