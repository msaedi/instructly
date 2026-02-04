"""MCP tools for guarded refund workflow."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_refund_preview(
        booking_id: str,
        reason_code: str,
        amount_type: str = "full",
        amount_value: float | None = None,
        note: str | None = None,
    ) -> dict:
        """
        Preview a refund to see eligibility, policy basis, and financial impact.

        IMPORTANT: This does NOT execute the refund. Use instainstru_refund_execute
        with the returned confirm_token to actually process the refund.

        Args:
            booking_id: The booking ULID to refund
            reason_code: CANCEL_POLICY, GOODWILL, DUPLICATE, DISPUTE_PREVENTION,
                         INSTRUCTOR_NO_SHOW, SERVICE_ISSUE
            amount_type: "full" or "partial"
            amount_value: Required if amount_type is "partial"
            note: Internal note for audit trail

        Returns:
            eligible: Whether refund is allowed
            policy_basis: Human-readable explanation of refund policy
            impact: Financial breakdown (card refund, credit, instructor delta)
            warnings: Important considerations before proceeding
            confirm_token: Use with refund_execute (expires in 5 minutes)
            idempotency_key: Use with refund_execute
        """
        if amount_type == "partial" and amount_value is None:
            raise ValueError("amount_value is required when amount_type is 'partial'")

        return await client.refund_preview(
            booking_id=booking_id,
            reason_code=reason_code,
            amount_type=amount_type,
            amount_value=amount_value,
            note=note,
        )

    async def instainstru_refund_execute(
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previously previewed refund.

        DANGEROUS: This actually processes the refund and moves money.

        Requirements:
        - Must call instainstru_refund_preview first
        - confirm_token expires after 5 minutes
        - idempotency_key must match the preview

        Args:
            confirm_token: Token from refund_preview response
            idempotency_key: Key from refund_preview response

        Returns:
            result: "success", "failed", or "pending"
            refund: Refund details if successful
            updated_booking: New booking status
            updated_payment: New payment status
            audit_id: Audit trail reference
        """
        return await client.refund_execute(
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    mcp.tool()(instainstru_refund_preview)
    mcp.tool()(instainstru_refund_execute)

    return {
        "instainstru_refund_preview": instainstru_refund_preview,
        "instainstru_refund_execute": instainstru_refund_execute,
    }
