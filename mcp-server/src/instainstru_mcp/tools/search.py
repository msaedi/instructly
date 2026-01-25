"""MCP tools for search analytics."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_search_top_queries(
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
        min_count: int = 2,
    ) -> dict:
        """Get top search queries with conversion metrics."""
        return await client.get_top_queries(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            min_count=min_count,
        )

    async def instainstru_search_zero_results(
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Get zero-result search queries."""
        return await client.get_zero_results(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    mcp.tool()(instainstru_search_top_queries)
    mcp.tool()(instainstru_search_zero_results)

    return {
        "instainstru_search_top_queries": instainstru_search_top_queries,
        "instainstru_search_zero_results": instainstru_search_zero_results,
    }
