# backend/app/routes/v1/admin/refunds.py
"""Admin refund endpoints (v1)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user, require_admin
from app.api.dependencies.database import get_db
from app.core.booking_lock import booking_lock
from app.core.enums import PermissionName
from app.core.exceptions import ServiceException
from app.dependencies.permissions import require_permission
from app.models.user import User
from app.schemas.admin_refunds import (
    AdminRefundReason,
    AdminRefundRequest,
    AdminRefundResponse,
)
from app.services.admin_refund_service import AdminRefundService
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService

router = APIRouter(tags=["admin-refunds"])

REASON_TO_STRIPE = {
    AdminRefundReason.INSTRUCTOR_NO_SHOW: "requested_by_customer",
    AdminRefundReason.DISPUTE: "duplicate",
    AdminRefundReason.PLATFORM_ERROR: "requested_by_customer",
    AdminRefundReason.OTHER: "requested_by_customer",
}


@router.post(
    "/{booking_id}/refund",
    response_model=AdminRefundResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_permission(PermissionName.MANAGE_FINANCIALS)),
    ],
)
async def admin_refund_booking(
    booking_id: str,
    request: AdminRefundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdminRefundResponse:
    """Issue a refund for a booking (admin only)."""
    refund_service = AdminRefundService(db)

    async with booking_lock(booking_id) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Operation in progress",
            )

        booking = await asyncio.to_thread(refund_service.get_booking, booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        if not booking.payment_intent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking has no payment to refund",
            )

        if (
            booking.refunded_to_card_amount
            and booking.refunded_to_card_amount > 0
            or (booking.settlement_outcome or "")
            in {
                "admin_refund",
                "instructor_cancel_full_refund",
                "instructor_no_show_full_refund",
                "student_wins_dispute_full_refund",
            }
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking already refunded",
            )

        full_amount_cents = await asyncio.to_thread(
            refund_service.resolve_full_refund_cents, booking
        )
        if full_amount_cents <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to determine refundable amount",
            )

        amount_cents = request.amount_cents or full_amount_cents
        if amount_cents > full_amount_cents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Refund amount exceeds original charge ({full_amount_cents} cents)",
            )

        stripe_reason = REASON_TO_STRIPE.get(request.reason, "requested_by_customer")
        amount_key = amount_cents if amount_cents is not None else "full"
        idempotency_key = f"admin_refund_{booking_id}_{amount_key}"

        stripe_service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
        )

        try:
            refund_result = await asyncio.to_thread(
                stripe_service.refund_payment,
                payment_intent_id=booking.payment_intent_id,
                amount_cents=amount_cents,
                reason=stripe_reason,
                reverse_transfer=True,
                idempotency_key=idempotency_key,
            )
        except ServiceException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stripe refund failed",
            ) from exc

        updated_booking = await asyncio.to_thread(
            refund_service.apply_refund_updates,
            booking_id=booking_id,
            reason=request.reason,
            note=request.note,
            amount_cents=amount_cents,
            stripe_reason=stripe_reason,
            refund_id=refund_result.get("refund_id"),
            actor=current_user,
        )
        if not updated_booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found after refund",
            )

        status_value = (
            updated_booking.status.value
            if hasattr(updated_booking.status, "value")
            else str(updated_booking.status)
        )

        return AdminRefundResponse(
            success=True,
            refund_id=refund_result.get("refund_id", ""),
            amount_refunded_cents=refund_result.get("amount_refunded", amount_cents),
            booking_id=updated_booking.id,
            booking_status=status_value,
            message=f"Refund issued: {request.reason.value}",
        )
