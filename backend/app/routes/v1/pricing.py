"""V1 Pricing preview endpoint for booking totals."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from ...api.dependencies import get_current_active_user
from ...api.dependencies.services import get_pricing_service
from ...core.exceptions import DomainException
from ...models.user import User
from ...schemas.pricing_preview import PricingPreviewData, PricingPreviewIn, PricingPreviewOut
from ...services.pricing_service import PricingService

logger = logging.getLogger(__name__)

# V1 router - mounted at /api/v1/pricing
router = APIRouter(tags=["pricing"])


@router.post("/preview", response_model=PricingPreviewOut)
def preview_selection_pricing(
    payload: PricingPreviewIn,
    current_user: User = Depends(get_current_active_user),
    pricing_service: PricingService = Depends(get_pricing_service),
) -> PricingPreviewOut:
    """Return pricing preview for a booking selection without a persisted draft."""

    try:
        pricing_data: PricingPreviewData = pricing_service.compute_quote_pricing(
            payload=payload,
            student_id=current_user.id,
        )
    except DomainException as exc:
        raise exc.to_http_exception() from exc

    return PricingPreviewOut(**pricing_data)
