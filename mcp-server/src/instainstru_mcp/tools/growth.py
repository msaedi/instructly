"""
Growth Command Center - Business health metrics.

Aggregates bookings, revenue, supply, and demand signals.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from ..client import InstaInstruClient

PeriodLiteral = Literal[
    "today",
    "yesterday",
    "last_7_days",
    "last_30_days",
    "this_month",
]
CompareLiteral = Literal[
    "previous_period",
    "same_period_last_week",
    "same_period_last_month",
]

BOOKINGS_PERIOD_MAP: dict[str, str] = {
    "today": "today",
    "yesterday": "yesterday",
    "last_7_days": "last_7_days",
    "this_month": "this_month",
    "last_30_days": "this_month",
}

DEFAULT_TAKE_RATE = 0.20


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_scope(required_scope: str) -> None:
    request = get_http_request()
    auth = getattr(request, "scope", {}).get("auth", {})
    method = auth.get("method") if isinstance(auth, dict) else None
    if method == "simple_token":
        return
    claims = auth.get("claims", {}) if isinstance(auth, dict) else {}
    scope_value = ""
    if isinstance(claims, dict):
        scope_value = claims.get("scope") or claims.get("scp") or ""
    if not scope_value and isinstance(auth, dict):
        scope_value = auth.get("scope") or ""
    scopes = {scope for scope in scope_value.split() if scope}
    if required_scope not in scopes:
        if required_scope == "mcp:read" and method in {"jwt", "workos"}:
            return
        raise PermissionError(f"Missing required scope: {required_scope}")


def _start_of_day(day: datetime) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _end_of_day(day: datetime) -> datetime:
    return _start_of_day(day) + timedelta(days=1) - timedelta(microseconds=1)


def _get_period_range(
    period: PeriodLiteral, now: datetime | None = None
) -> tuple[datetime, datetime]:
    reference = now or _utc_now()
    today = _start_of_day(reference)

    if period == "today":
        return today, _end_of_day(reference)
    if period == "yesterday":
        day = today - timedelta(days=1)
        return day, _end_of_day(day)
    if period == "last_7_days":
        start = today - timedelta(days=6)
        return start, _end_of_day(reference)
    if period == "last_30_days":
        start = today - timedelta(days=29)
        return start, _end_of_day(reference)
    if period == "this_month":
        start = datetime(reference.year, reference.month, 1, tzinfo=timezone.utc)
        return start, _end_of_day(reference)

    raise ValueError("Unsupported period")


def _get_comparison_range(
    period_start: datetime,
    period_end: datetime,
    compare_to: CompareLiteral,
) -> tuple[datetime, datetime]:
    if compare_to == "previous_period":
        duration = period_end - period_start
        compare_end = period_start - timedelta(microseconds=1)
        compare_start = compare_end - duration
        return compare_start, compare_end
    if compare_to == "same_period_last_week":
        return period_start - timedelta(days=7), period_end - timedelta(days=7)
    if compare_to == "same_period_last_month":
        return period_start - timedelta(days=30), period_end - timedelta(days=30)
    raise ValueError("Unsupported comparison period")


def _calc_delta(current: float | None, compare: float | None) -> dict[str, Any] | None:
    if current is None or compare is None:
        return None
    delta_abs = current - compare
    if abs(compare) < 1e-9:
        return {"abs": delta_abs, "pct": None}
    return {"abs": delta_abs, "pct": delta_abs / abs(compare)}


def _cents_to_dollars(value: Any) -> float | None:
    try:
        cents = float(value)
    except (TypeError, ValueError):
        return None
    return round(cents / 100.0, 2)


def _extract_booking_metrics(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {
            "total": 0,
            "completed": 0,
            "cancelled": 0,
            "pending": 0,
            "gmv": None,
            "avg_booking_value": None,
            "by_category": [],
            "by_location_type": [],
        }

    summary = payload.get("summary") if isinstance(payload, dict) else None
    summary_data = summary if isinstance(summary, dict) else payload
    total = int(summary_data.get("total_bookings", 0) or 0)
    by_status = summary_data.get("by_status") if isinstance(summary_data, dict) else {}
    by_status = by_status if isinstance(by_status, dict) else {}

    completed = int(by_status.get("completed", 0) or 0)
    cancelled = int(by_status.get("cancelled", 0) or 0)
    pending = int(by_status.get("pending", 0) or 0) + int(by_status.get("confirmed", 0) or 0)

    gmv = _cents_to_dollars(summary_data.get("total_revenue_cents"))
    avg_value = _cents_to_dollars(summary_data.get("avg_booking_value_cents"))

    categories = []
    for item in summary_data.get("top_categories", []) or []:
        if not isinstance(item, dict):
            continue
        count = int(item.get("count", 0) or 0)
        gmv_est = round((avg_value or 0) * count, 2) if avg_value is not None else None
        categories.append(
            {
                "category": item.get("category"),
                "count": count,
                "gmv": gmv_est,
            }
        )

    return {
        "total": total,
        "completed": completed,
        "cancelled": cancelled,
        "pending": pending,
        "gmv": gmv,
        "avg_booking_value": avg_value,
        "by_category": categories,
        "by_location_type": [],
    }


def _estimate_revenue(gmv: float | None) -> dict[str, Any]:
    if gmv is None:
        return {
            "platform_fees": None,
            "instructor_commissions": None,
            "total_platform_revenue": None,
            "instructor_payouts": None,
            "take_rate": None,
        }
    total_platform_revenue = round(gmv * DEFAULT_TAKE_RATE, 2)
    instructor_payouts = round(gmv - total_platform_revenue, 2)
    return {
        "platform_fees": None,
        "instructor_commissions": None,
        "total_platform_revenue": total_platform_revenue,
        "instructor_payouts": instructor_payouts,
        "take_rate": DEFAULT_TAKE_RATE,
    }


def _extract_search_analytics(
    top_payload: dict[str, Any] | None,
    zero_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    top_data = top_payload.get("data") if isinstance(top_payload, dict) else None
    zero_data = zero_payload.get("data") if isinstance(zero_payload, dict) else None

    total_searches = None
    if isinstance(top_data, dict):
        total_searches = top_data.get("total_searches")
    zero_total = None
    zero_rate = None
    if isinstance(zero_data, dict):
        zero_total = zero_data.get("total_zero_result_searches")
        zero_rate = zero_data.get("zero_result_rate")

    searches_with_results = None
    if isinstance(total_searches, int) and isinstance(zero_total, int):
        searches_with_results = max(0, total_searches - zero_total)

    top_queries = []
    if isinstance(top_data, dict):
        for row in top_data.get("queries", []) or []:
            if not isinstance(row, dict):
                continue
            top_queries.append(
                {
                    "query": row.get("query"),
                    "count": row.get("count"),
                    "conversion_rate": row.get("conversion_rate"),
                }
            )

    zero_queries = []
    if isinstance(zero_data, dict):
        for row in zero_data.get("queries", []) or []:
            if not isinstance(row, dict):
                continue
            zero_queries.append({"query": row.get("query"), "count": row.get("count")})

    return {
        "search_volume": {
            "total_searches": total_searches,
            "unique_users": None,
            "searches_with_results": searches_with_results,
            "zero_result_rate": zero_rate,
        },
        "top_queries": top_queries,
        "trending": [],
        "zero_results": zero_queries,
    }


def _extract_supply_metrics(
    coverage_payload: dict[str, Any] | None,
    funnel_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    coverage_data = coverage_payload.get("data") if isinstance(coverage_payload, dict) else None
    labels: list[str] = []
    values: list[Any] = []
    total_instructors = None
    if isinstance(coverage_data, dict):
        labels = coverage_data.get("labels") or []
        values = coverage_data.get("values") or []
        total_instructors = coverage_data.get("total_instructors")

    by_category = []
    for label, value in zip(labels, values):
        by_category.append(
            {
                "category": label,
                "instructors": value,
                "bookings": None,
            }
        )

    founding_used = None
    if isinstance(funnel_payload, dict):
        founding_cap = funnel_payload.get("founding_cap")
        if isinstance(founding_cap, dict):
            founding_used = founding_cap.get("used")

    return {
        "active_instructors": {
            "total": total_instructors,
            "with_bookings_this_period": None,
            "new_this_period": None,
            "founding": founding_used,
        },
        "availability": {
            "total_hours_posted": None,
            "utilization_rate": None,
        },
        "by_category": by_category,
        "gaps": [],
    }


def _generate_summary(
    current: dict[str, Any],
    comparison: dict[str, Any] | None,
    demand: dict[str, Any] | None,
) -> dict[str, Any]:
    highlights: list[str] = []
    concerns: list[str] = []

    total_current = current.get("total") or 0
    total_compare = (comparison or {}).get("total") if comparison else None

    booking_delta = None
    if isinstance(total_compare, int):
        booking_delta = total_current - total_compare

    gmv_current = current.get("gmv")
    gmv_compare = (comparison or {}).get("gmv") if comparison else None
    gmv_delta = None
    if isinstance(gmv_current, (int, float)) and isinstance(gmv_compare, (int, float)):
        gmv_delta = gmv_current - gmv_compare

    if booking_delta is not None:
        if booking_delta > 0:
            pct = booking_delta / max(total_compare or 1, 1) * 100
            highlights.append(f"{total_current} bookings (+{booking_delta}, +{pct:.0f}%)")
        elif booking_delta < 0:
            concerns.append(f"Bookings down {abs(booking_delta)} vs comparison period")

    if gmv_delta is not None and gmv_current is not None:
        if gmv_delta > 0:
            highlights.append(f"GMV ${gmv_current:,.0f} (+${gmv_delta:,.0f})")
        elif gmv_delta < 0:
            concerns.append(f"GMV down ${abs(gmv_delta):,.0f} vs comparison period")

    if demand:
        for zr in (demand.get("zero_results") or [])[:3]:
            query = zr.get("query")
            count = zr.get("count")
            if query:
                concerns.append(f"No results for '{query}' ({count} searches)")

    if booking_delta is not None and gmv_delta is not None:
        if booking_delta > 0 and gmv_delta > 0:
            status = "growing"
            headline = (
                f"Bookings up {booking_delta / max(total_compare or 1, 1) * 100:.0f}% vs comparison"
            )
        elif booking_delta < 0:
            status = "declining"
            headline = f"Bookings down {abs(booking_delta)} vs comparison"
        else:
            status = "stable"
            headline = "Metrics stable vs comparison period"
    else:
        status = "stable"
        headline = "Metrics stable (no comparison data)"

    return {
        "status": status,
        "headline": headline,
        "highlights": highlights,
        "concerns": concerns,
    }


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_growth_snapshot(
        period: PeriodLiteral = "today",
        compare_to: CompareLiteral = "previous_period",
        include_search_analytics: bool = True,
        include_supply_metrics: bool = True,
    ) -> dict:
        """
        Get a business health snapshot.

        Returns:
        - Booking metrics (count, GMV, completed, cancelled)
        - Revenue metrics (platform fees, instructor payouts)
        - Supply metrics (active instructors, new signups, coverage)
        - Demand signals (search queries, zero results, trending categories)
        - Comparison to previous period

        Args:
            period: Time period to analyze
            compare_to: Comparison period for deltas
            include_search_analytics: Include search demand data
            include_supply_metrics: Include instructor supply data
        """
        _require_scope("mcp:read")

        period_start, period_end = _get_period_range(period)
        compare_start, compare_end = _get_comparison_range(period_start, period_end, compare_to)

        bookings_period = BOOKINGS_PERIOD_MAP.get(period)
        compare_period = BOOKINGS_PERIOD_MAP.get(period)
        if compare_to == "previous_period" and period == "today":
            compare_period = "yesterday"
        elif compare_to == "previous_period" and period == "yesterday":
            compare_period = None

        tasks: list[tuple[str, Any]] = []
        if bookings_period:
            tasks.append(("bookings_current", client.get_booking_summary(period=bookings_period)))
        if compare_period:
            tasks.append(("bookings_compare", client.get_booking_summary(period=compare_period)))
        if include_search_analytics:
            start_date = period_start.date().isoformat()
            end_date = period_end.date().isoformat()
            tasks.append(
                (
                    "search_top",
                    client.get_top_queries(start_date=start_date, end_date=end_date, limit=20),
                )
            )
            tasks.append(
                (
                    "search_zero",
                    client.get_zero_results(start_date=start_date, end_date=end_date, limit=20),
                )
            )
        if include_supply_metrics:
            tasks.append(
                (
                    "coverage",
                    client.get_instructor_coverage(status="live", group_by="category", top=25),
                )
            )
            tasks.append(("funnel", client.get_funnel_summary()))

        results: dict[str, Any] = {}
        if tasks:
            gathered = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True,
            )
            for (key, _task), value in zip(tasks, gathered):
                if isinstance(value, BaseException):
                    results[key] = None
                else:
                    results[key] = value

        current_bookings = _extract_booking_metrics(results.get("bookings_current"))
        comparison_bookings = (
            _extract_booking_metrics(results.get("bookings_compare"))
            if results.get("bookings_compare")
            else None
        )

        bookings_delta = {
            "total": _calc_delta(
                current_bookings.get("total"), (comparison_bookings or {}).get("total")
            ),
            "gmv": _calc_delta(current_bookings.get("gmv"), (comparison_bookings or {}).get("gmv")),
        }

        revenue_current = _estimate_revenue(current_bookings.get("gmv"))
        revenue_compare = (
            _estimate_revenue((comparison_bookings or {}).get("gmv"))
            if comparison_bookings
            else None
        )
        revenue_delta = None
        if revenue_compare:
            revenue_delta = {
                "total_platform_revenue": _calc_delta(
                    revenue_current.get("total_platform_revenue"),
                    revenue_compare.get("total_platform_revenue"),
                )
            }

        demand = None
        if include_search_analytics:
            demand = _extract_search_analytics(
                results.get("search_top"), results.get("search_zero")
            )

        supply = None
        if include_supply_metrics:
            supply = _extract_supply_metrics(results.get("coverage"), results.get("funnel"))

        summary = _generate_summary(current_bookings, comparison_bookings, demand)

        funnel = {
            "searches": (demand or {}).get("search_volume", {}).get("total_searches"),
            "profile_views": None,
            "booking_started": None,
            "booking_completed": current_bookings.get("completed"),
            "conversion_rate": None,
        }
        if funnel["searches"] and current_bookings.get("completed"):
            try:
                funnel["conversion_rate"] = current_bookings["completed"] / max(
                    funnel["searches"], 1
                )
            except Exception:
                funnel["conversion_rate"] = None

        meta = {
            "generated_at": _utc_now().isoformat(),
            "period": period,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "compare_to": compare_to,
        }

        return {
            "meta": meta,
            "summary": summary,
            "bookings": {
                "current_period": current_bookings,
                "comparison_period": comparison_bookings,
                "delta": bookings_delta,
                "by_category": current_bookings.get("by_category", []),
                "by_location_type": current_bookings.get("by_location_type", []),
            },
            "revenue": {
                "current_period": revenue_current,
                "comparison_period": revenue_compare,
                "delta": revenue_delta,
                "take_rate": revenue_current.get("take_rate"),
            },
            "supply": supply if supply is not None else {"included": False},
            "demand": demand if demand is not None else {"included": False},
            "funnel": funnel,
        }

    mcp.tool()(instainstru_growth_snapshot)
    return {"instainstru_growth_snapshot": instainstru_growth_snapshot}


__all__ = [
    "register_tools",
    "_get_period_range",
    "_get_comparison_range",
    "_calc_delta",
    "_extract_booking_metrics",
    "_extract_search_analytics",
    "_extract_supply_metrics",
    "_generate_summary",
]
