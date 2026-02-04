"""MCP tools for instructor admin actions."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_instructor_suspend_preview(
        instructor_id: str,
        reason_code: str,
        note: str,
        notify_instructor: bool = True,
        cancel_pending_bookings: bool = True,
    ) -> dict:
        """
        Preview suspending an instructor account.

        Args:
            instructor_id: Instructor user ID
            reason_code: FRAUD, POLICY_VIOLATION, SAFETY_CONCERN, QUALITY_ISSUES,
                BGC_FAILURE, PAYMENT_FRAUD, IDENTITY_MISMATCH, TEMPORARY_REVIEW
            note: Required admin note for audit trail
            notify_instructor: Whether to notify the instructor
            cancel_pending_bookings: Whether to cancel pending bookings
        """
        return await client.instructor_suspend_preview(
            instructor_id=instructor_id,
            reason_code=reason_code,
            note=note,
            notify_instructor=notify_instructor,
            cancel_pending_bookings=cancel_pending_bookings,
        )

    async def instainstru_instructor_suspend_execute(
        instructor_id: str,
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previously previewed instructor suspension.

        Args:
            instructor_id: Instructor user ID from preview
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.instructor_suspend_execute(
            instructor_id=instructor_id,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_instructor_unsuspend(
        instructor_id: str,
        reason: str,
        restore_visibility: bool = True,
    ) -> dict:
        """
        Unsuspend an instructor account.

        Args:
            instructor_id: Instructor user ID
            reason: Required admin reason for audit trail
            restore_visibility: Whether to re-enable search visibility
        """
        return await client.instructor_unsuspend(
            instructor_id=instructor_id,
            reason=reason,
            restore_visibility=restore_visibility,
        )

    async def instainstru_instructor_verify_override(
        instructor_id: str,
        verification_type: str,
        reason: str,
        evidence: str | None = None,
    ) -> dict:
        """
        Manually override instructor verification status.

        Args:
            instructor_id: Instructor user ID
            verification_type: IDENTITY, BACKGROUND_CHECK, PAYMENT_SETUP, FULL
            reason: Required admin reason
            evidence: Optional supporting evidence link
        """
        return await client.instructor_verify_override(
            instructor_id=instructor_id,
            verification_type=verification_type,
            reason=reason,
            evidence=evidence,
        )

    async def instainstru_instructor_update_commission_preview(
        instructor_id: str,
        action: str,
        reason: str,
        tier: str | None = None,
        temporary_rate: float | None = None,
        temporary_until: str | None = None,
    ) -> dict:
        """
        Preview an instructor commission change.

        Args:
            instructor_id: Instructor user ID
            action: SET_TIER, GRANT_FOUNDING, REVOKE_FOUNDING, TEMPORARY_DISCOUNT
            reason: Required admin reason
            tier: entry, growth, pro, founding (for SET_TIER)
            temporary_rate: Temporary commission rate (for TEMPORARY_DISCOUNT)
            temporary_until: ISO timestamp for temporary discount expiry
        """
        return await client.instructor_update_commission_preview(
            instructor_id=instructor_id,
            action=action,
            reason=reason,
            tier=tier,
            temporary_rate=temporary_rate,
            temporary_until=temporary_until,
        )

    async def instainstru_instructor_update_commission_execute(
        instructor_id: str,
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previously previewed commission change.

        Args:
            instructor_id: Instructor user ID from preview
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.instructor_update_commission_execute(
            instructor_id=instructor_id,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_instructor_payout_hold(
        instructor_id: str,
        action: str,
        reason: str,
    ) -> dict:
        """
        Hold or release instructor payouts.

        Args:
            instructor_id: Instructor user ID
            action: HOLD or RELEASE
            reason: Required admin reason
        """
        return await client.instructor_payout_hold(
            instructor_id=instructor_id,
            action=action,
            reason=reason,
        )

    mcp.tool()(instainstru_instructor_suspend_preview)
    mcp.tool()(instainstru_instructor_suspend_execute)
    mcp.tool()(instainstru_instructor_unsuspend)
    mcp.tool()(instainstru_instructor_verify_override)
    mcp.tool()(instainstru_instructor_update_commission_preview)
    mcp.tool()(instainstru_instructor_update_commission_execute)
    mcp.tool()(instainstru_instructor_payout_hold)

    return {
        "instainstru_instructor_suspend_preview": instainstru_instructor_suspend_preview,
        "instainstru_instructor_suspend_execute": instainstru_instructor_suspend_execute,
        "instainstru_instructor_unsuspend": instainstru_instructor_unsuspend,
        "instainstru_instructor_verify_override": instainstru_instructor_verify_override,
        "instainstru_instructor_update_commission_preview": instainstru_instructor_update_commission_preview,
        "instainstru_instructor_update_commission_execute": instainstru_instructor_update_commission_execute,
        "instainstru_instructor_payout_hold": instainstru_instructor_payout_hold,
    }
