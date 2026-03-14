"""Default platform configuration for booking rules."""

from __future__ import annotations

from typing import Any, Dict

BOOKING_RULES_DEFAULTS: Dict[str, Any] = {
    "advance_notice_online_minutes": 60,
    "advance_notice_studio_minutes": 60,
    "advance_notice_travel_minutes": 180,
    "overnight_protection_window_start_hour": 20,
    "overnight_protection_window_end_hour": 8,
    "overnight_online_earliest_hour": 9,
    "overnight_travel_earliest_hour": 11,
    "default_non_travel_buffer_minutes": 15,
    "default_travel_buffer_minutes": 60,
}


__all__ = ["BOOKING_RULES_DEFAULTS"]
