"""MCP tool for support booking detail workflow."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient
from .common import register_backend_tool


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_booking_detail(
        booking_id: str,
        include_messages_summary: bool = False,
        include_webhooks: bool = True,
        include_trace_links: bool = False,
    ) -> dict:
        """
        Single-source-of-truth view of a booking for support investigations.

        Returns booking info, event timeline, payment status, webhooks, and recommended actions.

        Args:
            booking_id: The booking ULID
            include_messages_summary: Include conversation stats (default: False)
            include_webhooks: Include related webhook events (default: True)
            include_trace_links: Include Axiom trace IDs (default: False, future)
        """
        return await client.get_booking_detail(
            booking_id=booking_id,
            include_messages_summary=include_messages_summary,
            include_webhooks=include_webhooks,
            include_trace_links=include_trace_links,
        )

    instainstru_booking_detail = register_backend_tool(
        mcp,
        instainstru_booking_detail,
        error="booking_not_found",
        message="Booking not found.",
        extra={"booking": None},
    )

    return {"instainstru_booking_detail": instainstru_booking_detail}
