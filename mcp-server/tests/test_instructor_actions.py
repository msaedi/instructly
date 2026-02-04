from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import instructor_actions


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def instructor_suspend_preview(self, **params):
        self.calls.append(("suspend_preview", params))
        return {"ok": True}

    async def instructor_suspend_execute(self, **params):
        self.calls.append(("suspend_execute", params))
        return {"ok": True}

    async def instructor_unsuspend(self, **params):
        self.calls.append(("unsuspend", params))
        return {"ok": True}

    async def instructor_verify_override(self, **params):
        self.calls.append(("verify_override", params))
        return {"ok": True}

    async def instructor_update_commission_preview(self, **params):
        self.calls.append(("commission_preview", params))
        return {"ok": True}

    async def instructor_update_commission_execute(self, **params):
        self.calls.append(("commission_execute", params))
        return {"ok": True}

    async def instructor_payout_hold(self, **params):
        self.calls.append(("payout_hold", params))
        return {"ok": True}


@pytest.mark.asyncio
async def test_instructor_suspend_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructor_actions.register_tools(mcp, client)

    result = await tools["instainstru_instructor_suspend_preview"](
        instructor_id="01INS",
        reason_code="FRAUD",
        note="note",
        notify_instructor=False,
        cancel_pending_bookings=False,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "suspend_preview"
    assert params["instructor_id"] == "01INS"
    assert params["reason_code"] == "FRAUD"
    assert params["notify_instructor"] is False


@pytest.mark.asyncio
async def test_instructor_suspend_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructor_actions.register_tools(mcp, client)

    result = await tools["instainstru_instructor_suspend_execute"](
        instructor_id="01INS",
        confirm_token="ctok_123",
        idempotency_key="idem_123",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "suspend_execute"
    assert params["confirm_token"] == "ctok_123"


@pytest.mark.asyncio
async def test_instructor_unsuspend_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructor_actions.register_tools(mcp, client)

    result = await tools["instainstru_instructor_unsuspend"](
        instructor_id="01INS",
        reason="cleared",
        restore_visibility=True,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "unsuspend"
    assert params["restore_visibility"] is True


@pytest.mark.asyncio
async def test_instructor_verify_override_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructor_actions.register_tools(mcp, client)

    result = await tools["instainstru_instructor_verify_override"](
        instructor_id="01INS",
        verification_type="IDENTITY",
        reason="manual",
        evidence="link",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "verify_override"
    assert params["verification_type"] == "IDENTITY"


@pytest.mark.asyncio
async def test_instructor_commission_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructor_actions.register_tools(mcp, client)

    result = await tools["instainstru_instructor_update_commission_preview"](
        instructor_id="01INS",
        action="SET_TIER",
        reason="update",
        tier="entry",
        temporary_rate=None,
        temporary_until=None,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "commission_preview"
    assert params["action"] == "SET_TIER"


@pytest.mark.asyncio
async def test_instructor_commission_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructor_actions.register_tools(mcp, client)

    result = await tools["instainstru_instructor_update_commission_execute"](
        instructor_id="01INS",
        confirm_token="ctok_123",
        idempotency_key="idem_123",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "commission_execute"
    assert params["idempotency_key"] == "idem_123"


@pytest.mark.asyncio
async def test_instructor_payout_hold_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructor_actions.register_tools(mcp, client)

    result = await tools["instainstru_instructor_payout_hold"](
        instructor_id="01INS",
        action="HOLD",
        reason="hold",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "payout_hold"
    assert params["action"] == "HOLD"
