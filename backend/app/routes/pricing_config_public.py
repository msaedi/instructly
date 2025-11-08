"""Public pricing configuration routes."""

from inspect import isawaitable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.schemas.pricing_config import PricingConfig, PricingConfigResponse
from app.services.config_service import ConfigService

router = APIRouter(prefix="/api/config", tags=["config"])


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
