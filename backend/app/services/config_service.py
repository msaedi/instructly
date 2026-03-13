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
        normalized_location = normalize_location_type(location_type)
        if normalized_location in INSTRUCTOR_TRAVEL_LOCATION_TYPES:
            key = "advance_notice_travel_minutes"
        elif normalized_location in STUDIO_LOCATION_TYPES:
            key = "advance_notice_studio_minutes"
        else:
            key = "advance_notice_online_minutes"
        return int(config.get(key, DEFAULT_BOOKING_RULES_CONFIG[key]) or 0)

    @BaseService.measure_operation("get_default_buffer_minutes")
    def get_default_buffer_minutes(self, location_type: str | None = None) -> int:
        config, _updated_at = self.get_booking_rules_config()
        normalized_location = normalize_location_type(location_type)
        if normalized_location in INSTRUCTOR_TRAVEL_LOCATION_TYPES:
            key = "default_travel_buffer_minutes"
        else:
            key = "default_non_travel_buffer_minutes"
        return int(config.get(key, DEFAULT_BOOKING_RULES_CONFIG[key]) or 0)
