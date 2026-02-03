import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import audit


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def audit_search(self, **filters):
        self.calls.append(("audit_search", (), filters))
        return {"ok": True}

    async def audit_user_activity(self, user_email: str, since_days: int = 30, limit: int = 100):
        self.calls.append(
            ("audit_user_activity", (user_email,), {"since_days": since_days, "limit": limit})
        )
        return {"ok": True}

    async def audit_resource_history(self, resource_type: str, resource_id: str, limit: int = 50):
        self.calls.append(
            (
                "audit_resource_history",
                (resource_type, resource_id),
                {"limit": limit},
            )
        )
        return {"ok": True}

    async def audit_recent_admin_actions(self, since_hours: int = 24, limit: int = 100):
        self.calls.append(
            ("audit_recent_admin_actions", (), {"since_hours": since_hours, "limit": limit})
        )
        return {"ok": True}


@pytest.mark.asyncio
async def test_audit_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = audit.register_tools(mcp, client)

    result = await tools["instainstru_audit_search"](
        actor_email="admin@instainstru.com",
        action="booking.cancel",
        since_hours=12,
        limit=10,
    )
    assert result == {"ok": True}
    assert client.calls[0][0] == "audit_search"
    assert client.calls[0][2]["actor_email"] == "admin@instainstru.com"
    assert client.calls[0][2]["action"] == "booking.cancel"
    assert client.calls[0][2]["since_hours"] == 12
    assert client.calls[0][2]["limit"] == 10

    result = await tools["instainstru_audit_user_activity"](
        user_email="user@example.com",
        since_days=7,
        limit=5,
    )
    assert result == {"ok": True}
    assert client.calls[1][0] == "audit_user_activity"
    assert client.calls[1][1] == ("user@example.com",)
    assert client.calls[1][2]["since_days"] == 7
    assert client.calls[1][2]["limit"] == 5

    result = await tools["instainstru_audit_resource_history"](
        resource_type="booking",
        resource_id="01HXY1234567890ABCDEFGHJKL",
        limit=3,
    )
    assert result == {"ok": True}
    assert client.calls[2][0] == "audit_resource_history"
    assert client.calls[2][1] == ("booking", "01HXY1234567890ABCDEFGHJKL")
    assert client.calls[2][2]["limit"] == 3

    result = await tools["instainstru_audit_recent_admin_actions"](since_hours=6, limit=20)
    assert result == {"ok": True}
    assert client.calls[3][0] == "audit_recent_admin_actions"
    assert client.calls[3][2] == {"since_hours": 6, "limit": 20}
