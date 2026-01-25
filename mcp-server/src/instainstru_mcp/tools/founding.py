"""MCP tools for founding instructor funnel analytics."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_founding_funnel_summary(
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """Get founding instructor funnel summary with stage counts and conversion rates."""
        return await client.get_funnel_summary(start_date=start_date, end_date=end_date)

    async def instainstru_founding_stuck_instructors(
        stuck_days: int = 7,
        stage: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Find instructors stuck in onboarding."""
        return await client.get_stuck_instructors(
            stuck_days=stuck_days, stage=stage, limit=limit
        )

    mcp.tool()(instainstru_founding_funnel_summary)
    mcp.tool()(instainstru_founding_stuck_instructors)

    return {
        "instainstru_founding_funnel_summary": instainstru_founding_funnel_summary,
        "instainstru_founding_stuck_instructors": instainstru_founding_stuck_instructors,
    }
