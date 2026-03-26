from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

import pytest

from app.models.trusted_device import TrustedDevice
from app.repositories.trusted_device_repository import TrustedDeviceRepository


def _valid_create_kwargs(*, user_id: str) -> dict[str, object]:
    return {
        "user_id": user_id,
        "device_token_hash": "hash_123",
        "device_name": "Chrome on macOS",
        "user_agent": "Mozilla/5.0 Chrome/123.0 Macintosh",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("user_id", 123, "user_id must be a string"),
        ("device_token_hash", 123, "device_token_hash must be a string"),
        ("device_name", 123, "device_name must be a string"),
        ("user_agent", 123, "user_agent must be a string"),
        ("expires_at", "tomorrow", "expires_at must be a datetime"),
    ],
)
def test_create_rejects_invalid_field_types(db, test_student, field: str, value: object, message: str) -> None:
    repo = TrustedDeviceRepository(db)
    kwargs = _valid_create_kwargs(user_id=test_student.id)
    kwargs[field] = value

    with pytest.raises(TypeError, match=re.escape(message)):
        repo.create(**kwargs)


def test_delete_expired_removes_only_expired_rows(db, test_student) -> None:
    repo = TrustedDeviceRepository(db)
    now = datetime.now(timezone.utc)

    expired_kwargs = _valid_create_kwargs(user_id=test_student.id)
    expired_kwargs["device_token_hash"] = "expired_hash"
    expired_kwargs["expires_at"] = now - timedelta(minutes=1)
    active_kwargs = _valid_create_kwargs(user_id=test_student.id)
    active_kwargs["device_token_hash"] = "active_hash"
    active_kwargs["expires_at"] = now + timedelta(days=7)

    expired = repo.create(**expired_kwargs)
    active = repo.create(**active_kwargs)
    expired_id = expired.id
    active_id = active.id
    db.flush()

    deleted = repo.delete_expired(now=now)
    db.expire_all()

    remaining_ids = {
        device.id for device in db.query(TrustedDevice).filter(TrustedDevice.user_id == test_student.id).all()
    }

    assert deleted == 1
    assert expired_id not in remaining_ids
    assert remaining_ids == {active_id}


def test_update_last_used_returns_false_for_missing_device(db, test_student) -> None:
    repo = TrustedDeviceRepository(db)
    trusted_device = repo.create(**_valid_create_kwargs(user_id=test_student.id))
    original_last_used_at = trusted_device.last_used_at

    updated = repo.update_last_used("01ARZ3NDEKTSV4RRFFQ69G5FAV")

    db.refresh(trusted_device)
    assert updated is False
    assert trusted_device.last_used_at == original_last_used_at
