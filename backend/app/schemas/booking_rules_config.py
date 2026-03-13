"""Pydantic schemas for booking-rules configuration."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

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
        BOOKING_RULES_DEFAULTS["default_non_travel_buffer_minutes"], ge=0, le=120
    )
    default_travel_buffer_minutes: int = Field(
        BOOKING_RULES_DEFAULTS["default_travel_buffer_minutes"], ge=15, le=120
    )

    @model_validator(mode="after")
    def validate_windows(self) -> "BookingRulesConfig":
        if self.default_travel_buffer_minutes < self.default_non_travel_buffer_minutes:
            raise ValueError("Travel buffer must be greater than or equal to non-travel buffer")
        return self


class BookingRulesConfigResponse(BaseModel):
    config: BookingRulesConfig
    updated_at: datetime | None = None


__all__ = ["BookingRulesConfig", "BookingRulesConfigResponse"]
