"""MCP tools for student admin actions."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_student_suspend_preview(
        student_id: str,
        reason_code: str,
        note: str,
        notify_student: bool = True,
        cancel_pending_bookings: bool = True,
        forfeit_credits: bool = False,
    ) -> dict:
        """
        Preview suspending a student account.

        Args:
            student_id: Student user ID
            reason_code: FRAUD, ABUSE, PAYMENT_FRAUD, POLICY_VIOLATION,
                MULTIPLE_NO_SHOWS, HARASSMENT
            note: Required admin note for audit trail
            notify_student: Whether to notify the student
            cancel_pending_bookings: Whether to cancel pending bookings
            forfeit_credits: Whether to forfeit available credits
        """
        return await client.student_suspend_preview(
            student_id=student_id,
            reason_code=reason_code,
            note=note,
            notify_student=notify_student,
            cancel_pending_bookings=cancel_pending_bookings,
            forfeit_credits=forfeit_credits,
        )

    async def instainstru_student_suspend_execute(
        student_id: str,
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previously previewed student suspension.

        Args:
            student_id: Student user ID from preview
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.student_suspend_execute(
            student_id=student_id,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_student_unsuspend(
        student_id: str,
        reason: str,
        restore_credits: bool = True,
    ) -> dict:
        """
        Unsuspend a student account.

        Args:
            student_id: Student user ID
            reason: Required admin reason for audit trail
            restore_credits: Whether to restore forfeited credits
        """
        return await client.student_unsuspend(
            student_id=student_id,
            reason=reason,
            restore_credits=restore_credits,
        )

    async def instainstru_student_credit_adjust_preview(
        student_id: str,
        action: str,
        amount: float,
        reason_code: str,
        note: str | None = None,
        expires_at: str | None = None,
    ) -> dict:
        """
        Preview a student credit adjustment.

        Args:
            student_id: Student user ID
            action: ADD, REMOVE, SET
            amount: Credit amount in dollars
            reason_code: GOODWILL, COMPENSATION, PROMOTIONAL, CORRECTION, REFERRAL_BONUS,
                REFUND_CONVERSION, FRAUD_RECOVERY
            note: Optional admin note
            expires_at: Optional ISO timestamp for credit expiry
        """
        return await client.student_credit_adjust_preview(
            student_id=student_id,
            action=action,
            amount=amount,
            reason_code=reason_code,
            note=note,
            expires_at=expires_at,
        )

    async def instainstru_student_credit_adjust_execute(
        student_id: str,
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previously previewed credit adjustment.

        Args:
            student_id: Student user ID from preview
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.student_credit_adjust_execute(
            student_id=student_id,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_student_credit_history(
        student_id: str,
        include_expired: bool = True,
    ) -> dict:
        """
        Get student credit history.

        Args:
            student_id: Student user ID
            include_expired: Whether to include expired credits
        """
        return await client.student_credit_history(
            student_id=student_id,
            include_expired=include_expired,
        )

    async def instainstru_student_refund_history(
        student_id: str,
    ) -> dict:
        """
        Get student refund history.

        Args:
            student_id: Student user ID
        """
        return await client.student_refund_history(student_id=student_id)

    mcp.tool()(instainstru_student_suspend_preview)
    mcp.tool()(instainstru_student_suspend_execute)
    mcp.tool()(instainstru_student_unsuspend)
    mcp.tool()(instainstru_student_credit_adjust_preview)
    mcp.tool()(instainstru_student_credit_adjust_execute)
    mcp.tool()(instainstru_student_credit_history)
    mcp.tool()(instainstru_student_refund_history)

    return {
        "instainstru_student_suspend_preview": instainstru_student_suspend_preview,
        "instainstru_student_suspend_execute": instainstru_student_suspend_execute,
        "instainstru_student_unsuspend": instainstru_student_unsuspend,
        "instainstru_student_credit_adjust_preview": instainstru_student_credit_adjust_preview,
        "instainstru_student_credit_adjust_execute": instainstru_student_credit_adjust_execute,
        "instainstru_student_credit_history": instainstru_student_credit_history,
        "instainstru_student_refund_history": instainstru_student_refund_history,
    }
