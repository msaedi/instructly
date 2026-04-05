from __future__ import annotations

import os
from typing import Literal, cast

from pydantic import Field, model_validator

from .shared import _classify_site_mode


class AvailabilitySettingsMixin:
    public_availability_days: int = Field(
        default=30,
        description="Maximum number of days to show in public availability",
        ge=1,
        le=90,
    )
    public_availability_detail_level: Literal["full", "summary", "minimal"] = Field(
        default="full", description="Level of detail to show in public availability endpoints"
    )
    public_availability_show_instructor_name: bool = Field(
        default=True, description="Whether to show instructor names in public endpoints"
    )
    public_availability_cache_ttl: int = Field(
        default=300,
        description="Cache TTL in seconds for public availability data",
    )
    past_edit_window_days: int = Field(
        default=0,
        alias="PAST_EDIT_WINDOW_DAYS",
        ge=0,
        description="Maximum number of days in the past that bitmap edits will write; 0 = no limit",
    )
    clamp_copy_to_future: bool = Field(
        default=False,
        alias="CLAMP_COPY_TO_FUTURE",
        description="Skip bitmap apply/copy writes for target dates before today",
    )
    feature_disable_slot_writes: bool = Field(
        default=True,
        alias="FEATURE_DISABLE_SLOT_WRITES",
        description="When true, legacy availability_slots writes are disabled",
    )
    seed_disable_slots: bool = Field(
        default=True,
        alias="SEED_DISABLE_SLOTS",
        description="When true, seed scripts skip inserting availability_slots rows",
    )
    include_empty_days_in_tests: bool = Field(
        default=False,
        alias="INCLUDE_EMPTY_DAYS_IN_TESTS",
        description="When true, weekly availability responses include empty days (test-only helper)",
    )
    instant_deliver_in_tests: bool = Field(
        default=True,
        alias="INSTANT_DELIVER_IN_TESTS",
        description="When true, availability outbox events are marked sent immediately during tests",
    )
    suppress_past_availability_events: bool = Field(
        default=False,
        alias="SUPPRESS_PAST_AVAILABILITY_EVENTS",
        description="When true, availability events with only past dates are suppressed",
    )

    @model_validator(mode="after")
    def _default_bitmap_guardrails(self) -> "AvailabilitySettingsMixin":
        """Apply environment-based defaults for bitmap past-edit guardrails."""

        fields_set = cast(set[str], getattr(self, "model_fields_set", set()))
        normalized_mode, is_prod, is_non_prod = _classify_site_mode(os.environ.get("SITE_MODE"))
        guardrails_enabled = normalized_mode in {
            "prod",
            "production",
            "beta",
            "live",
            "stg",
            "stage",
            "staging",
        }
        if (
            not guardrails_enabled
            and is_non_prod
            and normalized_mode not in {"local", "dev", "development"}
        ):
            guardrails_enabled = normalized_mode not in {"int", "test"}

        if "past_edit_window_days" not in fields_set and "PAST_EDIT_WINDOW_DAYS" not in os.environ:
            self.past_edit_window_days = 30 if guardrails_enabled else 0
        self.past_edit_window_days = max(0, self.past_edit_window_days)

        if "clamp_copy_to_future" not in fields_set and "CLAMP_COPY_TO_FUTURE" not in os.environ:
            self.clamp_copy_to_future = guardrails_enabled

        if (
            "suppress_past_availability_events" not in fields_set
            and "SUPPRESS_PAST_AVAILABILITY_EVENTS" not in os.environ
        ):
            self.suppress_past_availability_events = guardrails_enabled

        return self
