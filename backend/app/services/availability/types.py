"""Availability type definitions, constants, and shared data structures."""

from __future__ import annotations

from datetime import date, datetime, time
import os
from typing import TYPE_CHECKING, Callable, NamedTuple, Optional, Protocol, TypedDict

if TYPE_CHECKING:
    from ...core.config import Settings

AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}
ALLOW_PAST = os.getenv("AVAILABILITY_ALLOW_PAST", "true").lower() in {"1", "true", "yes"}
PERF_DEBUG = os.getenv("AVAILABILITY_PERF_DEBUG", "0").lower() in {"1", "true", "yes"}


def build_availability_idempotency_key(
    instructor_id: str, week_start: date, event_type: str, version: str
) -> str:
    """Compose a deterministic idempotency key for availability events."""
    return f"avail:{instructor_id}:{week_start.isoformat()}:{event_type}:{version}"


class ScheduleSlotInput(TypedDict):
    """Input format for schedule slots from API."""

    date: str
    start_time: str
    end_time: str


class ProcessedSlot(TypedDict):
    """Internal format after processing schedule slots."""

    start_time: time
    end_time: time


class AvailabilityWindowInput(TypedDict):
    """Normalized window ready for persistence (bitmap storage)."""

    instructor_id: str
    specific_date: date
    start_time: time
    end_time: time


class TimeSlotResponse(TypedDict):
    """Response format for time slots."""

    start_time: str
    end_time: str


class SlotSnapshot(NamedTuple):
    specific_date: date
    start_time: time
    end_time: time
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class WeekAvailabilityResult(NamedTuple):
    week_map: dict[str, list[TimeSlotResponse]]
    windows: list[tuple[date, time, time]]


class PreparedWeek(NamedTuple):
    windows: list[AvailabilityWindowInput]
    affected_dates: set[date]


class SaveWeekBitsResult(NamedTuple):
    rows_written: int
    days_written: int
    weeks_affected: int
    windows_created: int
    skipped_past_window: int
    skipped_past_forbidden: int
    bits_by_day: dict[date, bytes]
    version: str
    written_dates: list[date]
    skipped_dates: list[date]
    past_written_dates: list[date]
    edited_dates: list[str]


class DayBitmaps(NamedTuple):
    bits: bytes
    format_tags: bytes


class SaveWeekBitmapsResult(NamedTuple):
    rows_written: int
    days_written: int
    weeks_affected: int
    windows_created: int
    skipped_past_window: int
    skipped_past_forbidden: int
    bitmaps_by_day: dict[date, DayBitmaps]
    version: str
    written_dates: list[date]
    skipped_dates: list[date]
    past_written_dates: list[date]
    edited_dates: list[str]


class AvailabilityServiceModuleProtocol(Protocol):
    """Typed view over the availability_service facade module."""

    ALLOW_PAST: bool
    AUDIT_ENABLED: bool
    PERF_DEBUG: bool
    settings: "Settings"
    get_user_now_by_id: Callable[..., datetime]
    get_user_today_by_id: Callable[..., date]
    invalidate_on_availability_change: Callable[..., None]
    windows_from_bits: Callable[..., list[tuple[str, str]]]


__all__ = [
    "ALLOW_PAST",
    "AUDIT_ENABLED",
    "PERF_DEBUG",
    "AvailabilityWindowInput",
    "DayBitmaps",
    "PreparedWeek",
    "ProcessedSlot",
    "SaveWeekBitsResult",
    "SaveWeekBitmapsResult",
    "ScheduleSlotInput",
    "SlotSnapshot",
    "TimeSlotResponse",
    "WeekAvailabilityResult",
    "availability_service_module",
    "build_availability_idempotency_key",
]


def availability_service_module() -> AvailabilityServiceModuleProtocol:
    """Return the public availability_service facade module for compatibility lookups."""
    from .. import availability_service as availability_service_module

    return availability_service_module
