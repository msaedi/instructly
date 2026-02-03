from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastmcp import FastMCP
from instainstru_mcp.tools import growth


def _set_auth(monkeypatch, auth):
    def fake_request():
        class Dummy:
            scope = {"auth": auth}

        return Dummy()

    monkeypatch.setattr(growth, "get_http_request", fake_request)


class FakeClient:
    def __init__(
        self,
        *,
        booking_payloads=None,
        top_payload=None,
        zero_payload=None,
        coverage_payload=None,
        funnel_payload=None,
        raise_on=None,
    ) -> None:
        self.booking_payloads = booking_payloads or {}
        self.top_payload = top_payload or {}
        self.zero_payload = zero_payload or {}
        self.coverage_payload = coverage_payload or {}
        self.funnel_payload = funnel_payload or {}
        self.raise_on = set(raise_on or [])

    async def get_booking_summary(self, period="today", *, start_date=None, end_date=None):
        if "get_booking_summary" in self.raise_on:
            raise RuntimeError("boom")
        if start_date or end_date:
            key = f"{start_date}:{end_date}"
            return self.booking_payloads.get(key, {})
        return self.booking_payloads.get(period, {})

    async def get_top_queries(self, **_filters):
        if "get_top_queries" in self.raise_on:
            raise RuntimeError("boom")
        return self.top_payload

    async def get_zero_results(self, **_filters):
        if "get_zero_results" in self.raise_on:
            raise RuntimeError("boom")
        return self.zero_payload

    async def get_instructor_coverage(self, **_filters):
        if "get_instructor_coverage" in self.raise_on:
            raise RuntimeError("boom")
        return self.coverage_payload

    async def get_funnel_summary(self):
        if "get_funnel_summary" in self.raise_on:
            raise RuntimeError("boom")
        return self.funnel_payload


def test_require_scope_variants(monkeypatch):
    _set_auth(monkeypatch, {"method": "simple_token"})
    growth._require_scope("mcp:read")

    _set_auth(monkeypatch, {"method": "jwt", "claims": {}})
    growth._require_scope("mcp:read")

    _set_auth(monkeypatch, {"method": "oauth", "claims": "bad", "scope": "mcp:read"})
    growth._require_scope("mcp:read")

    _set_auth(monkeypatch, {"method": "oauth", "claims": {"scope": "mcp:read"}})
    with pytest.raises(PermissionError):
        growth._require_scope("mcp:write")


def test_period_ranges():
    now = datetime(2026, 2, 2, 15, 30, tzinfo=timezone.utc)

    start, end = growth._get_period_range("today", now)
    assert start == datetime(2026, 2, 2, tzinfo=timezone.utc)
    assert end == growth._end_of_day(now)

    start, end = growth._get_period_range("yesterday", now)
    assert start == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert end == growth._end_of_day(start)

    start, end = growth._get_period_range("last_7_days", now)
    assert start == datetime(2026, 1, 27, tzinfo=timezone.utc)
    assert end == growth._end_of_day(now)

    start, end = growth._get_period_range("last_30_days", now)
    assert start == datetime(2026, 1, 4, tzinfo=timezone.utc)

    start, end = growth._get_period_range("this_month", now)
    assert start == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert end == growth._end_of_day(now)

    with pytest.raises(ValueError):
        growth._get_period_range("bad")  # type: ignore[arg-type]


def test_comparison_ranges():
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    end = datetime(2026, 2, 2, tzinfo=timezone.utc)

    compare_start, compare_end = growth._get_comparison_range(start, end, "previous_period")
    duration = end - start
    assert compare_end == start - timedelta(microseconds=1)
    assert compare_start == compare_end - duration

    compare_start, compare_end = growth._get_comparison_range(start, end, "same_period_last_week")
    assert compare_start == start - timedelta(days=7)
    assert compare_end == end - timedelta(days=7)

    compare_start, compare_end = growth._get_comparison_range(start, end, "same_period_last_month")
    assert compare_start == start - timedelta(days=30)
    assert compare_end == end - timedelta(days=30)

    with pytest.raises(ValueError):
        growth._get_comparison_range(start, end, "bad")  # type: ignore[arg-type]


def test_calc_delta_and_cents():
    assert growth._calc_delta(None, 1) is None
    assert growth._calc_delta(1, None) is None
    assert growth._calc_delta(1, 0) == {"abs": 1, "pct": None}
    assert growth._calc_delta(3, 2) == {"abs": 1, "pct": 0.5}

    assert growth._cents_to_dollars(12345) == 123.45
    assert growth._cents_to_dollars("bad") is None


