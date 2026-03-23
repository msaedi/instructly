"""Repository for trusted device persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy.orm import Session

from app.models.trusted_device import TrustedDevice

from .base_repository import BaseRepository


class TrustedDeviceRepository(BaseRepository[TrustedDevice]):
    """Data access for server-side trusted-device records."""

    def __init__(self, db: Session):
        super().__init__(db, TrustedDevice)

    def create(self, **kwargs: object) -> TrustedDevice:
        user_id = kwargs.get("user_id")
        device_token_hash = kwargs.get("device_token_hash")
        device_name = kwargs.get("device_name")
        user_agent = kwargs.get("user_agent")
        expires_at = kwargs.get("expires_at")

        if not isinstance(user_id, str):
            raise TypeError("user_id must be a string")
        if not isinstance(device_token_hash, str):
            raise TypeError("device_token_hash must be a string")
        if not isinstance(device_name, str):
            raise TypeError("device_name must be a string")
        if not isinstance(user_agent, str):
            raise TypeError("user_agent must be a string")
        if not isinstance(expires_at, datetime):
            raise TypeError("expires_at must be a datetime")

        now = datetime.now(timezone.utc)
        trusted_device = TrustedDevice(
            user_id=user_id,
            device_token_hash=device_token_hash,
            device_name=device_name,
            user_agent=user_agent,
            last_used_at=now,
            expires_at=expires_at,
        )
        self.db.add(trusted_device)
        self.db.flush()
        return trusted_device

    def find_by_token_hash(self, token_hash: str) -> TrustedDevice | None:
        result = (
            self.db.query(TrustedDevice)
            .filter(TrustedDevice.device_token_hash == token_hash)
            .first()
        )
        return cast(TrustedDevice | None, result)

    def find_by_user(self, user_id: str) -> list[TrustedDevice]:
        rows = (
            self.db.query(TrustedDevice)
            .filter(TrustedDevice.user_id == user_id)
            .order_by(TrustedDevice.last_used_at.desc(), TrustedDevice.created_at.desc())
            .all()
        )
        return cast(list[TrustedDevice], rows)

    def delete_all_for_user(self, user_id: str) -> int:
        deleted = (
            self.db.query(TrustedDevice)
            .filter(TrustedDevice.user_id == user_id)
            .delete(synchronize_session=False)
        )
        self.db.flush()
        return int(deleted)

    def delete_expired(self, *, now: datetime | None = None) -> int:
        cutoff = now or datetime.now(timezone.utc)
        deleted = (
            self.db.query(TrustedDevice)
            .filter(TrustedDevice.expires_at <= cutoff)
            .delete(synchronize_session=False)
        )
        self.db.flush()
        return int(deleted)

    def update_last_used(self, device_id: str, *, used_at: datetime | None = None) -> bool:
        trusted_device = self.get_by_id(device_id, load_relationships=False)
        if trusted_device is None:
            return False
        trusted_device.last_used_at = used_at or datetime.now(timezone.utc)
        self.db.flush()
        return True
