# backend/app/routes/v1/admin/config.py
"""Admin configuration routes (v1)."""

from inspect import isawaitable

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
    config_result = service.get_pricing_config()
    if isawaitable(config_result):
        config_dict, updated_at = await config_result
    else:
        config_dict, updated_at = config_result
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)


@router.patch("/pricing", response_model=PricingConfigResponse)
@requires_roles("admin")
async def update_pricing_config(
    payload: PricingConfigPayload,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> PricingConfigResponse:
    try:
        service = ConfigService(db)
        update_result = service.set_pricing_config(payload.model_dump())
        if isawaitable(update_result):
            config_dict, updated_at = await update_result
        else:
            config_dict, updated_at = update_result
        db.commit()
    except Exception:
        db.rollback()
        raise
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)
