"""Service helpers for platform configuration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.repositories.platform_config_repository import PlatformConfigRepository
from app.schemas.pricing_config import PricingConfig

DEFAULT_PRICING_CONFIG: Dict[str, Any] = PricingConfig(
    **PRICING_DEFAULTS,
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

    def commit(self) -> None:
        """Commit pending changes to the database."""
        self.db.commit()  # repo-pattern-ignore: Service wrapper for transaction commit

    def rollback(self) -> None:
        """Rollback pending changes."""
        self.db.rollback()  # repo-pattern-ignore: Service wrapper for transaction rollback
