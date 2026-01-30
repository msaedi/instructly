"""MCP tools for Sentry debug validation."""

from __future__ import annotations

from fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> dict[str, object]:
    def instainstru_sentry_debug() -> str:
        """Trigger a test error to verify Sentry integration."""
        raise RuntimeError("Sentry debug endpoint - intentional test error")

    mcp.tool()(instainstru_sentry_debug)

    return {"instainstru_sentry_debug": instainstru_sentry_debug}
