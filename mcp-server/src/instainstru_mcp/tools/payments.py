"""MCP tools for payment support workflows."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_payment_timeline(
        booking_id: str | None = None,
        user_id: str | None = None,
        since_days: int = 30,
        since_hours: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict:
        """
        Get payment timeline for a booking or user. Returns redacted, support-safe payment details.

        Use this to investigate:
        - "My payment failed"
        - "I was double charged"
        - "Where's my refund?"
        - "Why does it say pending?"

        Args:
            booking_id: Look up payments for a specific booking
            user_id: Look up all payments for a user
            since_days: How far back to look (default 30)
            since_hours: Optional override for the time window in hours
            start_time: Optional start time (ISO 8601) for a custom window
            end_time: Optional end time (ISO 8601) for a custom window

        Returns payment status timeline, amounts, and flags for common issues.
        """
        if (booking_id and user_id) or (not booking_id and not user_id):
            raise ValueError("Provide exactly one of booking_id or user_id")
        if start_time or end_time:
            if not start_time or not end_time:
                raise ValueError("start_time and end_time must be provided together")

        return await client.get_payment_timeline(
            booking_id=booking_id,
            user_id=user_id,
            since_days=since_days,
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
        )

    mcp.tool()(instainstru_payment_timeline)

    return {"instainstru_payment_timeline": instainstru_payment_timeline}
