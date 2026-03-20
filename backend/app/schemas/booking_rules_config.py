"""Pydantic schemas for booking-rules configuration."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.constants.booking_rules_defaults import BOOKING_RULES_DEFAULTS


class BookingRulesConfig(BaseModel):
    advance_notice_online_minutes: int = Field(
        BOOKING_RULES_DEFAULTS["advance_notice_online_minutes"], ge=0, le=1440
    )
    advance_notice_studio_minutes: int = Field(
        BOOKING_RULES_DEFAULTS["advance_notice_studio_minutes"], ge=0, le=1440
    )
    advance_notice_travel_minutes: int = Field(
        BOOKING_RULES_DEFAULTS["advance_notice_travel_minutes"], ge=0, le=1440
    )
    overnight_protection_window_start_hour: int = Field(
        BOOKING_RULES_DEFAULTS["overnight_protection_window_start_hour"], ge=0, le=23
    )
    overnight_protection_window_end_hour: int = Field(
        BOOKING_RULES_DEFAULTS["overnight_protection_window_end_hour"], ge=0, le=23
    )
    overnight_online_earliest_hour: int = Field(
        BOOKING_RULES_DEFAULTS["overnight_online_earliest_hour"], ge=0, le=23
    )
    overnight_travel_earliest_hour: int = Field(
        BOOKING_RULES_DEFAULTS["overnight_travel_earliest_hour"], ge=0, le=23
    )
    default_non_travel_buffer_minutes: int = Field(
        BOOKING_RULES_DEFAULTS["default_non_travel_buffer_minutes"], ge=10, le=120
    )
    default_travel_buffer_minutes: int = Field(
        BOOKING_RULES_DEFAULTS["default_travel_buffer_minutes"], ge=30, le=120
    )

    @field_validator("default_travel_buffer_minutes", mode="before")
    @classmethod
    def validate_travel_buffer_relative_minimum(cls, value: object, info: ValidationInfo) -> object:
        non_travel_buffer = info.data.get("default_non_travel_buffer_minutes")
        if not isinstance(non_travel_buffer, int):
            return value

        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, int):
            travel_buffer = value
        elif isinstance(value, str):
            try:
                travel_buffer = int(value)
            except ValueError:
                return value
        else:
            return value

        if travel_buffer < non_travel_buffer:
            raise ValueError("Travel buffer must be at least equal to non-travel buffer")
        return value


class BookingRulesConfigResponse(BaseModel):
    config: BookingRulesConfig
    updated_at: datetime | None = None


__all__ = ["BookingRulesConfig", "BookingRulesConfigResponse"]