def test_extract_booking_metrics_summary():
    payload = {
        "summary": {
            "total_bookings": 5,
            "by_status": {"completed": 3, "cancelled": 1, "pending": 1, "confirmed": 1},
            "total_revenue_cents": 10000,
            "avg_booking_value_cents": 2000,
            "top_categories": [
                {"category": "Music", "count": 2},
                "bad",
            ],
        }
    }
    result = growth._extract_booking_metrics(payload)
    assert result["total"] == 5
    assert result["completed"] == 3
    assert result["cancelled"] == 1
    assert result["pending"] == 2
    assert result["gmv"] == 100.0
    assert result["avg_booking_value"] == 20.0
    assert result["by_category"][0]["gmv"] == 40.0


def test_extract_booking_metrics_without_summary():
    payload = {
        "total_bookings": 1,
        "by_status": [],
        "total_revenue_cents": "bad",
    }
    result = growth._extract_booking_metrics(payload)
    assert result["total"] == 1
    assert result["gmv"] is None

    empty = growth._extract_booking_metrics(None)
    assert empty["total"] == 0
    assert empty["gmv"] is None


def test_estimate_revenue():
    result = growth._estimate_revenue(None)
    assert result["total_platform_revenue"] is None

    result = growth._estimate_revenue(100.0)
    assert result["total_platform_revenue"] == 20.0
    assert result["instructor_payouts"] == 80.0
    assert result["take_rate"] == growth.DEFAULT_TAKE_RATE


def test_extract_search_analytics():
    top_payload = {
        "data": {
            "total_searches": 100,
            "queries": [
                {"query": "piano", "count": 10, "conversion_rate": 0.4},
                "bad",
            ],
        }
    }
    zero_payload = {
        "data": {
            "total_zero_result_searches": 5,
            "zero_result_rate": 0.05,
            "queries": [{"query": "cello", "count": 2}, "bad"],
        }
    }
    result = growth._extract_search_analytics(top_payload, zero_payload)
    assert result["search_volume"]["total_searches"] == 100
    assert result["search_volume"]["searches_with_results"] == 95
    assert result["top_queries"][0]["query"] == "piano"
    assert result["zero_results"][0]["query"] == "cello"


def test_extract_supply_metrics():
    coverage_payload = {"data": {"labels": ["Music"], "values": [5], "total_instructors": 10}}
    funnel_payload = {"founding_cap": {"used": 3}}
    result = growth._extract_supply_metrics(coverage_payload, funnel_payload)
    assert result["active_instructors"]["total"] == 10
    assert result["active_instructors"]["founding"] == 3
    assert result["by_category"][0]["category"] == "Music"


def test_generate_summary_variants():
    current = {"total": 10, "gmv": 1000.0}
    compare = {"total": 8, "gmv": 800.0}
    demand = {"zero_results": [{"query": "cello", "count": 2}]}
    summary = growth._generate_summary(current, compare, demand)
    assert summary["status"] == "growing"
    assert summary["highlights"]
    assert summary["concerns"]

    current = {"total": 5, "gmv": 400.0}
    compare = {"total": 8, "gmv": 900.0}
    summary = growth._generate_summary(current, compare, {})
    assert summary["status"] == "declining"
    assert any("Bookings down" in item for item in summary["concerns"])

    current = {"total": 5, "gmv": 400.0}
    compare = {"total": 5, "gmv": 400.0}
    summary = growth._generate_summary(current, compare, {})
    assert summary["status"] == "stable"
    assert summary["headline"] == "Metrics stable vs comparison period"

    summary = growth._generate_summary(current, None, None)
    assert summary["status"] == "stable"
    assert "no comparison data" in summary["headline"]


@pytest.mark.asyncio
async def test_growth_snapshot_full(monkeypatch):
    _set_auth(monkeypatch, {"method": "simple_token"})
    fixed_now = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(growth, "_utc_now", lambda: fixed_now)
    booking_payloads = {
        "2026-02-03:2026-02-03": {
            "summary": {
                "total_bookings": 10,
                "by_status": {"completed": 8, "cancelled": 1, "pending": 1},
                "total_revenue_cents": 10000,
                "avg_booking_value_cents": 1000,
                "top_categories": [{"category": "Music", "count": 2}],
            }
        },
        "2026-02-02:2026-02-02": {
            "summary": {
                "total_bookings": 8,
                "by_status": {"completed": 6, "cancelled": 1, "pending": 1},
                "total_revenue_cents": 8000,
                "avg_booking_value_cents": 1000,
                "top_categories": [{"category": "Music", "count": 1}],
            }
        },
    }
    top_payload = {"data": {"total_searches": 50, "queries": []}}
    zero_payload = {
        "data": {
            "total_zero_result_searches": 5,
            "zero_result_rate": 0.1,
            "queries": [],
        }
    }
    coverage_payload = {"data": {"labels": ["Music"], "values": [5], "total_instructors": 10}}
    funnel_payload = {"founding_cap": {"used": 3}}

    client = FakeClient(
        booking_payloads=booking_payloads,
        top_payload=top_payload,
        zero_payload=zero_payload,
        coverage_payload=coverage_payload,
        funnel_payload=funnel_payload,
    )
    mcp = FastMCP("test")
    tools = growth.register_tools(mcp, client)

    result = await tools["instainstru_growth_snapshot"](
        period="today",
        compare_to="previous_period",
        include_search_analytics=True,
        include_supply_metrics=True,
    )

    assert result["summary"]["status"] == "growing"
    assert result["bookings"]["current_period"]["total"] == 10
    assert result["bookings"]["comparison_period"]["total"] == 8
    assert result["bookings"]["delta"]["total"]["abs"] == 2
    assert result["revenue"]["delta"]["total_platform_revenue"]["abs"] == 4.0
    assert result["demand"]["search_volume"]["total_searches"] == 50
    assert result["supply"]["active_instructors"]["total"] == 10
    assert result["funnel"]["conversion_rate"] == pytest.approx(0.16)


