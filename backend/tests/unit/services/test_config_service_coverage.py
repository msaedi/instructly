"""Unit tests for ConfigService coverage."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.config_service import (
    DEFAULT_BOOKING_RULES_CONFIG,
    DEFAULT_PRICING_CONFIG,
    ConfigService,
)

ORIGINAL_GET_ADVANCE_NOTICE_MINUTES = ConfigService.get_advance_notice_minutes
ORIGINAL_GET_OVERNIGHT_EARLIEST_HOUR = ConfigService.get_overnight_earliest_hour
ORIGINAL_GET_OVERNIGHT_WINDOW_HOURS = ConfigService.get_overnight_window_hours
ORIGINAL_IS_IN_OVERNIGHT_WINDOW = ConfigService.is_in_overnight_window
ORIGINAL_GET_DEFAULT_BUFFER_MINUTES = ConfigService.get_default_buffer_minutes


@pytest.fixture(autouse=True)
def clear_config_service_caches() -> None:
    ConfigService._clear_pricing_cache()
    ConfigService._clear_booking_rules_cache()


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
        stored_config = deepcopy(DEFAULT_PRICING_CONFIG)
        stored_config["student_fee_pct"] = 0.15
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

    def test_get_pricing_config_uses_cache_within_ttl(self) -> None:
        db = MagicMock()
        stored_config = deepcopy(DEFAULT_PRICING_CONFIG)
        stored_config["student_fee_pct"] = 0.15
        record_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = stored_config
            mock_record.updated_at = record_time
            mock_repo.get_by_key.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            with patch("app.services.config_service.time.monotonic", side_effect=[100.0, 120.0]):
                first_config, first_updated_at = service.get_pricing_config()
                first_config["student_fee_pct"] = 0.99
                second_config, second_updated_at = service.get_pricing_config()

            mock_repo.get_by_key.assert_called_once_with("pricing")
            assert first_updated_at == record_time
            assert second_updated_at == record_time
            assert second_config["student_fee_pct"] == 0.15

    def test_get_pricing_config_refreshes_after_ttl(self) -> None:
        db = MagicMock()
        first_config = deepcopy(DEFAULT_PRICING_CONFIG)
        second_config = deepcopy(DEFAULT_PRICING_CONFIG)
        first_config["student_fee_pct"] = 0.15
        second_config["student_fee_pct"] = 0.2
        first_time = datetime.now(timezone.utc)
        second_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            first_record = MagicMock(value_json=first_config, updated_at=first_time)
            second_record = MagicMock(value_json=second_config, updated_at=second_time)
            mock_repo.get_by_key.side_effect = [first_record, second_record]
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            with patch("app.services.config_service.time.monotonic", side_effect=[100.0, 161.0]):
                cached_config, _cached_updated_at = service.get_pricing_config()
                refreshed_config, refreshed_updated_at = service.get_pricing_config()

            assert cached_config["student_fee_pct"] == 0.15
            assert refreshed_config["student_fee_pct"] == 0.2
            assert refreshed_updated_at == second_time
            assert mock_repo.get_by_key.call_count == 2


class TestConfigServiceSetPricingConfig:
    """Tests for set_pricing_config method."""

    def test_set_pricing_config_validates_and_stores(self) -> None:
        """Lines 34-37: set_pricing_config validates and stores config."""
        db = MagicMock()

        # Create a valid pricing config payload
        payload = deepcopy(DEFAULT_PRICING_CONFIG)
        payload["student_fee_pct"] = 0.12

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

    def test_set_pricing_config_updates_cache(self) -> None:
        db = MagicMock()
        payload = deepcopy(DEFAULT_PRICING_CONFIG)
        payload["student_fee_pct"] = 0.12
        record_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = payload
            mock_record.updated_at = record_time
            mock_repo.upsert.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            mock_repo.get_by_key.reset_mock()
            with patch("app.services.config_service.time.monotonic", side_effect=[100.0, 120.0]):
                stored_config, stored_updated_at = service.set_pricing_config(payload)
                cached_config, cached_updated_at = service.get_pricing_config()

            assert stored_config == payload
            assert stored_updated_at == record_time
            assert cached_config == payload
            assert cached_updated_at == record_time
            mock_repo.get_by_key.assert_not_called()


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


class TestConfigServiceBookingRules:
    """Tests for booking rules config support."""

    def test_get_booking_rules_config_returns_default_when_no_record(self) -> None:
        db = MagicMock()

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_key.return_value = None
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            config, updated_at = service.get_booking_rules_config()

            mock_repo.get_by_key.assert_called_once_with("booking_rules")
            assert config == DEFAULT_BOOKING_RULES_CONFIG
            assert updated_at is None

    def test_get_booking_rules_config_returns_stored_config(self) -> None:
        db = MagicMock()
        stored_config = deepcopy(DEFAULT_BOOKING_RULES_CONFIG)
        stored_config["advance_notice_travel_minutes"] = 240
        record_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = stored_config
            mock_record.updated_at = record_time
            mock_repo.get_by_key.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            config, updated_at = service.get_booking_rules_config()

            assert config == stored_config
            assert updated_at == record_time

    def test_get_booking_rules_config_uses_cache_within_ttl(self) -> None:
        db = MagicMock()
        stored_config = deepcopy(DEFAULT_BOOKING_RULES_CONFIG)
        stored_config["advance_notice_travel_minutes"] = 240
        record_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_record = MagicMock()
            mock_record.value_json = stored_config
            mock_record.updated_at = record_time
            mock_repo.get_by_key.return_value = mock_record
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            with patch("app.services.config_service.time.monotonic", side_effect=[100.0, 120.0]):
                first_config, first_updated_at = service.get_booking_rules_config()
                first_config["advance_notice_travel_minutes"] = 999
                second_config, second_updated_at = service.get_booking_rules_config()

            mock_repo.get_by_key.assert_called_once_with("booking_rules")
            assert first_updated_at == record_time
            assert second_updated_at == record_time
            assert second_config["advance_notice_travel_minutes"] == 240

    def test_get_booking_rules_config_refreshes_after_ttl(self) -> None:
        db = MagicMock()
        first_config = deepcopy(DEFAULT_BOOKING_RULES_CONFIG)
        second_config = deepcopy(DEFAULT_BOOKING_RULES_CONFIG)
        first_config["advance_notice_travel_minutes"] = 180
        second_config["advance_notice_travel_minutes"] = 300
        first_time = datetime.now(timezone.utc)
        second_time = datetime.now(timezone.utc)

        with patch("app.services.config_service.PlatformConfigRepository") as mock_repo_class:
            mock_repo = MagicMock()
            first_record = MagicMock(value_json=first_config, updated_at=first_time)
            second_record = MagicMock(value_json=second_config, updated_at=second_time)
            mock_repo.get_by_key.side_effect = [first_record, second_record]
            mock_repo_class.return_value = mock_repo

            service = ConfigService(db)
            with patch("app.services.config_service.time.monotonic", side_effect=[100.0, 161.0]):
                cached_config, _cached_updated_at = service.get_booking_rules_config()
                refreshed_config, refreshed_updated_at = service.get_booking_rules_config()

            assert cached_config["advance_notice_travel_minutes"] == 180
            assert refreshed_config["advance_notice_travel_minutes"] == 300
            assert refreshed_updated_at == second_time
            assert mock_repo.get_by_key.call_count == 2

    @pytest.mark.parametrize(
        ("location_type", "expected_minutes"),
        [
            ("online", 60),
            ("instructor_location", 60),
            ("student_location", 180),
            ("neutral_location", 180),
            (None, 60),
        ],
    )
    def test_get_advance_notice_minutes_uses_location_mapping(
        self, location_type: str | None, expected_minutes: int
    ) -> None:
        db = MagicMock()

        with patch.object(
            ConfigService,
            "get_booking_rules_config",
            return_value=(deepcopy(DEFAULT_BOOKING_RULES_CONFIG), None),
        ), patch.object(
            ConfigService,
            "get_advance_notice_minutes",
            ORIGINAL_GET_ADVANCE_NOTICE_MINUTES,
        ):
            service = ConfigService(db)
            assert service.get_advance_notice_minutes(location_type) == expected_minutes

    @pytest.mark.parametrize(
        ("location_type", "expected_minutes"),
        [
            ("online", 15),
            ("instructor_location", 15),
            ("student_location", 60),
            ("neutral_location", 60),
            (None, 15),
        ],
    )
    def test_get_default_buffer_minutes_uses_location_mapping(
        self, location_type: str | None, expected_minutes: int
    ) -> None:
        db = MagicMock()

        with patch.object(
            ConfigService,
            "get_booking_rules_config",
            return_value=(deepcopy(DEFAULT_BOOKING_RULES_CONFIG), None),
        ), patch.object(
            ConfigService,
            "get_default_buffer_minutes",
            ORIGINAL_GET_DEFAULT_BUFFER_MINUTES,
        ):
            service = ConfigService(db)
            assert service.get_default_buffer_minutes(location_type) == expected_minutes

    def test_booking_rule_accessors_fall_back_to_defaults_for_none_values(self) -> None:
        db = MagicMock()
        config_with_nones = deepcopy(DEFAULT_BOOKING_RULES_CONFIG)
        config_with_nones.update(
            {
                "advance_notice_online_minutes": None,
                "default_non_travel_buffer_minutes": None,
                "overnight_online_earliest_hour": None,
                "overnight_protection_window_start_hour": None,
                "overnight_protection_window_end_hour": None,
            }
        )

        with patch.object(
            ConfigService,
            "get_booking_rules_config",
            return_value=(config_with_nones, None),
        ), patch.object(
            ConfigService,
            "get_advance_notice_minutes",
            ORIGINAL_GET_ADVANCE_NOTICE_MINUTES,
        ), patch.object(
            ConfigService,
            "get_default_buffer_minutes",
            ORIGINAL_GET_DEFAULT_BUFFER_MINUTES,
        ), patch.object(
            ConfigService,
            "get_overnight_earliest_hour",
            ORIGINAL_GET_OVERNIGHT_EARLIEST_HOUR,
        ), patch.object(
            ConfigService,
            "get_overnight_window_hours",
            ORIGINAL_GET_OVERNIGHT_WINDOW_HOURS,
        ):
            service = ConfigService(db)
            assert (
                service.get_advance_notice_minutes("online")
                == DEFAULT_BOOKING_RULES_CONFIG["advance_notice_online_minutes"]
            )
            assert (
                service.get_default_buffer_minutes("online")
                == DEFAULT_BOOKING_RULES_CONFIG["default_non_travel_buffer_minutes"]
            )
            assert (
                service.get_overnight_earliest_hour("online")
                == DEFAULT_BOOKING_RULES_CONFIG["overnight_online_earliest_hour"]
            )
            assert service.get_overnight_window_hours() == (
                DEFAULT_BOOKING_RULES_CONFIG["overnight_protection_window_start_hour"],
                DEFAULT_BOOKING_RULES_CONFIG["overnight_protection_window_end_hour"],
            )

    @pytest.mark.parametrize(
        ("location_type", "expected_hour"),
        [
            ("online", 9),
            ("instructor_location", 9),
            ("student_location", 11),
            ("neutral_location", 11),
            (None, 9),
        ],
    )
    def test_get_overnight_earliest_hour_uses_location_mapping(
        self, location_type: str | None, expected_hour: int
    ) -> None:
        db = MagicMock()

        with patch.object(
            ConfigService,
            "get_booking_rules_config",
            return_value=(deepcopy(DEFAULT_BOOKING_RULES_CONFIG), None),
        ), patch.object(
            ConfigService,
            "get_overnight_earliest_hour",
            ORIGINAL_GET_OVERNIGHT_EARLIEST_HOUR,
        ):
            service = ConfigService(db)
            assert service.get_overnight_earliest_hour(location_type) == expected_hour

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            (datetime(2030, 1, 1, 19, 59, tzinfo=timezone.utc), False),
            (datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc), True),
            (datetime(2030, 1, 2, 7, 59, tzinfo=timezone.utc), True),
            (datetime(2030, 1, 2, 8, 0, tzinfo=timezone.utc), False),
        ],
    )
    def test_is_in_overnight_window_uses_wrapping_hours(
        self, target: datetime, expected: bool
    ) -> None:
        db = MagicMock()

        with patch.object(
            ConfigService,
            "get_overnight_window_hours",
            ORIGINAL_GET_OVERNIGHT_WINDOW_HOURS,
        ), patch.object(
            ConfigService,
            "get_booking_rules_config",
            return_value=(deepcopy(DEFAULT_BOOKING_RULES_CONFIG), None),
        ), patch.object(
            ConfigService,
            "is_in_overnight_window",
            ORIGINAL_IS_IN_OVERNIGHT_WINDOW,
        ):
            service = ConfigService(db)
            assert service.is_in_overnight_window(target) is expected
