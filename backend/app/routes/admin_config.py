"""Admin configuration routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.api.dependencies.database import get_db
from app.schemas.pricing_config import PricingConfig, PricingConfigPayload, PricingConfigResponse
from app.services.config_service import ConfigService

router = APIRouter(prefix="/api/admin/config", tags=["admin-config"])


@router.get("/pricing", response_model=PricingConfigResponse)
async def get_pricing_config(
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> PricingConfigResponse:
    service = ConfigService(db)
    config_dict, updated_at = service.get_pricing_config()
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)


@router.patch("/pricing", response_model=PricingConfigResponse)
async def update_pricing_config(
    payload: PricingConfigPayload,
    db: Session = Depends(get_db),
    _: object = Depends(require_admin),
) -> PricingConfigResponse:
    try:
        service = ConfigService(db)
        config_dict, updated_at = service.set_pricing_config(payload.model_dump())
        db.commit()
    except Exception:
        db.rollback()
        raise
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)
