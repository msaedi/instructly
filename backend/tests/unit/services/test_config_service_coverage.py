"""Unit tests for ConfigService coverage."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.config_service import DEFAULT_PRICING_CONFIG, ConfigService


class TestConfigServiceInit:
    """Tests for ConfigService initialization."""

    def test_init_creates_repository(self) -> None:
        """Lines 23-25: ConfigService initializes with repository."""
        db = MagicMock()

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)

            assert service.db == db
            mock_repo_class.assert_called_once_with(db)
            assert service.repo == mock_repo


class TestConfigServiceGetPricingConfig:
    """Tests for get_pricing_config method."""

    def test_get_pricing_config_returns_default_when_no_record(self) -> None:
        """Lines 28-30: Returns default when no record exists."""
        db = MagicMock()

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_key.return_value = None
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            config, updated_at = service.get_pricing_config()

            mock_repo.get_by_key.assert_called_once_with("pricing")
            assert config == DEFAULT_PRICING_CONFIG
            assert updated_at is None

    def test_get_pricing_config_returns_default_when_empty_value(self) -> None:
        """Lines 29: Returns default when record has empty value_json."""
        db = MagicMock()

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = None  # Empty value
            mock_repo.get_by_key.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            config, updated_at = service.get_pricing_config()

            assert config == DEFAULT_PRICING_CONFIG
            assert updated_at is None

    def test_get_pricing_config_returns_stored_config(self) -> None:
        """Line 31: Returns stored config when record exists."""
        db = MagicMock()
        stored_config = {"commission_rate": 0.15, "platform_fee": 2.50}
        record_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = stored_config
            mock_record.updated_at = record_time
            mock_repo.get_by_key.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            config, updated_at = service.get_pricing_config()

            assert config == stored_config
            assert updated_at == record_time


class TestConfigServiceSetPricingConfig:
    """Tests for set_pricing_config method."""

    def test_set_pricing_config_validates_and_stores(self) -> None:
        """Lines 34-37: set_pricing_config validates and stores config."""
        db = MagicMock()

        # Create a valid pricing config payload
        payload = deepcopy(DEFAULT_PRICING_CONFIG)
        payload["commission_rate"] = 0.12

        record_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = payload
            mock_record.updated_at = record_time
            mock_repo.upsert.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            config, updated_at = service.set_pricing_config(payload)

            # Verify upsert was called with validated config
            mock_repo.upsert.assert_called_once()
            call_args = mock_repo.upsert.call_args
            assert call_args.kwargs["key"] == "pricing"
            assert "value" in call_args.kwargs
            assert "updated_at" in call_args.kwargs

            assert config == payload
            assert updated_at == record_time

    def test_set_pricing_config_uses_fallback_timestamp(self) -> None:
        """Line 37: Uses now as fallback when record has no updated_at."""
        db = MagicMock()
        payload = deepcopy(DEFAULT_PRICING_CONFIG)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = payload
            mock_record.updated_at = None  # No timestamp on record
            mock_repo.upsert.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            config, updated_at = service.set_pricing_config(payload)

            # Should return a timestamp even when record has none
            assert updated_at is not None


class TestConfigServiceTransactions:
    """Tests for transaction handling via BaseService.transaction()."""

    def test_set_pricing_config_commits_via_transaction(self) -> None:
        """set_pricing_config commits through self.transaction() context manager."""
        db = MagicMock()
        payload = deepcopy(DEFAULT_PRICING_CONFIG)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = payload
            mock_record.updated_at = datetime.now(timezone.utc)
            mock_repo.upsert.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            service.set_pricing_config(payload)

            # transaction() context manager calls db.commit()
            db.commit.assert_called_once()

    def test_set_pricing_config_rolls_back_on_error(self) -> None:
        """set_pricing_config rolls back through self.transaction() on failure."""
        db = MagicMock()
        payload = deepcopy(DEFAULT_PRICING_CONFIG)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.upsert.side_effect = RuntimeError("boom")
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            with pytest.raises(RuntimeError, match="boom"):
                service.set_pricing_config(payload)

            db.rollback.assert_called_once()
