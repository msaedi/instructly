"""MCP tools for payment support workflows."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_payment_timeline(
        booking_id: str | None = None,
        user_id: str | None = None,
        email: str | None = None,
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
            user_id: Look up all payments for a user (by ID)
            email: Look up all payments for a user (by email) - resolves to user_id
            since_days: How far back to look (default 30)
            since_hours: Optional override for the time window in hours
            start_time: Optional start time (ISO 8601) for a custom window
            end_time: Optional end time (ISO 8601) for a custom window

        Returns payment status timeline, amounts, and flags for common issues.
        """
        provided = [value for value in (booking_id, user_id, email) if value]
        if len(provided) != 1:
            raise ValueError("Provide exactly one of booking_id, user_id, or email")
        if start_time or end_time:
            if not start_time or not end_time:
                raise ValueError("start_time and end_time must be provided together")

        resolved_user = None
        if email:
            lookup = await client.lookup_user(identifier=email)
            if not lookup.get("found") or not lookup.get("user"):
                return {
                    "error": "user_not_found",
                    "message": f"No user found with email: {email}",
                }
            resolved_user = lookup["user"]
            user_id = resolved_user.get("user_id") or resolved_user.get("id")

        response = await client.get_payment_timeline(
            booking_id=booking_id,
            user_id=user_id,
            since_days=since_days,
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
        )
        if resolved_user:
            meta = response.get("meta", {})
            meta["resolved_user"] = {
                "id": resolved_user.get("user_id") or resolved_user.get("id"),
                "email_provided": email,
                "name": resolved_user.get("name"),
            }
            response["meta"] = meta
        return response

    mcp.tool()(instainstru_payment_timeline)

    return {"instainstru_payment_timeline": instainstru_payment_timeline}
