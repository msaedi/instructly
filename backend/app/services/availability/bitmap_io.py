"""Bitmap read operations, encoding helpers, and week versioning."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import logging
from typing import Iterable, Optional

from ...utils.bitset import bits_from_windows, new_empty_bits, new_empty_tags, windows_from_bits
from ...utils.time_helpers import string_to_time
from ..base import BaseService
from .mixin_base import AvailabilityMixinBase
from .types import DayBitmaps, SlotSnapshot, TimeSlotResponse

logger = logging.getLogger(__name__)


def _coerce_week_window_time(value: str | time) -> tuple[time, bool]:
    if isinstance(value, time):
        return value, False
    value_str = str(value)
    is_midnight = value_str in {"24:00", "24:00:00"}
    coerced = string_to_time(value_str)
    return coerced, is_midnight


class AvailabilityBitmapIOMixin(AvailabilityMixinBase):
    """Bitmap read/write primitives, encoding/decoding, versioning."""

    @BaseService.measure_operation("get_week_bits")
    def get_week_bits(
        self, instructor_id: str, week_start: date, *, use_cache: bool = True
    ) -> dict[date, bytes]:
        """Return dict of day -> bits, ensuring all 7 days are present."""
        monday = week_start - timedelta(days=week_start.weekday())
        cache_service = self.cache_service if use_cache else None
        cache_keys: Optional[tuple[str, str]] = None
        if cache_service:
            cache_keys = self._week_cache_keys(instructor_id, monday)
            map_key, composite_key = cache_keys
            try:
                cached_payload = cache_service.get_json(composite_key)
                cached_result = self._extract_cached_week_result(
                    cached_payload,
                    include_slots=False,
                )
                if cached_result:
                    return self._bits_from_week_map(cached_result.week_map, monday)

                cached_map = cache_service.get_json(map_key)
                sanitized = self._sanitize_week_map(cached_map)
                if sanitized is not None:
                    return self._bits_from_week_map(sanitized, monday)
            except Exception as cache_error:
                logger.warning("Cache read error for week bits: %s", cache_error)

        repo = self._bitmap_repo()
        rows = repo.get_week_rows(instructor_id, monday)
        existing = {row.day_date: row.bits for row in rows}
        bits_by_day: dict[date, bytes] = {}
        for offset in range(7):
            day = monday + timedelta(days=offset)
            bits_by_day[day] = existing.get(day, new_empty_bits())

        if use_cache and cache_service and cache_keys:
            try:
                week_map, _ = self._week_map_from_bits(bits_by_day, include_snapshots=False)
                self._persist_week_cache(
                    instructor_id=instructor_id,
                    week_start=monday,
                    week_map=week_map,
                    cache_keys=cache_keys,
                )
            except Exception as cache_error:
                logger.warning("Cache write error for week bits: %s", cache_error)

        return bits_by_day

    @BaseService.measure_operation("get_week_bitmaps")
    def get_week_bitmaps(
        self, instructor_id: str, week_start: date, *, use_cache: bool = False
    ) -> dict[date, DayBitmaps]:
        """Return dict of day -> (bits, format_tags), ensuring all 7 days are present."""
        monday = week_start - timedelta(days=week_start.weekday())
        if use_cache:
            logger.debug(
                "Week bitmap pair cache is not enabled; falling back to direct repository fetch",
                extra={"instructor_id": instructor_id, "week_start": monday.isoformat()},
            )

        repo = self._bitmap_repo()
        rows = repo.get_week_rows(instructor_id, monday)
        existing = {
            row.day_date: DayBitmaps(row.bits, row.format_tags or new_empty_tags()) for row in rows
        }
        bitmaps_by_day: dict[date, DayBitmaps] = {}
        for offset in range(7):
            day = monday + timedelta(days=offset)
            bitmaps_by_day[day] = existing.get(day, DayBitmaps(new_empty_bits(), new_empty_tags()))
        return bitmaps_by_day

    @BaseService.measure_operation("compute_week_version_bits")
    def compute_week_version_bits(self, bits_by_day: dict[date, bytes]) -> str:
        """Stable SHA1 of concatenated 7xbits ordered chronologically."""
        if not bits_by_day:
            concat = new_empty_bits() * 7
        else:
            anchor = min(bits_by_day.keys())
            monday = anchor - timedelta(days=anchor.weekday())
            ordered_days = [monday + timedelta(days=i) for i in range(7)]
            concat = b"".join(bits_by_day.get(day, new_empty_bits()) for day in ordered_days)
        return hashlib.sha1(concat, usedforsecurity=False).hexdigest()

    @BaseService.measure_operation("compute_week_version_bitmaps")
    def compute_week_version_bitmaps(self, bitmaps_by_day: dict[date, DayBitmaps]) -> str:
        """Stable SHA1 of concatenated 7x(bits + format_tags) ordered chronologically."""
        if not bitmaps_by_day:
            concat = (new_empty_bits() + new_empty_tags()) * 7
        else:
            anchor = min(bitmaps_by_day.keys())
            monday = anchor - timedelta(days=anchor.weekday())
            ordered_days = [monday + timedelta(days=i) for i in range(7)]
            concat = b"".join(
                (
                    bitmaps_by_day.get(day, DayBitmaps(new_empty_bits(), new_empty_tags())).bits
                    + bitmaps_by_day.get(
                        day, DayBitmaps(new_empty_bits(), new_empty_tags())
                    ).format_tags
                )
                for day in ordered_days
            )
        return hashlib.sha1(concat, usedforsecurity=False).hexdigest()

    @BaseService.measure_operation("get_week_bitmap_last_modified")
    def get_week_bitmap_last_modified(
        self, instructor_id: str, week_start: date
    ) -> Optional[datetime]:
        """Return the latest updated_at across bitmap rows for the week."""
        repo = self._bitmap_repo()
        rows = repo.get_week_rows(instructor_id, week_start)
        latest: Optional[datetime] = None
        for row in rows:
            dt = row.updated_at
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if latest is None or dt > latest:
                latest = dt
        return latest

    @staticmethod
    def _normalize_week_windows_for_bits_save(
        raw_windows: Iterable[tuple[str | time, str | time]],
    ) -> list[tuple[str, str]]:
        normalized: list[tuple[str, str]] = []
        for start_raw, end_raw in raw_windows:
            start_obj, _ = _coerce_week_window_time(start_raw)
            end_obj, end_is_midnight = _coerce_week_window_time(end_raw)
            start_val = start_obj.strftime("%H:%M:%S")
            if end_is_midnight or (
                end_obj == time(0, 0) and start_obj != time(0, 0) and start_obj > end_obj
            ):
                end_val = "24:00:00"
            else:
                end_val = end_obj.strftime("%H:%M:%S")
            normalized.append((start_val, end_val))
        return normalized

    @BaseService.measure_operation("compute_week_version")
    def compute_week_version(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        windows: Optional[list[tuple[date, time, time]]] = None,
    ) -> str:
        """Compute a deterministic week version using bits and format tags."""
        week_start = start_date - timedelta(days=start_date.weekday())
        bitmaps_by_day = self.get_week_bitmaps(instructor_id, week_start)
        return self.compute_week_version_bitmaps(bitmaps_by_day)

    def _week_map_from_bits(
        self,
        bits_by_day: dict[date, bytes],
        *,
        include_snapshots: bool,
    ) -> tuple[dict[str, list[TimeSlotResponse]], list[SlotSnapshot]]:
        week_schedule: dict[str, list[TimeSlotResponse]] = {}
        snapshots: list[SlotSnapshot] = []
        for day in sorted(bits_by_day.keys()):
            date_str = day.isoformat()
            windows = windows_from_bits(bits_by_day[day])
            entries: list[TimeSlotResponse] = []
            for start, end in windows:
                start_str = str(start)
                end_str = str(end)
                entries.append(
                    TimeSlotResponse(
                        start_time=start_str,
                        end_time=end_str,
                    )
                )
                if include_snapshots:
                    snapshots.append(
                        SlotSnapshot(
                            specific_date=day,
                            start_time=string_to_time(start_str),
                            end_time=string_to_time(end_str),
                            created_at=None,
                            updated_at=None,
                        )
                    )
            if entries:
                week_schedule[date_str] = entries
        return week_schedule, snapshots

    @staticmethod
    def _bits_from_week_map(
        week_map: dict[str, list[TimeSlotResponse]],
        week_start: date,
    ) -> dict[date, bytes]:
        monday = week_start - timedelta(days=week_start.weekday())
        bits_by_day: dict[date, bytes] = {}
        for offset in range(7):
            day = monday + timedelta(days=offset)
            windows: list[tuple[str, str]] = []
            for entry in week_map.get(day.isoformat(), []):
                start = entry.get("start_time")
                end = entry.get("end_time")
                if start is None or end is None:
                    continue
                windows.append((str(start), str(end)))
            bits_by_day[day] = bits_from_windows(windows) if windows else new_empty_bits()
        return bits_by_day
