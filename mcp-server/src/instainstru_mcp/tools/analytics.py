"""MCP tools for platform analytics."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_revenue_dashboard(
        period: str,
        compare_to: str | None = "previous_period",
        breakdown_by: str | None = None,
    ) -> dict:
        """
        Retrieve revenue dashboard metrics.

        Args:
            period: today, yesterday, last_7_days, last_30_days, this_month, last_month, this_quarter
            compare_to: previous_period, same_period_last_month, same_period_last_year
            breakdown_by: day, week, category
        """
        return await client.revenue_dashboard(
            period=period,
            compare_to=compare_to,
            breakdown_by=breakdown_by,
        )

    async def instainstru_booking_funnel(
        period: str,
        segment_by: str | None = None,
    ) -> dict:
        """
        Retrieve booking funnel analytics.

        Args:
            period: last_7_days, last_30_days, this_month
            segment_by: device, category, source
        """
        return await client.booking_funnel(period=period, segment_by=segment_by)

    async def instainstru_funnel_snapshot(
        period: str = "last_7_days",
        compare_to: str | None = None,
    ) -> dict:
        """
        Conversion funnel analysis: where do users drop off?

        Shows: visits → signup → verified → search → booking_started → booking_confirmed → completed

        Args:
            period: today, yesterday, last_7_days, last_30_days, this_month
            compare_to: previous_period, same_period_last_week, same_period_last_month
        """
        return await client.funnel_snapshot(period=period, compare_to=compare_to)

    async def instainstru_supply_demand(
        period: str,
        location: str | None = None,
        category: str | None = None,
    ) -> dict:
        """
        Retrieve supply vs demand metrics.

        Args:
            period: last_7_days, last_30_days
            location: Neighborhood or borough
            category: Service category
        """
        return await client.supply_demand(period=period, location=location, category=category)

    async def instainstru_category_performance(
        period: str,
        sort_by: str = "revenue",
        limit: int = 20,
    ) -> dict:
        """
        Retrieve category performance metrics.

        Args:
            period: last_7_days, last_30_days, this_month, last_quarter
            sort_by: revenue, bookings, growth, conversion
            limit: max categories
        """
        return await client.category_performance(period=period, sort_by=sort_by, limit=limit)

    async def instainstru_cohort_retention(
        user_type: str,
        cohort_period: str = "month",
        periods_back: int = 6,
        metric: str = "active",
    ) -> dict:
        """
        Retrieve cohort retention analytics.

        Args:
            user_type: student or instructor
            cohort_period: week or month
            periods_back: number of cohorts
            metric: active, booking, revenue
        """
        return await client.cohort_retention(
            user_type=user_type,
            cohort_period=cohort_period,
            periods_back=periods_back,
            metric=metric,
        )

    async def instainstru_platform_alerts(
        severity: str | None = None,
        category: str | None = None,
        acknowledged: bool = False,
    ) -> dict:
        """
        Retrieve active platform alerts.

        Args:
            severity: critical, warning, info
            category: revenue, operations, quality, technical
            acknowledged: include acknowledged alerts
        """
        return await client.platform_alerts(
            severity=severity,
            category=category,
            acknowledged=acknowledged,
        )

    mcp.tool()(instainstru_revenue_dashboard)
    mcp.tool()(instainstru_booking_funnel)
    mcp.tool()(instainstru_funnel_snapshot)
    mcp.tool()(instainstru_supply_demand)
    mcp.tool()(instainstru_category_performance)
    mcp.tool()(instainstru_cohort_retention)
    mcp.tool()(instainstru_platform_alerts)

    return {
        "instainstru_revenue_dashboard": instainstru_revenue_dashboard,
        "instainstru_booking_funnel": instainstru_booking_funnel,
        "instainstru_funnel_snapshot": instainstru_funnel_snapshot,
        "instainstru_supply_demand": instainstru_supply_demand,
        "instainstru_category_performance": instainstru_category_performance,
        "instainstru_cohort_retention": instainstru_cohort_retention,
        "instainstru_platform_alerts": instainstru_platform_alerts,
    }