@pytest.mark.asyncio
async def test_growth_snapshot_previous_period_range(monkeypatch):
    _set_auth(monkeypatch, {"method": "simple_token"})
    fixed_now = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(growth, "_utc_now", lambda: fixed_now)
    booking_payloads = {
        "2026-01-28:2026-02-03": {
            "summary": {
                "total_bookings": 5,
                "by_status": {"completed": 4},
                "total_revenue_cents": 5000,
                "avg_booking_value_cents": 1000,
                "top_categories": [],
            }
        },
        "2026-01-21:2026-01-27": {
            "summary": {
                "total_bookings": 3,
                "by_status": {"completed": 2},
                "total_revenue_cents": 3000,
                "avg_booking_value_cents": 1000,
                "top_categories": [],
            }
        },
    }
    client = FakeClient(booking_payloads=booking_payloads)
    mcp = FastMCP("test")
    tools = growth.register_tools(mcp, client)

    result = await tools["instainstru_growth_snapshot"](
        period="last_7_days",
        compare_to="previous_period",
        include_search_analytics=False,
        include_supply_metrics=False,
    )

    assert result["bookings"]["current_period"]["total"] == 5
    assert result["bookings"]["comparison_period"]["total"] == 3
    assert result["bookings"]["delta"]["total"]["abs"] == 2


@pytest.mark.asyncio
async def test_growth_snapshot_no_compare_no_extras(monkeypatch):
    _set_auth(monkeypatch, {"method": "simple_token"})
    fixed_now = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(growth, "_utc_now", lambda: fixed_now)
    booking_payloads = {
        "2026-02-02:2026-02-02": {
            "summary": {
                "total_bookings": 4,
                "by_status": {"completed": 2},
                "total_revenue_cents": 4000,
            }
        }
    }
    client = FakeClient(booking_payloads=booking_payloads)
    mcp = FastMCP("test")
    tools = growth.register_tools(mcp, client)

    result = await tools["instainstru_growth_snapshot"](
        period="yesterday",
        compare_to="previous_period",
        include_search_analytics=False,
        include_supply_metrics=False,
    )

    assert result["bookings"]["comparison_period"] is None
    assert result["revenue"]["comparison_period"] is None
    assert result["demand"]["included"] is False
    assert result["supply"]["included"] is False


@pytest.mark.asyncio
async def test_growth_snapshot_handles_exceptions(monkeypatch):
    _set_auth(monkeypatch, {"method": "simple_token"})
    client = FakeClient(raise_on={"get_booking_summary"})
    mcp = FastMCP("test")
    tools = growth.register_tools(mcp, client)

    result = await tools["instainstru_growth_snapshot"](
        period="today",
        include_search_analytics=False,
        include_supply_metrics=False,
    )

    assert result["bookings"]["current_period"]["total"] == 0
    assert result["summary"]["status"] == "stable"


@pytest.mark.asyncio
async def test_growth_snapshot_conversion_rate_exception(monkeypatch):
    _set_auth(monkeypatch, {"method": "simple_token"})

    def fake_extract(_payload):
        return {
            "total": 1,
            "completed": "bad",
            "gmv": None,
            "by_category": [],
            "by_location_type": [],
        }

    monkeypatch.setattr(growth, "_extract_booking_metrics", fake_extract)

    client = FakeClient(top_payload={"data": {"total_searches": 10}})
    mcp = FastMCP("test")
    tools = growth.register_tools(mcp, client)

    result = await tools["instainstru_growth_snapshot"](
        period="today",
        include_search_analytics=True,
        include_supply_metrics=False,
    )

    assert result["funnel"]["conversion_rate"] is None
