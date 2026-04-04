"""Shared typing base for availability mixins."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, Iterable

from ..base import BaseService
from .types import (
    DayBitmaps,
    PreparedWeek,
    ProcessedSlot,
    SaveWeekBitsResult,
    SlotSnapshot,
    TimeSlotResponse,
    WeekAvailabilityResult,
)

if TYPE_CHECKING:
    from ...repositories.audit_repository import AuditRepository
    from ...repositories.availability_day_repository import AvailabilityDayRepository
    from ...repositories.availability_repository import AvailabilityRepository
    from ...repositories.booking_repository import BookingRepository
    from ...repositories.conflict_checker_repository import ConflictCheckerRepository
    from ...repositories.event_outbox_repository import EventOutboxRepository
    from ...repositories.instructor_profile_repository import InstructorProfileRepository
    from ..cache_service import CacheServiceSyncAdapter
    from ..config_service import ConfigService


class AvailabilityMixinBase(BaseService):
    """Base class used only to make mixin dependencies visible to static typing."""

    if TYPE_CHECKING:
        cache_service: CacheServiceSyncAdapter | None
        repository: AvailabilityRepository
        booking_repository: BookingRepository
        conflict_repository: ConflictCheckerRepository
        instructor_repository: InstructorProfileRepository
        event_outbox_repository: EventOutboxRepository
        audit_repository: AuditRepository
        config_service: ConfigService | None

        def _bitmap_repo(self) -> AvailabilityDayRepository:
            ...

        def get_week_bits(
            self,
            instructor_id: str,
            week_start: date,
            *,
            use_cache: bool = True,
        ) -> dict[date, bytes]:
            ...

        def get_week_bitmaps(
            self,
            instructor_id: str,
            week_start: date,
            *,
            use_cache: bool = True,
        ) -> dict[date, DayBitmaps]:
            ...

        def get_week_bitmap_last_modified(
            self,
            instructor_id: str,
            week_start: date,
        ) -> datetime | None:
            ...

        def compute_week_version(
            self,
            instructor_id: str,
            start_date: date,
            end_date: date,
            windows: list[tuple[date, time, time]] | None = None,
        ) -> str:
            ...

        def compute_week_version_bitmaps(self, bitmaps_by_day: dict[date, DayBitmaps]) -> str:
            ...

        @staticmethod
        def _normalize_week_windows_for_bits_save(
            raw_windows: Iterable[tuple[str | time, str | time]],
        ) -> list[tuple[str, str]]:
            ...

        def _week_cache_keys(self, instructor_id: str, week_start: date) -> tuple[str, str]:
            ...

        def _extract_cached_week_result(
            self,
            payload: Any,
            *,
            include_slots: bool,
        ) -> WeekAvailabilityResult | None:
            ...

        def _sanitize_week_map(
            self,
            payload: Any,
        ) -> dict[str, list[TimeSlotResponse]] | None:
            ...

        def _persist_week_cache(
            self,
            *,
            instructor_id: str,
            week_start: date,
            week_map: dict[str, list[TimeSlotResponse]],
            cache_keys: tuple[str, str] | None = None,
        ) -> None:
            ...

        def _update_bitmap_caches_after_save(
            self,
            *,
            instructor_id: str,
            monday: date,
            after_map: dict[date, DayBitmaps],
        ) -> None:
            ...

        def _week_map_from_bits(
            self,
            bits_by_day: dict[date, bytes],
            *,
            include_snapshots: bool,
        ) -> tuple[dict[str, list[TimeSlotResponse]], list[SlotSnapshot]]:
            ...

        def _invalidate_availability_caches(self, instructor_id: str, dates: list[date]) -> None:
            ...

        def get_week_availability(
            self,
            instructor_id: str,
            start_date: date,
            *,
            use_cache: bool = True,
            include_empty: bool = False,
        ) -> dict[str, list[TimeSlotResponse]]:
            ...

        def _validate_no_overlaps(
            self,
            instructor_id: str,
            schedule_by_date: dict[date, list[ProcessedSlot]],
            *,
            ignore_existing: bool,
            existing_by_date: dict[date, list[ProcessedSlot]] | None = None,
        ) -> None:
            ...

        def _ensure_valid_interval(self, target_date: date, start: time, end: time) -> None:
            ...

        @staticmethod
        def _minutes_range(start: time, end: time) -> tuple[int, int]:
            ...

        def save_week_bits(
            self,
            instructor_id: str,
            week_start: date,
            windows_by_day: dict[date, list[tuple[str, str]]],
            base_version: str | None,
            override: bool,
            clear_existing: bool,
            *,
            actor: Any | None = None,
        ) -> SaveWeekBitsResult:
            ...

        def _build_bitmap_save_audit_payloads(
            self,
            *,
            week_start: date,
            normalized_current_map: dict[date, DayBitmaps],
            target_map: dict[date, DayBitmaps],
            changed_dates: set[date],
            skipped_window_dates: list[date],
            skipped_forbidden_dates: list[date],
            past_written_dates: set[date],
            audit_dates: list[date],
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            ...

        def _write_availability_audit(
            self,
            instructor_id: str,
            week_start: date,
            action: str,
            *,
            actor: Any | None,
            before: dict[str, Any] | None,
            after: dict[str, Any] | None,
            default_role: str = "instructor",
        ) -> None:
            ...

        def _enqueue_week_save_event(
            self,
            instructor_id: str,
            week_start: date,
            week_dates: list[date],
            prepared: PreparedWeek,
            created_count: int,
            deleted_count: int,
            clear_existing: bool,
        ) -> None:
            ...
