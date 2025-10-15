"""Repository for platform configuration records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional, cast

from sqlalchemy.orm import Session

from app.models.platform_config import PlatformConfig


class PlatformConfigRepository:
    """Data access helper for platform configuration key/value records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_key(self, key: str) -> Optional[PlatformConfig]:
        result = self.db.query(PlatformConfig).filter(PlatformConfig.key == key).first()
        return cast(Optional[PlatformConfig], result)

    def upsert(self, *, key: str, value: Mapping[str, Any], updated_at: datetime) -> PlatformConfig:
        record = self.get_by_key(key)
        if record is None:
            record = PlatformConfig(key=key, value_json=dict(value), updated_at=updated_at)
            self.db.add(record)
        else:
            record.value_json = dict(value)
            record.updated_at = updated_at
        self.db.flush()
        return record


__all__ = ["PlatformConfigRepository"]
