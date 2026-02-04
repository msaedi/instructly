from __future__ import annotations

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import analytics


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def revenue_dashboard(self, **params):
        self.calls.append(("revenue_dashboard", params))
        return {"ok": True}

    async def booking_funnel(self, **params):
        self.calls.append(("booking_funnel", params))
        return {"ok": True}

    async def funnel_snapshot(self, **params):
        self.calls.append(("funnel_snapshot", params))
        return {"ok": True}

    async def supply_demand(self, **params):
        self.calls.append(("supply_demand", params))
        return {"ok": True}

    async def category_performance(self, **params):
        self.calls.append(("category_performance", params))
        return {"ok": True}

    async def cohort_retention(self, **params):
        self.calls.append(("cohort_retention", params))
        return {"ok": True}

    async def platform_alerts(self, **params):
        self.calls.append(("platform_alerts", params))
        return {"ok": True}


@pytest.mark.asyncio
async def test_revenue_dashboard_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = analytics.register_tools(mcp, client)

    result = await tools["instainstru_revenue_dashboard"](
        period="last_7_days",
        compare_to="previous_period",
        breakdown_by="day",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "revenue_dashboard"
    assert params["period"] == "last_7_days"


@pytest.mark.asyncio
async def test_booking_funnel_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = analytics.register_tools(mcp, client)

    result = await tools["instainstru_booking_funnel"](
        period="last_7_days",
        segment_by="device",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "booking_funnel"
    assert params["segment_by"] == "device"


@pytest.mark.asyncio
async def test_funnel_snapshot_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = analytics.register_tools(mcp, client)

    result = await tools["instainstru_funnel_snapshot"](
        period="last_7_days",
        compare_to="previous_period",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "funnel_snapshot"
    assert params["compare_to"] == "previous_period"


@pytest.mark.asyncio
async def test_supply_demand_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = analytics.register_tools(mcp, client)

    result = await tools["instainstru_supply_demand"](
        period="last_30_days",
        location="Manhattan",
        category="music",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "supply_demand"
    assert params["location"] == "Manhattan"


@pytest.mark.asyncio
async def test_category_performance_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = analytics.register_tools(mcp, client)

    result = await tools["instainstru_category_performance"](
        period="last_quarter",
        sort_by="revenue",
        limit=5,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "category_performance"
    assert params["limit"] == 5


@pytest.mark.asyncio
async def test_cohort_retention_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = analytics.register_tools(mcp, client)

    result = await tools["instainstru_cohort_retention"](
        user_type="student",
        cohort_period="month",
        periods_back=6,
        metric="active",
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "cohort_retention"
    assert params["periods_back"] == 6


@pytest.mark.asyncio
async def test_platform_alerts_calls_client():
    client = FakeClient()
    mcp = FastMCP("test")
    tools = analytics.register_tools(mcp, client)

    result = await tools["instainstru_platform_alerts"](
        severity="warning",
        category="revenue",
        acknowledged=False,
    )
    assert result == {"ok": True}
    name, params = client.calls[0]
    assert name == "platform_alerts"
    assert params["severity"] == "warning"
