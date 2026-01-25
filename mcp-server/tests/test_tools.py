import pytest

from fastmcp import FastMCP

from instainstru_mcp.tools import founding, instructors, invites, metrics, search


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def get_funnel_summary(self, start_date=None, end_date=None):
        self.calls.append(("get_funnel_summary", (), {"start_date": start_date, "end_date": end_date}))
        return {"ok": True}

    async def get_stuck_instructors(self, stuck_days=7, stage=None, limit=50):
        self.calls.append((
            "get_stuck_instructors",
            (),
            {"stuck_days": stuck_days, "stage": stage, "limit": limit},
        ))
        return {"ok": True}

    async def list_instructors(self, **filters):
        self.calls.append(("list_instructors", (), filters))
        return {"ok": True}

    async def get_instructor_coverage(self, status="live", group_by="category", top=25):
        self.calls.append((
            "get_instructor_coverage",
            (),
            {"status": status, "group_by": group_by, "top": top},
        ))
        return {"ok": True}

    async def get_instructor_detail(self, identifier):
        self.calls.append(("get_instructor_detail", (identifier,), {}))
        return {"ok": True}

    async def preview_invites(self, **payload):
        self.calls.append(("preview_invites", (), payload))
        return {"ok": True}

    async def send_invites(self, confirm_token, idempotency_key):
        self.calls.append((
            "send_invites",
            (confirm_token, idempotency_key),
            {},
        ))
        return {"ok": True}

    async def get_top_queries(self, **filters):
        self.calls.append(("get_top_queries", (), filters))
        return {"ok": True}

    async def get_zero_results(self, **filters):
        self.calls.append(("get_zero_results", (), filters))
        return {"ok": True}

    async def get_metric(self, metric_name):
        self.calls.append(("get_metric", (metric_name,), {}))
        return {"ok": True}


@pytest.mark.asyncio
async def test_founding_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = founding.register_tools(mcp, client)

    result = await tools["instainstru_founding_funnel_summary"]("2026-01-01", "2026-01-31")
    assert result == {"ok": True}
    assert client.calls[0][0] == "get_funnel_summary"
    assert client.calls[0][2] == {"start_date": "2026-01-01", "end_date": "2026-01-31"}

    result = await tools["instainstru_founding_stuck_instructors"](stuck_days=10, stage="profile_submitted", limit=5)
    assert result == {"ok": True}
    assert client.calls[1][0] == "get_stuck_instructors"
    assert client.calls[1][2] == {"stuck_days": 10, "stage": "profile_submitted", "limit": 5}


@pytest.mark.asyncio
async def test_instructor_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = instructors.register_tools(mcp, client)

    result = await tools["instainstru_instructors_list"](
        status="live",
        is_founding=True,
        service_slug="guitar",
        category_slug="music",
        limit=10,
        cursor="cursor",
    )
    assert result == {"ok": True}
    assert client.calls[0][0] == "list_instructors"
    assert client.calls[0][2]["status"] == "live"
    assert client.calls[0][2]["is_founding"] is True

    result = await tools["instainstru_instructors_coverage"](status="live", group_by="service", top=5)
    assert result == {"ok": True}
    assert client.calls[1][0] == "get_instructor_coverage"
    assert client.calls[1][2] == {"status": "live", "group_by": "service", "top": 5}

    result = await tools["instainstru_instructors_detail"]("01HQX")
    assert result == {"ok": True}
    assert client.calls[2][0] == "get_instructor_detail"
    assert client.calls[2][1][0] == "01HQX"


@pytest.mark.asyncio
async def test_invite_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = invites.register_tools(mcp, client)

    result = await tools["instainstru_invites_preview"](
        recipient_emails=["a@example.com"],
        grant_founding_status=True,
        expires_in_days=7,
        message_note="hi",
    )
    assert result == {"ok": True}
    assert client.calls[0][0] == "preview_invites"
    assert client.calls[0][2]["recipient_emails"] == ["a@example.com"]

    result = await tools["instainstru_invites_send"]("token", "idem")
    assert result == {"ok": True}
    assert client.calls[1][0] == "send_invites"
    assert client.calls[1][1] == ("token", "idem")


@pytest.mark.asyncio
async def test_search_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = search.register_tools(mcp, client)

    result = await tools["instainstru_search_top_queries"](
        start_date="2026-01-01",
        end_date="2026-01-31",
        limit=10,
        min_count=3,
    )
    assert result == {"ok": True}
    assert client.calls[0][0] == "get_top_queries"
    assert client.calls[0][2]["min_count"] == 3

    result = await tools["instainstru_search_zero_results"](start_date="2026-01-01", end_date="2026-01-31", limit=5)
    assert result == {"ok": True}
    assert client.calls[1][0] == "get_zero_results"
    assert client.calls[1][2]["limit"] == 5


@pytest.mark.asyncio
async def test_metrics_tool_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = metrics.register_tools(mcp, client)

    result = await tools["instainstru_metrics_describe"]("instructor.live")
    assert result == {"ok": True}
    assert client.calls[0][0] == "get_metric"
    assert client.calls[0][1][0] == "instructor.live"
