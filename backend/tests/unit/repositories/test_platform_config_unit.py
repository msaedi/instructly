"""Unit test for PlatformConfigRepository.upsert CREATE path (L26-27)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.repositories.platform_config_repository import PlatformConfigRepository


@pytest.mark.unit
class TestPlatformConfigUpsertCreate:
    """Exercise the CREATE branch (L26-27) via mock DB session."""

    def test_upsert_create_when_no_record(self) -> None:
        """L26-27: When get_by_key returns None, a new PlatformConfig is created and added."""
        db = MagicMock()
        # get_by_key returns None -> triggers CREATE path
        db.query.return_value.filter.return_value.first.return_value = None

        repo = PlatformConfigRepository(db)
        now = datetime.now(timezone.utc)
        result = repo.upsert(key="new_key", value={"flag": True}, updated_at=now)

        # Verify db.add was called (L27)
        assert db.add.called
        # Verify db.flush was called (L31)
        assert db.flush.called
        # Verify the created record
        assert result.key == "new_key"
        assert result.value_json == {"flag": True}
        assert result.updated_at == now
