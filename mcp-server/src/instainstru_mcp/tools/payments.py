"""MCP tools for payment support workflows."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient
from .common import build_not_found_response, register_backend_tool


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    def _payment_timeline_not_found(
        booking_id: str | None = None,
        user_id: str | None = None,
        email: str | None = None,
        since_days: int = 30,
        since_hours: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        include_capture_schedule: bool = False,
    ) -> dict:
        del since_days, since_hours, start_time, end_time, include_capture_schedule
        if booking_id:
            return build_not_found_response(
                mode="read",
                error="booking_not_found",
                message="Booking not found.",
            )
        if user_id or email:
            return build_not_found_response(
                mode="read",
                error="user_not_found",
                message="User not found.",
            )
        return build_not_found_response(mode="read")

    async def instainstru_payment_timeline(
        booking_id: str | None = None,
        user_id: str | None = None,
        email: str | None = None,
        since_days: int = 30,
        since_hours: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        include_capture_schedule: bool = False,
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
            include_capture_schedule: Include scheduled authorize/capture timestamps

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
                    "found": False,
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
            include_capture_schedule=include_capture_schedule,
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

    instainstru_payment_timeline = register_backend_tool(
        mcp,
        instainstru_payment_timeline,
        on_not_found=_payment_timeline_not_found,
    )

    return {"instainstru_payment_timeline": instainstru_payment_timeline}
