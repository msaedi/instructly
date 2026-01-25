"""MCP tools for metrics definitions."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_metrics_describe(metric_name: str) -> dict:
        """Get a metrics dictionary definition."""
        return await client.get_metric(metric_name)

    mcp.tool()(instainstru_metrics_describe)

    return {"instainstru_metrics_describe": instainstru_metrics_describe}
