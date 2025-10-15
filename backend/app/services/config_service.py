"""Service helpers for platform configuration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from app.repositories.platform_config_repository import PlatformConfigRepository
from app.schemas.pricing_config import PricingConfig

DEFAULT_PRICING_CONFIG: Dict[str, Any] = PricingConfig(
    student_fee_pct=0.12,
    instructor_tiers=[
        {"min": 1, "max": 4, "pct": 0.15},
        {"min": 5, "max": 10, "pct": 0.12},
        {"min": 11, "max": None, "pct": 0.10},
    ],
    tier_activity_window_days=30,
    tier_stepdown_max=1,
    tier_inactivity_reset_days=90,
    price_floor_cents={"private_in_person": 8000, "private_remote": 6000},
    student_credit_cycle={
        "cycle_len": 11,
        "mod10": 5,
        "cents10": 1000,
        "mod20": 0,
        "cents20": 2000,
    },
).model_dump()


class ConfigService:
    """Business logic for reading/writing platform configuration."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PlatformConfigRepository(db)

    def get_pricing_config(self) -> Tuple[Dict[str, Any], datetime | None]:
        record = self.repo.get_by_key("pricing")
        if record is None or not record.value_json:
            return deepcopy(DEFAULT_PRICING_CONFIG), None
        return deepcopy(record.value_json), record.updated_at

    def set_pricing_config(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], datetime]:
        validated = PricingConfig(**payload).model_dump()
        now = datetime.now(timezone.utc)
        record = self.repo.upsert(key="pricing", value=validated, updated_at=now)
        return deepcopy(record.value_json), record.updated_at or now
