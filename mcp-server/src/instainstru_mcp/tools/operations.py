"""MCP tools for admin operations (bookings, payments, user support)."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    # ==================== Bookings ====================

    async def instainstru_bookings_summary(period: str = "today") -> dict:
        """Get booking summary for a time period.

        Args:
            period: Time period - today, yesterday, this_week, last_7_days, this_month

        Returns booking statistics including:
        - Total bookings count
        - Breakdown by status (confirmed, completed, cancelled)
        - Total revenue in cents
        - Average booking value
        - New vs repeat students
        - Top categories by booking count
        """
        return await client.get_booking_summary(period=period)

    async def instainstru_bookings_recent(
        status: str | None = None,
        limit: int = 20,
        hours: int = 24,
    ) -> dict:
        """Get recent bookings with optional filters.

        Args:
            status: Filter by status - confirmed, completed, cancelled, pending (optional)
            limit: Maximum results to return (1-100, default 20)
            hours: Look back window in hours (1-168/1 week, default 24)

        Returns a list of recent bookings including:
        - Booking ID, status, date/time
        - Student name (privacy-safe: "John S.")
        - Instructor name (privacy-safe: "Sarah C.")
        - Service name and category
        - Total price in cents
        - Location type
        """
        return await client.get_recent_bookings(status=status, limit=limit, hours=hours)

    # ==================== Payments ====================

    async def instainstru_payments_pipeline() -> dict:
        """Get payment pipeline status - authorizations, captures, failures, revenue.

        Returns payment pipeline overview including:
        - Pending authorization count (awaiting T-24hr auth)
        - Authorized count (awaiting lesson completion)
        - Pending capture count (lesson complete, awaiting T+24hr capture)
        - Captured/Failed/Refunded counts (last 7 days)
        - Alerts: overdue authorizations and captures
        - Revenue metrics: total captured, refunded, net
        - Platform fees and instructor payouts
        """
        return await client.get_payment_pipeline()

    async def instainstru_payments_pending_payouts(limit: int = 20) -> dict:
        """Get instructors with pending payouts awaiting transfer.

        Args:
            limit: Maximum results to return (1-100, default 20)

        Returns instructors with pending payouts including:
        - Instructor ID and name (privacy-safe: "Sarah C.")
        - Pending amount in cents
        - Number of completed lessons awaiting payout
        - Oldest pending date
        - Stripe connected status
        - Total pending amount across all instructors
        """
        return await client.get_pending_payouts(limit=limit)

    # ==================== Users ====================

    async def instainstru_users_lookup(identifier: str) -> dict:
        """Look up a user by email, phone number, or user ID.

        Args:
            identifier: Email address, phone number, or user ID (ULID)

        Returns user profile and statistics (for admin support):
        - User ID, email, full name
        - Role (student or instructor)
        - Account creation and last login dates
        - Verification and founding status
        - Total bookings and spending
        - Stripe customer/account IDs
        - For instructors: status, lessons taught, earnings, rating
        """
        return await client.lookup_user(identifier=identifier)

    async def instainstru_users_booking_history(user_id: str, limit: int = 20) -> dict:
        """Get a user's booking history by user ID.

        Args:
            user_id: The user's ID (ULID, 26 characters)
            limit: Maximum results to return (1-100, default 20)

        Returns the user's bookings:
        - As a student: lessons they've booked
        - As an instructor: lessons they've taught
        - Each booking includes: ID, status, date/time, counterparty name,
          service, category, price, location type
        """
        return await client.get_user_booking_history(user_id=user_id, limit=limit)

    # Register all tools
    mcp.tool()(instainstru_bookings_summary)
    mcp.tool()(instainstru_bookings_recent)
    mcp.tool()(instainstru_payments_pipeline)
    mcp.tool()(instainstru_payments_pending_payouts)
    mcp.tool()(instainstru_users_lookup)
    mcp.tool()(instainstru_users_booking_history)

    return {
        "instainstru_bookings_summary": instainstru_bookings_summary,
        "instainstru_bookings_recent": instainstru_bookings_recent,
        "instainstru_payments_pipeline": instainstru_payments_pipeline,
        "instainstru_payments_pending_payouts": instainstru_payments_pending_payouts,
        "instainstru_users_lookup": instainstru_users_lookup,
        "instainstru_users_booking_history": instainstru_users_booking_history,
    }
