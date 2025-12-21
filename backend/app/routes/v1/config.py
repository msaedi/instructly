"""V1 Public configuration routes."""

from inspect import isawaitable
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.schemas.platform_config import PlatformFees, PublicConfigResponse
from app.schemas.pricing_config import PricingConfig, PricingConfigResponse
from app.services.config_service import ConfigService

# V1 router - mounted at /api/v1/config
router = APIRouter(tags=["config"])


def _build_platform_fees(config: Dict[str, Any]) -> PlatformFees:
    tiers = config.get("instructor_tiers") or PRICING_DEFAULTS.get("instructor_tiers", [])
    tiers = sorted(tiers, key=lambda tier: tier.get("min", 0))
    default_tiers = PRICING_DEFAULTS.get("instructor_tiers", [])

    def _tier_pct(index: int) -> float:
        fallback = 0.0
        if default_tiers:
            fallback = default_tiers[min(index, len(default_tiers) - 1)].get("pct", 0)
        if index >= len(tiers):
            return float(fallback)
        return float(tiers[index].get("pct", fallback))

    return PlatformFees(
        founding_instructor=float(
            config.get(
                "founding_instructor_rate_pct",
                PRICING_DEFAULTS.get("founding_instructor_rate_pct", 0),
            )
        ),
        tier_1=_tier_pct(0),
        tier_2=_tier_pct(1),
        tier_3=_tier_pct(2),
        student_booking_fee=float(
            config.get("student_fee_pct", PRICING_DEFAULTS.get("student_fee_pct", 0))
        ),
    )


@router.get("/pricing", response_model=PricingConfigResponse)
async def get_public_pricing_config(db: Session = Depends(get_db)) -> PricingConfigResponse:
    """Return the current pricing configuration for client consumption."""

    service = ConfigService(db)
    config_result = service.get_pricing_config()
    if isawaitable(config_result):
        config_dict, updated_at = await config_result
    else:
        config_dict, updated_at = config_result
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)


@router.get("/public", response_model=PublicConfigResponse)
async def get_public_config(db: Session = Depends(get_db)) -> PublicConfigResponse:
    """Return public platform configuration for frontend display."""

    service = ConfigService(db)
    config_result = service.get_pricing_config()
    if isawaitable(config_result):
        config_dict, updated_at = await config_result
    else:
        config_dict, updated_at = config_result
    fees = _build_platform_fees(config_dict)
    return PublicConfigResponse(fees=fees, updated_at=updated_at)
