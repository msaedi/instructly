"""MCP tools for instructor listings and coverage."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_instructors_list(
        status: str | None = None,
        is_founding: bool | None = None,
        service_slug: str | None = None,
        category_name: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """List instructors with optional filters."""
        return await client.list_instructors(
            status=status,
            is_founding=is_founding,
            service_slug=service_slug,
            category_name=category_name,
            limit=limit,
            cursor=cursor,
        )

    async def instainstru_instructors_coverage(
        status: str = "live",
        group_by: str = "category",
        top: int = 25,
    ) -> dict:
        """Get instructor service coverage data."""
        return await client.get_instructor_coverage(status=status, group_by=group_by, top=top)

    async def instainstru_instructors_detail(identifier: str) -> dict:
        """Get full instructor profile details by id/email/name."""
        return await client.get_instructor_detail(identifier)

    mcp.tool()(instainstru_instructors_list)
    mcp.tool()(instainstru_instructors_coverage)
    mcp.tool()(instainstru_instructors_detail)

    return {
        "instainstru_instructors_list": instainstru_instructors_list,
        "instainstru_instructors_coverage": instainstru_instructors_coverage,
        "instainstru_instructors_detail": instainstru_instructors_detail,
    }
