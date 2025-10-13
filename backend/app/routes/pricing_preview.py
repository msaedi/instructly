"""Pricing preview endpoint for booking totals."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..api.dependencies import get_current_active_user
from ..api.dependencies.services import get_pricing_service
from ..core.exceptions import DomainException
from ..models.user import User
from ..schemas.pricing_preview import PricingPreviewOut
from ..services.pricing_service import PricingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bookings", tags=["pricing"])


@router.get("/{booking_id}/pricing", response_model=PricingPreviewOut)
def preview_booking_pricing(
    booking_id: str,
    applied_credit_cents: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    pricing_service: PricingService = Depends(get_pricing_service),
) -> PricingPreviewOut:
    """Return a pricing preview for the requested booking."""

    booking = pricing_service.booking_repository.get_by_id(booking_id, load_relationships=False)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    allowed_participants = {booking.student_id, booking.instructor_id}
    if current_user.id not in allowed_participants:
        logger.warning(
            "pricing_preview.forbidden",
            extra={
                "booking_id": booking_id,
                "requested_by": current_user.id,
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        pricing_data = pricing_service.compute_booking_pricing(
            booking_id=booking_id,
            applied_credit_cents=applied_credit_cents,
            persist=False,
        )
    except DomainException as exc:
        raise exc.to_http_exception() from exc

    return PricingPreviewOut(**pricing_data)
