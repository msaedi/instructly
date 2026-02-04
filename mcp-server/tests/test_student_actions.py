from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import student_actions


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def student_suspend_preview(self, **params):
        self.calls.append(("suspend_preview", params))
        return {"ok": True}

    async def student_suspend_execute(self, **params):
        self.calls.append(("suspend_execute", params))
        return {"ok": True}

    async def student_unsuspend(self, **params):
        self.calls.append(("unsuspend", params))
        return {"ok": True}

    async def student_credit_adjust_preview(self, **params):
        self.calls.append(("credit_adjust_preview", params))
        return {"ok": True}

    async def student_credit_adjust_execute(self, **params):
        self.calls.append(("credit_adjust_execute", params))
        return {"ok": True}

    async def student_credit_history(self, **params):
        self.calls.append(("credit_history", params))
        return {"ok": True}

    async def student_refund_history(self, **params):
        self.calls.append(("refund_history", params))
        return {"ok": True}


@pytest.mark.asyncio
async def test_student_suspend_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = student_actions.register_tools(mcp, client)

    result = await tools["instainstru_student_suspend_preview"](
        student_id="01STU",
        reason_code="FRAUD",
        note="note",
        notify_student=False,
        cancel_pending_bookings=False,
        forfeit_credits=True,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "suspend_preview"
    assert params["student_id"] == "01STU"
    assert params["forfeit_credits"] is True


@pytest.mark.asyncio
async def test_student_suspend_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = student_actions.register_tools(mcp, client)

    result = await tools["instainstru_student_suspend_execute"](
        student_id="01STU",
        confirm_token="ctok_123",
        idempotency_key="idem_123",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "suspend_execute"
    assert params["confirm_token"] == "ctok_123"


@pytest.mark.asyncio
async def test_student_unsuspend_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = student_actions.register_tools(mcp, client)

    result = await tools["instainstru_student_unsuspend"](
        student_id="01STU",
        reason="cleared",
        restore_credits=True,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "unsuspend"
    assert params["restore_credits"] is True


@pytest.mark.asyncio
async def test_student_credit_adjust_preview_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = student_actions.register_tools(mcp, client)

    result = await tools["instainstru_student_credit_adjust_preview"](
        student_id="01STU",
        action="ADD",
        amount=25.0,
        reason_code="GOODWILL",
        note=None,
        expires_at=None,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "credit_adjust_preview"
    assert params["action"] == "ADD"


@pytest.mark.asyncio
async def test_student_credit_adjust_execute_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = student_actions.register_tools(mcp, client)

    result = await tools["instainstru_student_credit_adjust_execute"](
        student_id="01STU",
        confirm_token="ctok_123",
        idempotency_key="idem_123",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "credit_adjust_execute"
    assert params["idempotency_key"] == "idem_123"


@pytest.mark.asyncio
async def test_student_credit_history_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = student_actions.register_tools(mcp, client)

    result = await tools["instainstru_student_credit_history"](
        student_id="01STU",
        include_expired=False,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "credit_history"
    assert params["include_expired"] is False


@pytest.mark.asyncio
async def test_student_refund_history_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = student_actions.register_tools(mcp, client)

    result = await tools["instainstru_student_refund_history"](
        student_id="01STU",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "refund_history"
    assert params["student_id"] == "01STU"
