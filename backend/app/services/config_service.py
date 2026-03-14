"""Service helpers for platform configuration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from app.constants.booking_rules_defaults import BOOKING_RULES_DEFAULTS
from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.repositories.platform_config_repository import PlatformConfigRepository
from app.schemas.booking_rules_config import BookingRulesConfig
from app.schemas.pricing_config import PricingConfig
from app.services.base import BaseService

DEFAULT_LOCATION_TYPE = "online"
INSTRUCTOR_TRAVEL_LOCATION_TYPES = frozenset({"student_location", "neutral_location"})
STUDENT_TRAVEL_LOCATION_TYPES = frozenset({"instructor_location", "neutral_location"})
STUDIO_LOCATION_TYPES = frozenset({"instructor_location"})
VALID_LOCATION_TYPES = frozenset(
    INSTRUCTOR_TRAVEL_LOCATION_TYPES | STUDENT_TRAVEL_LOCATION_TYPES | {DEFAULT_LOCATION_TYPE}
)


def is_hour_in_window(hour: int, start_hour: int, end_hour: int) -> bool:
    """Return whether an hour falls inside a possibly overnight window."""
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def normalize_location_type(location_type: str | None) -> str:
    """Normalize booking location types and fall back to online."""
    normalized = (location_type or DEFAULT_LOCATION_TYPE).strip().lower()
    if normalized in VALID_LOCATION_TYPES:
        return normalized
    return DEFAULT_LOCATION_TYPE


def is_instructor_travel_format(location_type: str | None) -> bool:
    """Return whether the instructor must travel for this booking format."""
    return normalize_location_type(location_type) in INSTRUCTOR_TRAVEL_LOCATION_TYPES


def is_student_travel_format(location_type: str | None) -> bool:
    """Return whether the student must travel for this booking format."""
    return normalize_location_type(location_type) in STUDENT_TRAVEL_LOCATION_TYPES


DEFAULT_PRICING_CONFIG: Dict[str, Any] = PricingConfig(
    **PRICING_DEFAULTS,
).model_dump()
DEFAULT_BOOKING_RULES_CONFIG: Dict[str, Any] = BookingRulesConfig(
    **BOOKING_RULES_DEFAULTS,
).model_dump()


class ConfigService(BaseService):
    """Business logic for reading/writing platform configuration."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.repo = PlatformConfigRepository(db)

    @staticmethod
    def _get_booking_rules_int(config: Dict[str, Any], key: str) -> int:
        value = config.get(key)
        return int(value) if value is not None else int(DEFAULT_BOOKING_RULES_CONFIG[key])

    @classmethod
    def _resolve_advance_notice_minutes_from_config(
        cls, config: Dict[str, Any], location_type: str | None = None
    ) -> int:
        normalized_location = normalize_location_type(location_type)
        if normalized_location in INSTRUCTOR_TRAVEL_LOCATION_TYPES:
            key = "advance_notice_travel_minutes"
        elif normalized_location in STUDIO_LOCATION_TYPES:
            key = "advance_notice_studio_minutes"
        else:
            key = "advance_notice_online_minutes"
        return cls._get_booking_rules_int(config, key)

    @classmethod
    def _resolve_overnight_window_hours_from_config(cls, config: Dict[str, Any]) -> tuple[int, int]:
        start_hour = cls._get_booking_rules_int(config, "overnight_protection_window_start_hour")
        end_hour = cls._get_booking_rules_int(config, "overnight_protection_window_end_hour")
        return start_hour, end_hour

    @classmethod
    def _resolve_overnight_earliest_hour_from_config(
        cls, config: Dict[str, Any], location_type: str | None = None
    ) -> int:
        normalized_location = normalize_location_type(location_type)
        if normalized_location in INSTRUCTOR_TRAVEL_LOCATION_TYPES:
            key = "overnight_travel_earliest_hour"
        else:
            key = "overnight_online_earliest_hour"
        return cls._get_booking_rules_int(config, key)

    @classmethod
    def _resolve_default_buffer_minutes_from_config(
        cls, config: Dict[str, Any], location_type: str | None = None
    ) -> int:
        normalized_location = normalize_location_type(location_type)
        if normalized_location in INSTRUCTOR_TRAVEL_LOCATION_TYPES:
            key = "default_travel_buffer_minutes"
        else:
            key = "default_non_travel_buffer_minutes"
        return cls._get_booking_rules_int(config, key)

    @BaseService.measure_operation("get_pricing_config")
    def get_pricing_config(self) -> Tuple[Dict[str, Any], datetime | None]:
        record = self.repo.get_by_key("pricing")
        if record is None or not record.value_json:
            return deepcopy(DEFAULT_PRICING_CONFIG), None
        return deepcopy(record.value_json), record.updated_at

    @BaseService.measure_operation("get_booking_rules_config")
    def get_booking_rules_config(self) -> Tuple[Dict[str, Any], datetime | None]:
        record = self.repo.get_by_key("booking_rules")
        if record is None or not record.value_json:
            return deepcopy(DEFAULT_BOOKING_RULES_CONFIG), None
        validated = BookingRulesConfig(**record.value_json).model_dump()
        return validated, record.updated_at

    @BaseService.measure_operation("set_pricing_config")
    def set_pricing_config(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], datetime]:
        validated = PricingConfig(**payload).model_dump()
        now = datetime.now(timezone.utc)
        with self.transaction():
            record = self.repo.upsert(key="pricing", value=validated, updated_at=now)
        return deepcopy(record.value_json), record.updated_at or now

    @BaseService.measure_operation("get_advance_notice_minutes")
    def get_advance_notice_minutes(self, location_type: str | None = None) -> int:
        config, _updated_at = self.get_booking_rules_config()
        return self._resolve_advance_notice_minutes_from_config(config, location_type)

    @BaseService.measure_operation("get_overnight_window_hours")
    def get_overnight_window_hours(self) -> tuple[int, int]:
        config, _updated_at = self.get_booking_rules_config()
        return self._resolve_overnight_window_hours_from_config(config)

    @BaseService.measure_operation("is_in_overnight_window")
    def is_in_overnight_window(self, local_dt: datetime) -> bool:
        start_hour, end_hour = self.get_overnight_window_hours()
        return is_hour_in_window(local_dt.hour, start_hour, end_hour)

    @BaseService.measure_operation("get_overnight_earliest_hour")
    def get_overnight_earliest_hour(self, location_type: str | None = None) -> int:
        config, _updated_at = self.get_booking_rules_config()
        return self._resolve_overnight_earliest_hour_from_config(config, location_type)

    @BaseService.measure_operation("get_default_buffer_minutes")
    def get_default_buffer_minutes(self, location_type: str | None = None) -> int:
        config, _updated_at = self.get_booking_rules_config()
        return self._resolve_default_buffer_minutes_from_config(config, location_type)
