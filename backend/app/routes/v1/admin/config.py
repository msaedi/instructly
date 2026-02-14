# backend/app/routes/v1/admin/config.py
"""Admin configuration routes (v1)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.dependencies.authz import requires_roles
from app.api.dependencies.database import get_db
from app.schemas.pricing_config import PricingConfig, PricingConfigPayload, PricingConfigResponse
from app.services.config_service import ConfigService

router = APIRouter(tags=["admin-config"])


@router.get("/pricing", response_model=PricingConfigResponse)
@requires_roles("admin")
async def get_pricing_config(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> PricingConfigResponse:
    service = ConfigService(db)
    config_dict, updated_at = service.get_pricing_config()
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)


@router.patch("/pricing", response_model=PricingConfigResponse)
@requires_roles("admin")
async def update_pricing_config(
    payload: PricingConfigPayload,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> PricingConfigResponse:
    service = ConfigService(db)
    config_dict, updated_at = service.set_pricing_config(payload.model_dump())
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)
