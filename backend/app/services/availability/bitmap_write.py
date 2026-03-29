"""Core bitmap persistence for availability week saves."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import logging
from typing import Any, Optional

from ...core.constants import MINUTES_PER_SLOT
from ...core.exceptions import ConflictException
from ...repositories.availability_day_repository import normalize_format_tags
from ...utils.bitset import (
    bits_from_windows,
    new_empty_bits,
    new_empty_tags,
    pack_indexes,
    unpack_indexes,
)
from ...utils.time_utils import time_to_minutes
from ..base import BaseService
from .mixin_base import AvailabilityMixinBase
from .types import (
    DayBitmaps,
    PreparedWeek,
    SaveWeekBitmapsResult,
    SaveWeekBitsResult,
    availability_service_module,
)

logger = logging.getLogger(__name__)


@dataclass
class BitmapDayUpdateResult:
    server_version: str
    normalized_current_map: dict[date, DayBitmaps]
    target_map: dict[date, DayBitmaps]
    updates: list[tuple[date, bytes, bytes]]
    changed_dates: set[date]
    past_written_dates: set[date]
    skipped_window_dates: list[date]
    skipped_forbidden_dates: list[date]
    windows_created: int


def _apply_same_day_cutoff(
    bits: bytes,
    target_day: date,
    *,
    instructor_id: str,
    db: Any,
    instructor_today: date,
    now_minutes: Optional[int],
) -> tuple[bytes, Optional[int]]:
    service_module = availability_service_module()
    if service_module.ALLOW_PAST or target_day != instructor_today:
        return bits, now_minutes
    if now_minutes is None:
        now_dt = service_module.get_user_now_by_id(instructor_id, db)
        now_minutes = max(0, time_to_minutes(now_dt.time(), is_end_time=False))
    cutoff_index = now_minutes // MINUTES_PER_SLOT
    if cutoff_index <= 0:
        return bits, now_minutes
    original_indexes = unpack_indexes(bits)
    filtered = [index for index in original_indexes if index >= cutoff_index]
    if len(filtered) == len(original_indexes):
        return bits, now_minutes
    return pack_indexes(filtered), now_minutes


def _resolve_desired_day_bitmaps(
    day: date,
    *,
    existing: DayBitmaps,
    bitmaps_by_day: dict[date, DayBitmaps],
    clear_existing: bool,
) -> tuple[bytes, bytes]:
    if day in bitmaps_by_day:
        return bitmaps_by_day[day].bits, bitmaps_by_day[day].format_tags
    if clear_existing:
        return new_empty_bits(), new_empty_tags()
    return existing.bits, existing.format_tags


def _log_bitmap_write_debug(
    *,
    day: date,
    existing: DayBitmaps,
    desired_bits: bytes,
    desired_tags: bytes,
    override: bool,
    allow_past: bool,
) -> None:
    old_crc = hashlib.sha1(existing.bits + existing.format_tags, usedforsecurity=False).hexdigest()
    new_crc = hashlib.sha1(desired_bits + desired_tags, usedforsecurity=False).hexdigest()
    logger.debug(
        "bitmap_pair_write day=%s changed=%s old_crc=%s new_crc=%s override=%s allow_past=%s",
        day.isoformat(),
        "true",
        old_crc,
        new_crc,
        override,
        "true" if allow_past else "false",
    )


class AvailabilityBitmapWriteMixin(AvailabilityMixinBase):
    """Core bitmap persistence: diffing, upsert, audit, and cache update."""

    @BaseService.measure_operation("save_week_bits")
    def save_week_bits(
        self,
        instructor_id: str,
        week_start: date,
        windows_by_day: dict[date, list[tuple[str, str]]],
        base_version: Optional[str],
        override: bool,
        clear_existing: bool,
        *,
        actor: Any | None = None,
    ) -> SaveWeekBitsResult:
        """Persist week availability using bitmap storage via the bitmap-native save path."""
        monday = week_start - timedelta(days=week_start.weekday())
        days_this_week = [monday + timedelta(days=offset) for offset in range(7)]
        current_bitmaps = self.get_week_bitmaps(instructor_id, monday, use_cache=False)
        requested_bitmaps: dict[date, DayBitmaps] = {}
        force_write_dates: set[date] = set()

        for day in days_this_week:
            existing = current_bitmaps.get(day, DayBitmaps(new_empty_bits(), new_empty_tags()))
            if day in windows_by_day:
                normalized_windows = self._normalize_week_windows_for_bits_save(windows_by_day[day])
                desired_bits = (
                    bits_from_windows(normalized_windows)
                    if normalized_windows
                    else new_empty_bits()
                )
                requested_bitmaps[day] = DayBitmaps(desired_bits, existing.format_tags)
                if clear_existing and normalized_windows:
                    force_write_dates.add(day)
            elif clear_existing:
                requested_bitmaps[day] = DayBitmaps(new_empty_bits(), existing.format_tags)

        bitmap_result = self._save_week_bitmaps_internal(
            instructor_id=instructor_id,
            week_start=week_start,
            bitmaps_by_day=requested_bitmaps,
            base_version=base_version,
            override=override,
            clear_existing=clear_existing,
            actor=actor,
            current_map=current_bitmaps,
            force_write_dates=force_write_dates,
        )
        return SaveWeekBitsResult(
            rows_written=bitmap_result.rows_written,
            days_written=bitmap_result.days_written,
            weeks_affected=bitmap_result.weeks_affected,
            windows_created=bitmap_result.windows_created,
            skipped_past_window=bitmap_result.skipped_past_window,
            skipped_past_forbidden=bitmap_result.skipped_past_forbidden,
            bits_by_day={
                day: bitmaps.bits for day, bitmaps in bitmap_result.bitmaps_by_day.items()
            },
            version=bitmap_result.version,
            written_dates=bitmap_result.written_dates,
            skipped_dates=bitmap_result.skipped_dates,
            past_written_dates=bitmap_result.past_written_dates,
            edited_dates=bitmap_result.edited_dates,
        )

    def _compute_bitmap_day_updates(
        self,
        *,
        instructor_id: str,
        week_start: date,
        bitmaps_by_day: dict[date, DayBitmaps],
        base_version: Optional[str],
        override: bool,
        clear_existing: bool,
        current_map: dict[date, DayBitmaps] | None,
        force_write_dates: set[date] | None,
    ) -> BitmapDayUpdateResult:
        monday = week_start - timedelta(days=week_start.weekday())
        days_this_week = [monday + timedelta(days=offset) for offset in range(7)]
        current_raw = current_map or self.get_week_bitmaps(instructor_id, monday, use_cache=False)
        normalized_current_map: dict[date, DayBitmaps] = {
            day: current_raw.get(day, DayBitmaps(new_empty_bits(), new_empty_tags()))
            for day in days_this_week
        }
        server_version = self.compute_week_version_bitmaps(normalized_current_map)
        if base_version and base_version != server_version and not override:
            raise ConflictException("Week has changed; please refresh and retry")
        service_module = availability_service_module()
        instructor_today = service_module.get_user_today_by_id(instructor_id, self.db)
        window_days = max(0, service_module.settings.past_edit_window_days)
        past_cutoff = instructor_today - timedelta(days=window_days) if window_days > 0 else None
        now_minutes: Optional[int] = None
        updates: list[tuple[date, bytes, bytes]] = []
        target_map: dict[date, DayBitmaps] = dict(normalized_current_map)
        changed_dates: set[date] = set()
        past_written_dates: set[date] = set()
        skipped_window_dates: set[date] = set()
        skipped_forbidden_dates: set[date] = set()
        windows_created = 0
        forced_dates = force_write_dates or set()
        for day in days_this_week:
            existing = normalized_current_map[day]
            desired_bits, desired_tags = _resolve_desired_day_bitmaps(
                day,
                existing=existing,
                bitmaps_by_day=bitmaps_by_day,
                clear_existing=clear_existing,
            )
            desired_bits, now_minutes = _apply_same_day_cutoff(
                desired_bits,
                day,
                instructor_id=instructor_id,
                db=self.db,
                instructor_today=instructor_today,
                now_minutes=now_minutes,
            )
            desired_tags = normalize_format_tags(desired_bits, desired_tags)
            if (
                desired_bits == existing.bits
                and desired_tags == existing.format_tags
                and day not in forced_dates
            ):
                continue
            if not service_module.ALLOW_PAST and day < instructor_today:
                skipped_forbidden_dates.add(day)
                continue
            if past_cutoff and day < past_cutoff:
                skipped_window_dates.add(day)
                continue
            target_map[day] = DayBitmaps(desired_bits, desired_tags)
            updates.append((day, desired_bits, desired_tags))
            changed_dates.add(day)
            if day < instructor_today:
                past_written_dates.add(day)
            old_windows = service_module.windows_from_bits(existing.bits)
            new_windows = service_module.windows_from_bits(desired_bits)
            if len(new_windows) > len(old_windows):
                windows_created += len(new_windows) - len(old_windows)
            if service_module.PERF_DEBUG:
                _log_bitmap_write_debug(
                    day=day,
                    existing=existing,
                    desired_bits=desired_bits,
                    desired_tags=desired_tags,
                    override=override,
                    allow_past=service_module.ALLOW_PAST,
                )
        return BitmapDayUpdateResult(
            server_version=server_version,
            normalized_current_map=normalized_current_map,
            target_map=target_map,
            updates=updates,
            changed_dates=changed_dates,
            past_written_dates=past_written_dates,
            skipped_window_dates=sorted(skipped_window_dates),
            skipped_forbidden_dates=sorted(skipped_forbidden_dates),
            windows_created=windows_created,
        )

    def _persist_bitmap_updates(
        self,
        *,
        instructor_id: str,
        updates: list[tuple[date, bytes, bytes]],
    ) -> int:
        return int(self._bitmap_repo().upsert_week(instructor_id, updates))

    def _build_noop_bitmap_save_result(
        self,
        *,
        day_updates: BitmapDayUpdateResult,
    ) -> SaveWeekBitmapsResult:
        return SaveWeekBitmapsResult(
            rows_written=0,
            days_written=0,
            weeks_affected=0,
            windows_created=0,
            skipped_past_window=len(day_updates.skipped_window_dates),
            skipped_past_forbidden=len(day_updates.skipped_forbidden_dates),
            bitmaps_by_day=day_updates.normalized_current_map,
            version=day_updates.server_version,
            written_dates=[],
            skipped_dates=day_updates.skipped_window_dates,
            past_written_dates=[],
            edited_dates=[],
        )

    def _write_bitmap_save_audit_if_needed(
        self,
        *,
        instructor_id: str,
        week_start: date,
        day_updates: BitmapDayUpdateResult,
        actor: Any | None,
    ) -> None:
        service_module = availability_service_module()
        audit_dates = sorted(
            set(day_updates.changed_dates)
            | set(day_updates.skipped_window_dates)
            | set(day_updates.skipped_forbidden_dates)
        )
        if not audit_dates or not service_module.AUDIT_ENABLED:
            return
        before_payload, after_payload = self._build_bitmap_save_audit_payloads(
            week_start=week_start,
            normalized_current_map=day_updates.normalized_current_map,
            target_map=day_updates.target_map,
            changed_dates=day_updates.changed_dates,
            skipped_window_dates=day_updates.skipped_window_dates,
            skipped_forbidden_dates=day_updates.skipped_forbidden_dates,
            past_written_dates=day_updates.past_written_dates,
            audit_dates=audit_dates,
        )
        try:
            self._write_availability_audit(
                instructor_id,
                week_start,
                "save_week",
                actor=actor,
                before=before_payload,
                after=after_payload,
            )
        except Exception as audit_error:
            logger.warning(
                "Audit write failed for bitmap save_week_bitmaps",
                extra={
                    "instructor_id": instructor_id,
                    "week_start": week_start.isoformat(),
                    "error": str(audit_error),
                },
            )

    def _emit_bitmap_save_events(
        self,
        *,
        instructor_id: str,
        week_start: date,
        changed_dates: set[date],
        instructor_today: date,
        clear_existing: bool,
    ) -> None:
        event_dates = [
            day
            for day in sorted(changed_dates)
            if not (
                availability_service_module().settings.suppress_past_availability_events
                and day < instructor_today
            )
        ]
        if not event_dates:
            return
        try:
            prepared = PreparedWeek(windows=[], affected_dates=set(event_dates))
            self._enqueue_week_save_event(
                instructor_id,
                week_start,
                week_dates=[week_start + timedelta(days=offset) for offset in range(7)],
                prepared=prepared,
                created_count=len(changed_dates),
                deleted_count=0,
                clear_existing=bool(clear_existing),
            )
        except Exception as enqueue_error:
            logger.warning(
                "Outbox enqueue failed for bitmap save_week_bitmaps",
                extra={
                    "instructor_id": instructor_id,
                    "week_start": week_start.isoformat(),
                    "error": str(enqueue_error),
                },
            )

    def _finalize_bitmap_save_result(
        self,
        *,
        instructor_id: str,
        monday: date,
        rows_written: int,
        day_updates: BitmapDayUpdateResult,
    ) -> SaveWeekBitmapsResult:
        after_map = dict(day_updates.target_map)
        self._update_bitmap_caches_after_save(
            instructor_id=instructor_id,
            monday=monday,
            after_map=after_map,
        )
        changed_dates = sorted(day_updates.changed_dates)
        past_written_dates = sorted(day_updates.past_written_dates)
        if changed_dates:
            self._invalidate_availability_caches(instructor_id, changed_dates)
        availability_service_module().invalidate_on_availability_change(instructor_id)
        return SaveWeekBitmapsResult(
            rows_written=rows_written,
            days_written=len(changed_dates),
            weeks_affected=1,
            windows_created=day_updates.windows_created,
            skipped_past_window=len(day_updates.skipped_window_dates),
            skipped_past_forbidden=len(day_updates.skipped_forbidden_dates),
            bitmaps_by_day=after_map,
            version=self.compute_week_version_bitmaps(after_map),
            written_dates=changed_dates,
            skipped_dates=day_updates.skipped_window_dates,
            past_written_dates=past_written_dates,
            edited_dates=[day.isoformat() for day in changed_dates],
        )

    def _save_week_bitmaps_internal(
        self,
        instructor_id: str,
        week_start: date,
        bitmaps_by_day: dict[date, DayBitmaps],
        base_version: Optional[str],
        override: bool,
        clear_existing: bool,
        *,
        actor: Any | None = None,
        current_map: dict[date, DayBitmaps] | None = None,
        force_write_dates: set[date] | None = None,
    ) -> SaveWeekBitmapsResult:
        """Persist week availability using bitmap-native bits + format tags."""
        monday = week_start - timedelta(days=week_start.weekday())
        day_updates = self._compute_bitmap_day_updates(
            instructor_id=instructor_id,
            week_start=week_start,
            bitmaps_by_day=bitmaps_by_day,
            base_version=base_version,
            override=override,
            clear_existing=clear_existing,
            current_map=current_map,
            force_write_dates=force_write_dates,
        )
        if not day_updates.updates:
            return self._build_noop_bitmap_save_result(day_updates=day_updates)
        service_module = availability_service_module()
        instructor_today = service_module.get_user_today_by_id(instructor_id, self.db)
        with self.transaction():
            rows_written = self._persist_bitmap_updates(
                instructor_id=instructor_id,
                updates=day_updates.updates,
            )
            self._write_bitmap_save_audit_if_needed(
                instructor_id=instructor_id,
                week_start=week_start,
                day_updates=day_updates,
                actor=actor,
            )
            self._emit_bitmap_save_events(
                instructor_id=instructor_id,
                week_start=week_start,
                changed_dates=day_updates.changed_dates,
                instructor_today=instructor_today,
                clear_existing=clear_existing,
            )
        return self._finalize_bitmap_save_result(
            instructor_id=instructor_id,
            monday=monday,
            rows_written=rows_written,
            day_updates=day_updates,
        )

    @BaseService.measure_operation("save_week_bitmaps")
    def save_week_bitmaps(
        self,
        instructor_id: str,
        week_start: date,
        bitmaps_by_day: dict[date, DayBitmaps],
        base_version: Optional[str],
        override: bool,
        clear_existing: bool,
        *,
        actor: Any | None = None,
    ) -> SaveWeekBitmapsResult:
        return self._save_week_bitmaps_internal(
            instructor_id=instructor_id,
            week_start=week_start,
            bitmaps_by_day=bitmaps_by_day,
            base_version=base_version,
            override=override,
            clear_existing=clear_existing,
            actor=actor,
        )
