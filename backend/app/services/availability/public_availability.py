"""Student-facing availability calculation and interval math helpers."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any, Iterable, Optional

from ...core.constants import BOOKING_START_STEP_MINUTES, MINUTES_PER_SLOT
from ...utils.bitset import (
    get_slot_tag,
    is_tag_compatible,
    new_empty_tags,
)
from ...utils.time_helpers import string_to_time
from ...utils.time_utils import time_to_minutes
from ..base import BaseService
from ..config_service import is_instructor_travel_format, normalize_location_type
from .mixin_base import AvailabilityMixinBase
from .types import availability_service_module


class AvailabilityPublicMixin(AvailabilityMixinBase):
    """Student-facing availability and slot filtering logic."""

    @staticmethod
    def _coerce_buffer_minutes(value: object, default: int) -> int:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str):
            try:
                return max(0, int(value))
            except ValueError:
                return default
        return default

    @staticmethod
    def _minutes_to_time(minute_value: int) -> time:
        if minute_value >= 24 * 60:
            return time(0, 0)
        clamped = max(0, minute_value)
        return time(clamped // 60, clamped % 60)

    @staticmethod
    def _align_start_minute(start_minute: int) -> int:
        clamped_start = max(0, int(start_minute))
        return (
            (clamped_start + BOOKING_START_STEP_MINUTES - 1) // BOOKING_START_STEP_MINUTES
        ) * BOOKING_START_STEP_MINUTES

    @classmethod
    def _first_aligned_start_in_window(
        cls,
        start_minute: int,
        end_minute: int,
        *,
        duration_minutes: int,
    ) -> int | None:
        required_minutes = max(0, int(duration_minutes))
        aligned_start = cls._align_start_minute(start_minute)
        if aligned_start > end_minute:
            return None
        if aligned_start + required_minutes > end_minute:
            return None
        return aligned_start

    @classmethod
    def _merge_time_intervals(cls, intervals: list[tuple[time, time]]) -> list[tuple[time, time]]:
        if not intervals:
            return []
        minute_ranges = sorted(
            [
                (
                    time_to_minutes(start, is_end_time=False),
                    time_to_minutes(end, is_end_time=True),
                )
                for start, end in intervals
            ],
            key=lambda interval: interval[0],
        )
        merged: list[tuple[int, int]] = []
        current_start, current_end = minute_ranges[0]
        for start_minute, end_minute in minute_ranges[1:]:
            if start_minute <= current_end:
                current_end = max(current_end, end_minute)
            else:
                merged.append((current_start, current_end))
                current_start, current_end = start_minute, end_minute
        merged.append((current_start, current_end))
        return [
            (cls._minutes_to_time(start_minute), cls._minutes_to_time(end_minute))
            for start_minute, end_minute in merged
        ]

    @classmethod
    def _subtract_time_intervals(
        cls, bases: list[tuple[time, time]], cuts: list[tuple[time, time]]
    ) -> list[tuple[time, time]]:
        if not bases:
            return []
        if not cuts:
            return cls._merge_time_intervals(bases)

        cut_ranges = [
            (
                time_to_minutes(start, is_end_time=False),
                time_to_minutes(end, is_end_time=True),
            )
            for start, end in cls._merge_time_intervals(cuts)
        ]
        out: list[tuple[time, time]] = []
        for base_start, base_end in bases:
            segments = [
                (
                    time_to_minutes(base_start, is_end_time=False),
                    time_to_minutes(base_end, is_end_time=True),
                )
            ]
            for cut_start, cut_end in cut_ranges:
                next_segments: list[tuple[int, int]] = []
                for segment_start, segment_end in segments:
                    if segment_end <= cut_start or segment_start >= cut_end:
                        next_segments.append((segment_start, segment_end))
                    else:
                        if segment_start < cut_start:
                            next_segments.append((segment_start, max(segment_start, cut_start)))
                        if segment_end > cut_end:
                            next_segments.append((min(segment_end, cut_end), segment_end))
                segments = [segment for segment in next_segments if segment[1] > segment[0]]
                if not segments:
                    break
            for segment_start, segment_end in segments:
                out.append(
                    (
                        cls._minutes_to_time(segment_start),
                        cls._minutes_to_time(segment_end),
                    )
                )
        return cls._merge_time_intervals(out)

    @classmethod
    def _resolve_buffer_profile_values(
        cls,
        instructor_profile: object | None,
        *,
        default_non_travel_buffer_minutes: int,
        default_travel_buffer_minutes: int,
    ) -> tuple[int, int]:
        if instructor_profile is None:
            return (
                cls._coerce_buffer_minutes(
                    default_non_travel_buffer_minutes, default_non_travel_buffer_minutes
                ),
                cls._coerce_buffer_minutes(
                    default_travel_buffer_minutes, default_travel_buffer_minutes
                ),
            )
        return (
            cls._coerce_buffer_minutes(
                getattr(instructor_profile, "non_travel_buffer_minutes", None),
                default_non_travel_buffer_minutes,
            ),
            cls._coerce_buffer_minutes(
                getattr(instructor_profile, "travel_buffer_minutes", None),
                default_travel_buffer_minutes,
            ),
        )

    @classmethod
    def _subtract_buffered_bookings_from_windows(
        cls,
        bases: list[tuple[time, time]],
        bookings: Iterable[object],
        *,
        requested_location_type: str | None,
        non_travel_buffer_minutes: int,
        travel_buffer_minutes: int,
    ) -> list[tuple[time, time]]:
        if not bases:
            return []

        normalized_requested_location = normalize_location_type(requested_location_type)
        cuts: list[tuple[time, time]] = []
        for booking in bookings:
            start_time = getattr(booking, "start_time", None)
            end_time = getattr(booking, "end_time", None)
            if not isinstance(start_time, time) or not isinstance(end_time, time):
                continue
            existing_location_type = getattr(booking, "location_type", None)
            buffer_minutes = (
                travel_buffer_minutes
                if (
                    is_instructor_travel_format(existing_location_type)
                    or is_instructor_travel_format(normalized_requested_location)
                )
                else non_travel_buffer_minutes
            )
            start_minute = max(
                0,
                time_to_minutes(start_time, is_end_time=False) - max(0, buffer_minutes),
            )
            end_minute = min(
                24 * 60,
                time_to_minutes(end_time, is_end_time=True) + max(0, buffer_minutes),
            )
            if end_minute <= start_minute:
                continue
            cuts.append(
                (
                    cls._minutes_to_time(start_minute),
                    cls._minutes_to_time(end_minute),
                )
            )
        return cls._subtract_time_intervals(bases, cuts)

    @classmethod
    def _windows_support_booking_request(
        cls,
        windows: Iterable[tuple[time, time]],
        *,
        time_after: time | None = None,
        time_before: time | None = None,
        duration_minutes: int = 60,
    ) -> bool:
        earliest_start_minute = (
            time_to_minutes(time_after, is_end_time=False) if time_after is not None else 0
        )
        latest_end_minute = (
            time_to_minutes(time_before, is_end_time=True) if time_before is not None else 24 * 60
        )
        required_minutes = max(0, int(duration_minutes))
        for start_time, end_time in windows:
            start_minute = max(
                time_to_minutes(start_time, is_end_time=False), earliest_start_minute
            )
            end_minute = min(time_to_minutes(end_time, is_end_time=True), latest_end_minute)
            if (
                cls._first_aligned_start_in_window(
                    start_minute,
                    end_minute,
                    duration_minutes=required_minutes,
                )
                is not None
            ):
                return True
        return False

    @classmethod
    def _filter_windows_by_format_tags(
        cls,
        windows: list[tuple[time, time]],
        format_tags: bytes | None,
        *,
        requested_location_type: str | None,
    ) -> list[tuple[time, time]]:
        if not windows:
            return []

        tags = format_tags or new_empty_tags()
        normalized_requested_location = normalize_location_type(requested_location_type)
        filtered: list[tuple[time, time]] = []

        for start_time, end_time in windows:
            start_minute = time_to_minutes(start_time, is_end_time=False)
            end_minute = time_to_minutes(end_time, is_end_time=True)
            start_slot = start_minute // MINUTES_PER_SLOT
            end_slot = end_minute // MINUTES_PER_SLOT
            compatible_run_start: int | None = None

            for slot in range(start_slot, end_slot):
                tag = get_slot_tag(tags, slot)
                compatible = is_tag_compatible(tag, normalized_requested_location)
                if compatible:
                    if compatible_run_start is None:
                        compatible_run_start = slot
                    continue

                if compatible_run_start is not None and slot > compatible_run_start:
                    filtered.append(
                        (
                            cls._minutes_to_time(compatible_run_start * MINUTES_PER_SLOT),
                            cls._minutes_to_time(slot * MINUTES_PER_SLOT),
                        )
                    )
                    compatible_run_start = None

            if compatible_run_start is not None and end_slot > compatible_run_start:
                filtered.append(
                    (
                        cls._minutes_to_time(compatible_run_start * MINUTES_PER_SLOT),
                        cls._minutes_to_time(end_slot * MINUTES_PER_SLOT),
                    )
                )

        return filtered

    def _load_public_availability_data(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
    ) -> tuple[dict[date, list[tuple[time, time]]], dict[date, bytes], dict[date, list[Any]]]:
        by_date: dict[date, list[tuple[time, time]]] = {}
        tags_by_date: dict[date, bytes] = {}
        bitmap_repo = self._bitmap_repo()
        for day_row in bitmap_repo.get_days_in_range(instructor_id, start_date, end_date):
            bits = day_row.bits
            format_tags = day_row.format_tags or new_empty_tags()
            tags_by_date[day_row.day_date] = format_tags
            windows_str: list[tuple[str, str]] = availability_service_module().windows_from_bits(
                bits
            )
            by_date[day_row.day_date] = [
                (string_to_time(start_str), string_to_time(end_str))
                for start_str, end_str in windows_str
            ]

        bookings_by_date: dict[date, list[Any]] = {}
        for booking in self.conflict_repository.get_bookings_for_date_range(
            instructor_id,
            start_date,
            end_date,
        ):
            bookings_by_date.setdefault(booking.booking_date, []).append(booking)
        return by_date, tags_by_date, bookings_by_date

    def _compute_day_available_windows(
        self,
        *,
        current_date: date,
        by_date: dict[date, list[tuple[time, time]]],
        tags_by_date: dict[date, bytes],
        bookings_by_date: dict[date, list[Any]],
        requested_location_type: str,
        non_travel_buffer_minutes: int,
        travel_buffer_minutes: int,
    ) -> list[tuple[time, time]]:
        bases = self._merge_time_intervals(by_date.get(current_date, []))
        remaining = self._subtract_buffered_bookings_from_windows(
            bases,
            bookings_by_date.get(current_date, []),
            requested_location_type=requested_location_type,
            non_travel_buffer_minutes=non_travel_buffer_minutes,
            travel_buffer_minutes=travel_buffer_minutes,
        )
        return self._filter_windows_by_format_tags(
            remaining,
            tags_by_date.get(current_date),
            requested_location_type=requested_location_type,
        )

    def _trim_windows_for_advance_notice(
        self,
        intervals: list[tuple[time, time]],
        min_start_minutes: int,
    ) -> list[tuple[time, time]]:
        trimmed: list[tuple[time, time]] = []
        for start, end in intervals:
            start_min, end_min = self._minutes_range(start, end)
            if end_min <= min_start_minutes:
                continue
            if start_min < min_start_minutes:
                start_min = min_start_minutes

            new_start = self._minutes_to_time(start_min)
            new_end = time(0, 0) if end_min >= 24 * 60 else self._minutes_to_time(end_min)
            trimmed.append((new_start, new_end))
        return trimmed

    def _resolve_earliest_allowed_booking(
        self,
        instructor_id: str,
        *,
        requested_location_type: str,
        apply_min_advance: bool,
    ) -> tuple[Optional[date], Optional[int]]:
        config_service = self.config_service
        if config_service is None:
            raise RuntimeError("Config service is required for public availability")
        min_advance_minutes = (
            config_service.get_advance_notice_minutes(requested_location_type)
            if apply_min_advance
            else 0
        )
        if min_advance_minutes <= 0:
            return None, None

        earliest_allowed_local = availability_service_module().get_user_now_by_id(
            instructor_id, self.db
        ) + timedelta(minutes=min_advance_minutes)
        earliest_allowed_local = earliest_allowed_local.replace(second=0, microsecond=0)
        minutes_since_midnight = time_to_minutes(earliest_allowed_local.time(), is_end_time=False)
        aligned_minutes = self._align_start_minute(minutes_since_midnight)
        base_midnight = earliest_allowed_local.replace(hour=0, minute=0, second=0, microsecond=0)
        earliest_allowed_local = base_midnight + timedelta(minutes=aligned_minutes)
        earliest_allowed_date = earliest_allowed_local.date()
        earliest_allowed_minutes = time_to_minutes(earliest_allowed_local.time(), is_end_time=False)
        return earliest_allowed_date, earliest_allowed_minutes

    @BaseService.measure_operation("compute_public_availability")
    def compute_public_availability(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        *,
        requested_location_type: str | None = None,
        apply_min_advance: bool = True,
    ) -> dict[str, list[tuple[time, time]]]:
        """
        Compute per-date availability intervals merged and with booked times subtracted.

        Returns dict: { 'YYYY-MM-DD': [(start_time, end_time), ...] }
        """
        effective_requested_location_type = requested_location_type or "student_location"
        config_service = self.config_service
        if config_service is None:
            raise RuntimeError("Config service is required for public availability")
        profile = self.instructor_repository.get_by_user_id(instructor_id)
        default_non_travel_buffer_minutes = config_service.get_default_buffer_minutes("online")
        default_travel_buffer_minutes = config_service.get_default_buffer_minutes(
            "student_location"
        )
        non_travel_buffer_minutes, travel_buffer_minutes = self._resolve_buffer_profile_values(
            profile,
            default_non_travel_buffer_minutes=default_non_travel_buffer_minutes,
            default_travel_buffer_minutes=default_travel_buffer_minutes,
        )
        earliest_allowed_date, earliest_allowed_minutes = self._resolve_earliest_allowed_booking(
            instructor_id,
            requested_location_type=effective_requested_location_type,
            apply_min_advance=apply_min_advance,
        )
        by_date, tags_by_date, bookings_by_date = self._load_public_availability_data(
            instructor_id,
            start_date,
            end_date,
        )

        result: dict[str, list[tuple[time, time]]] = {}
        current_date = start_date
        while current_date <= end_date:
            remaining = self._compute_day_available_windows(
                current_date=current_date,
                by_date=by_date,
                tags_by_date=tags_by_date,
                bookings_by_date=bookings_by_date,
                requested_location_type=effective_requested_location_type,
                non_travel_buffer_minutes=non_travel_buffer_minutes,
                travel_buffer_minutes=travel_buffer_minutes,
            )
            if earliest_allowed_date:
                if current_date < earliest_allowed_date:
                    result[current_date.isoformat()] = []
                    current_date += timedelta(days=1)
                    continue
                if current_date == earliest_allowed_date and earliest_allowed_minutes is not None:
                    remaining = self._trim_windows_for_advance_notice(
                        remaining, earliest_allowed_minutes
                    )

            result[current_date.isoformat()] = remaining
            current_date += timedelta(days=1)
        return result
