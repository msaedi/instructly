"""Integration tests for PlatformConfigRepository – target L26-27 (CREATE path in upsert)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.repositories.platform_config_repository import PlatformConfigRepository


@pytest.mark.integration
class TestPlatformConfigRepoCoverage:
    """Cover the upsert CREATE path (L26-27) and edge cases."""

    def test_upsert_creates_new_record_when_key_missing(self, db: object) -> None:
        """L26-27: When key doesn't exist, upsert should INSERT a new PlatformConfig."""
        repo = PlatformConfigRepository(db)
        now = datetime.now(timezone.utc)

        result = repo.upsert(key="test_new_key", value={"flag": True}, updated_at=now)
        db.commit()

        assert result is not None
        assert result.key == "test_new_key"
        assert result.value_json == {"flag": True}
        assert result.updated_at == now

    def test_upsert_updates_existing_record(self, db: object) -> None:
        """When key exists, upsert should UPDATE the record."""
        repo = PlatformConfigRepository(db)
        now = datetime.now(timezone.utc)

        # Create
        repo.upsert(key="update_key", value={"v": 1}, updated_at=now)
        db.commit()

        # Update
        later = datetime.now(timezone.utc)
        result = repo.upsert(key="update_key", value={"v": 2}, updated_at=later)
        db.commit()

        assert result.value_json == {"v": 2}
        assert result.updated_at == later

    def test_get_by_key_returns_none_for_missing(self, db: object) -> None:
        repo = PlatformConfigRepository(db)
        assert repo.get_by_key("nonexistent_key_999") is None

    def test_get_by_key_returns_record(self, db: object) -> None:
        repo = PlatformConfigRepository(db)
        now = datetime.now(timezone.utc)
        repo.upsert(key="get_test_key", value={"hello": "world"}, updated_at=now)
        db.commit()

        found = repo.get_by_key("get_test_key")
        assert found is not None
        assert found.value_json == {"hello": "world"}

    def test_upsert_with_empty_value(self, db: object) -> None:
        """Bug hunt: upsert with empty dict should work."""
        repo = PlatformConfigRepository(db)
        now = datetime.now(timezone.utc)

        result = repo.upsert(key="empty_val_key", value={}, updated_at=now)
        db.commit()

        assert result.value_json == {}

    def test_upsert_idempotent_same_value(self, db: object) -> None:
        """Bug hunt: upserting same key+value twice should be idempotent."""
        repo = PlatformConfigRepository(db)
        now = datetime.now(timezone.utc)

        r1 = repo.upsert(key="idempotent_key", value={"x": 1}, updated_at=now)
        db.commit()

        r2 = repo.upsert(key="idempotent_key", value={"x": 1}, updated_at=now)
        db.commit()

        assert r1.key == r2.key
        assert r2.value_json == {"x": 1}
