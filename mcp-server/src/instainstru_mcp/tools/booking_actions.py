"""MCP tools for booking admin actions."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_booking_force_cancel_preview(
        booking_id: str,
        reason_code: str,
        note: str,
        refund_preference: str = "POLICY_BASED",
    ) -> dict:
        """
        Preview a force-cancel action for a booking.

        Args:
            booking_id: The booking ULID to cancel
            reason_code: ADMIN_DISCRETION, INSTRUCTOR_NO_SHOW, STUDENT_NO_SHOW,
                DUPLICATE_BOOKING, TECHNICAL_ISSUE, DISPUTE_RESOLUTION
            note: Required admin note for audit trail
            refund_preference: FULL_CARD, POLICY_BASED, or NO_REFUND
        """
        return await client.booking_force_cancel_preview(
            booking_id=booking_id,
            reason_code=reason_code,
            note=note,
            refund_preference=refund_preference,
        )

    async def instainstru_booking_force_cancel_execute(
        booking_id: str,
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previously previewed force-cancel.

        Args:
            booking_id: Booking ID from preview
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.booking_force_cancel_execute(
            booking_id=booking_id,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_booking_force_complete_preview(
        booking_id: str,
        reason_code: str,
        note: str,
    ) -> dict:
        """
        Preview a force-complete action for a booking.

        Args:
            booking_id: The booking ULID to complete
            reason_code: LESSON_CONFIRMED_BY_BOTH, INSTRUCTOR_CONFIRMED,
                STUDENT_CONFIRMED, ADMIN_VERIFIED
            note: Required admin note for audit trail
        """
        return await client.booking_force_complete_preview(
            booking_id=booking_id,
            reason_code=reason_code,
            note=note,
        )

    async def instainstru_booking_force_complete_execute(
        booking_id: str,
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previously previewed force-complete.

        Args:
            booking_id: Booking ID from preview
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.booking_force_complete_execute(
            booking_id=booking_id,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_booking_resend_notification(
        booking_id: str,
        notification_type: str,
        note: str,
        recipient: str = "student",
    ) -> dict:
        """
        Resend a booking notification.

        Args:
            booking_id: The booking ULID
            notification_type: booking_confirmation, lesson_reminder_24h,
                lesson_reminder_1h, lesson_completed, cancellation_notice
            recipient: student, instructor, or both
            note: Required admin note for audit trail
        """
        return await client.booking_resend_notification(
            booking_id=booking_id,
            notification_type=notification_type,
            recipient=recipient,
            note=note,
        )

    async def instainstru_booking_add_note(
        booking_id: str,
        note: str,
        visibility: str = "internal",
        category: str = "general",
    ) -> dict:
        """
        Add an internal admin note to a booking.

        Args:
            booking_id: The booking ULID
            note: The note content (max 2000 chars)
            visibility: internal, shared_with_instructor, shared_with_student
            category: support_interaction, dispute, fraud_flag, quality_issue, general
        """
        return await client.booking_add_note(
            booking_id=booking_id,
            note=note,
            visibility=visibility,
            category=category,
        )

    mcp.tool()(instainstru_booking_force_cancel_preview)
    mcp.tool()(instainstru_booking_force_cancel_execute)
    mcp.tool()(instainstru_booking_force_complete_preview)
    mcp.tool()(instainstru_booking_force_complete_execute)
    mcp.tool()(instainstru_booking_resend_notification)
    mcp.tool()(instainstru_booking_add_note)

    return {
        "instainstru_booking_force_cancel_preview": instainstru_booking_force_cancel_preview,
        "instainstru_booking_force_cancel_execute": instainstru_booking_force_cancel_execute,
        "instainstru_booking_force_complete_preview": instainstru_booking_force_complete_preview,
        "instainstru_booking_force_complete_execute": instainstru_booking_force_complete_execute,
        "instainstru_booking_resend_notification": instainstru_booking_resend_notification,
        "instainstru_booking_add_note": instainstru_booking_add_note,
    }
