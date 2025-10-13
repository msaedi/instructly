"""Public pricing configuration routes."""

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
    config_dict, updated_at = service.get_pricing_config()
    config = PricingConfig(**config_dict)
    return PricingConfigResponse(config=config, updated_at=updated_at)
