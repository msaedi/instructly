import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import (
    celery,
    founding,
    instructors,
    invites,
    metrics,
    operations,
    search,
    services,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def get_funnel_summary(self, start_date=None, end_date=None):
        self.calls.append(
            ("get_funnel_summary", (), {"start_date": start_date, "end_date": end_date})
        )
        return {"ok": True}

    async def get_stuck_instructors(self, stuck_days=7, stage=None, limit=50):
        self.calls.append(
            (
                "get_stuck_instructors",
                (),
                {"stuck_days": stuck_days, "stage": stage, "limit": limit},
            )
        )
        return {"ok": True}

    async def list_instructors(self, **filters):
        self.calls.append(("list_instructors", (), filters))
        return {"ok": True}

    async def get_instructor_coverage(self, status="live", group_by="category", top=25):
        self.calls.append(
            (
                "get_instructor_coverage",
                (),
                {"status": status, "group_by": group_by, "top": top},
            )
        )
        return {"ok": True}

    async def get_instructor_detail(self, identifier):
        self.calls.append(("get_instructor_detail", (identifier,), {}))
        return {"ok": True}

    async def preview_invites(self, **payload):
        self.calls.append(("preview_invites", (), payload))
        return {"ok": True}

    async def send_invites(self, confirm_token, idempotency_key):
        self.calls.append(
            (
                "send_invites",
                (confirm_token, idempotency_key),
                {},
            )
        )
        return {"ok": True}

    async def list_invites(self, **filters):
        self.calls.append(("list_invites", (), filters))
        return {"ok": True}

    async def get_invite_detail(self, identifier):
        self.calls.append(("get_invite_detail", (identifier,), {}))
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

    async def get_services_catalog(self):
        self.calls.append(("get_services_catalog", (), {}))
        return {"ok": True}

    async def lookup_service(self, query):
        self.calls.append(("lookup_service", (query,), {}))
        return {"ok": True}

    async def get_celery_workers(self):
        self.calls.append(("get_celery_workers", (), {}))
        return {"ok": True}

    async def get_celery_queues(self):
        self.calls.append(("get_celery_queues", (), {}))
        return {"ok": True}

    async def get_celery_failed_tasks(self, limit=50):
        self.calls.append(("get_celery_failed_tasks", (), {"limit": limit}))
        return {"ok": True}

    async def get_celery_payment_health(self):
        self.calls.append(("get_celery_payment_health", (), {}))
        return {"ok": True}

    async def get_celery_active_tasks(self):
        self.calls.append(("get_celery_active_tasks", (), {}))
        return {"ok": True}

    async def get_celery_task_history(self, task_name=None, state=None, hours=1, limit=100):
        self.calls.append(
            (
                "get_celery_task_history",
                (),
                {"task_name": task_name, "state": state, "hours": hours, "limit": limit},
            )
        )
        return {"ok": True}

    async def get_celery_beat_schedule(self):
        self.calls.append(("get_celery_beat_schedule", (), {}))
        return {"ok": True}

    async def get_booking_summary(self, period="today"):
        self.calls.append(("get_booking_summary", (), {"period": period}))
        return {"ok": True}

    async def get_recent_bookings(self, status=None, limit=20, hours=24):
        self.calls.append(
            ("get_recent_bookings", (), {"status": status, "limit": limit, "hours": hours})
        )
        return {"ok": True}

    async def get_payment_pipeline(self):
        self.calls.append(("get_payment_pipeline", (), {}))
        return {"ok": True}

    async def get_pending_payouts(self, limit=20):
        self.calls.append(("get_pending_payouts", (), {"limit": limit}))
        return {"ok": True}

    async def lookup_user(self, identifier):
        self.calls.append(("lookup_user", (), {"identifier": identifier}))
        return {"ok": True}

    async def get_user_booking_history(self, user_id, limit=20):
        self.calls.append(("get_user_booking_history", (), {"user_id": user_id, "limit": limit}))
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

    result = await tools["instainstru_founding_stuck_instructors"](
        stuck_days=10, stage="profile_submitted", limit=5
    )
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

    result = await tools["instainstru_instructors_coverage"](
        status="live", group_by="service", top=5
    )
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

    result = await tools["instainstru_invites_list"](
        email="a@example.com",
        status="pending",
        start_date="2026-01-01",
        end_date="2026-01-31",
        limit=25,
        cursor="cursor",
    )
    assert result == {"ok": True}
    assert client.calls[2][0] == "list_invites"
    assert client.calls[2][2]["email"] == "a@example.com"

    result = await tools["instainstru_invites_detail"]("INVITE1")
    assert result == {"ok": True}
    assert client.calls[3][0] == "get_invite_detail"
    assert client.calls[3][1][0] == "INVITE1"


@pytest.mark.asyncio
async def test_services_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = services.register_tools(mcp, client)

    result = await tools["instainstru_services_catalog"]()
    assert result == {"ok": True}
    assert client.calls[0][0] == "get_services_catalog"

    result = await tools["instainstru_service_lookup"]("swim")
    assert result == {"ok": True}
    assert client.calls[1][0] == "lookup_service"
    assert client.calls[1][1][0] == "swim"


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

    result = await tools["instainstru_search_zero_results"](
        start_date="2026-01-01", end_date="2026-01-31", limit=5
    )
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


@pytest.mark.asyncio
async def test_metrics_describe_alias_returns_local_definition():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = metrics.register_tools(mcp, client)

    result = await tools["instainstru_metrics_describe"]("p99 latency")
    assert result["metric"]["name"] == "instainstru_http_request_duration_seconds"
    assert client.calls == []


@pytest.mark.asyncio
async def test_metrics_describe_lists_metrics_when_empty():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = metrics.register_tools(mcp, client)

    result = await tools["instainstru_metrics_describe"]()
    assert result["count"] > 0
    assert "supported_questions" in result


@pytest.mark.asyncio
async def test_celery_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = celery.register_tools(mcp, client)

    result = await tools["instainstru_celery_worker_status"]()
    assert result == {"ok": True}
    result = await tools["instainstru_celery_queue_depth"]()
    assert result == {"ok": True}
    result = await tools["instainstru_celery_failed_tasks"](limit=5)
    assert result == {"ok": True}
    result = await tools["instainstru_celery_payment_health"]()
    assert result == {"ok": True}
    result = await tools["instainstru_celery_active_tasks"]()
    assert result == {"ok": True}
    result = await tools["instainstru_celery_task_history"](
        task_name="task", state="FAILURE", hours=2, limit=10
    )
    assert result == {"ok": True}
    result = await tools["instainstru_celery_beat_schedule"]()
    assert result == {"ok": True}

    assert client.calls[0][0] == "get_celery_workers"
    assert client.calls[1][0] == "get_celery_queues"
    assert client.calls[2][2]["limit"] == 5
    assert client.calls[3][0] == "get_celery_payment_health"
    assert client.calls[4][0] == "get_celery_active_tasks"
    assert client.calls[5][2]["task_name"] == "task"
    assert client.calls[6][0] == "get_celery_beat_schedule"


@pytest.mark.asyncio
async def test_operations_tools_call_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = operations.register_tools(mcp, client)

    result = await tools["instainstru_bookings_summary"](period="last_7_days")
    assert result == {"ok": True}
    result = await tools["instainstru_bookings_recent"](status="confirmed", limit=10, hours=48)
    assert result == {"ok": True}
    result = await tools["instainstru_payments_pipeline"]()
    assert result == {"ok": True}
    result = await tools["instainstru_payments_pending_payouts"](limit=5)
    assert result == {"ok": True}
    result = await tools["instainstru_users_lookup"](identifier="user@example.com")
    assert result == {"ok": True}
    result = await tools["instainstru_users_booking_history"](user_id="01USER", limit=15)
    assert result == {"ok": True}

    assert client.calls[0][0] == "get_booking_summary"
    assert client.calls[0][2]["period"] == "last_7_days"
    assert client.calls[1][2]["status"] == "confirmed"
    assert client.calls[2][0] == "get_payment_pipeline"
    assert client.calls[3][2]["limit"] == 5
    assert client.calls[4][2]["identifier"] == "user@example.com"
    assert client.calls[5][2]["user_id"] == "01USER"
