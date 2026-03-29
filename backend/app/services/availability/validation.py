"""Overlap validation, interval checks, and specific-date availability."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from ...core.exceptions import AvailabilityOverlapException, ConflictException
from ...schemas.availability_window import SpecificDateAvailabilityCreate
from ...utils.bitset import bits_from_windows
from ...utils.time_helpers import string_to_time
from ...utils.time_utils import time_to_minutes
from ..base import BaseService
from .mixin_base import AvailabilityMixinBase
from .types import ProcessedSlot, availability_service_module


class AvailabilityValidationMixin(AvailabilityMixinBase):
    """Overlap validation, interval checks, and specific-date availability."""

    @BaseService.measure_operation("add_specific_date")
    def add_specific_date_availability(
        self, instructor_id: str, availability_data: SpecificDateAvailabilityCreate
    ) -> dict[str, Any]:
        """Add availability for a specific date using bitmap storage."""
        target_date = availability_data.specific_date

        with self.transaction():
            bitmap_repo = self._bitmap_repo()
            existing_bits = bitmap_repo.get_day_bits(instructor_id, target_date)
            service_module = availability_service_module()
            existing_windows_str: list[tuple[str, str]] = (
                service_module.windows_from_bits(existing_bits) if existing_bits else []
            )
            new_window_str = (
                availability_data.start_time.strftime("%H:%M:%S"),
                availability_data.end_time.strftime("%H:%M:%S"),
            )
            if new_window_str in existing_windows_str:
                raise ConflictException("This time slot already exists")

            candidate_windows_str = existing_windows_str + [new_window_str]
            candidate_windows_time: list[tuple[time, time]] = [
                (string_to_time(start_str), string_to_time(end_str))
                for start_str, end_str in candidate_windows_str
            ]
            self._validate_no_overlaps(
                instructor_id,
                {
                    target_date: [
                        ProcessedSlot(start_time=start, end_time=end)
                        for start, end in candidate_windows_time
                    ]
                },
                ignore_existing=True,
            )

            if existing_bits:
                new_bits = bits_from_windows(candidate_windows_str)
            else:
                new_bits = bits_from_windows([new_window_str])

            bitmap_repo.upsert_week(instructor_id, [(target_date, new_bits)])

        self._invalidate_availability_caches(instructor_id, [target_date])
        availability_service_module().invalidate_on_availability_change(instructor_id)
        return {
            "id": f"{instructor_id}:{target_date.isoformat()}:{availability_data.start_time}:{availability_data.end_time}",
            "instructor_id": instructor_id,
            "specific_date": target_date,
            "start_time": availability_data.start_time,
            "end_time": availability_data.end_time,
        }

    def _validate_no_overlaps(
        self,
        instructor_id: str,
        schedule_by_date: dict[date, list[ProcessedSlot]],
        *,
        ignore_existing: bool,
        existing_by_date: dict[date, list[ProcessedSlot]] | None = None,
    ) -> None:
        """Ensure proposed slots obey the half-open interval rules."""
        for target_date, slots in list(schedule_by_date.items()):
            if not slots:
                continue

            slots.sort(key=lambda slot: (slot["start_time"], slot["end_time"]))
            schedule_by_date[target_date] = slots

            active_start: time | None = None
            active_end: time | None = None
            active_end_min = None
            for slot in slots:
                start = slot["start_time"]
                end = slot["end_time"]
                self._ensure_valid_interval(target_date, start, end)
                start_min, end_min = self._minutes_range(start, end)
                if active_end_min is not None and start_min < active_end_min:
                    self._raise_overlap(target_date, (start, end), (active_start, active_end))
                if active_end_min is None or end_min > active_end_min:
                    active_start, active_end = start, end
                    active_end_min = end_min

            if ignore_existing:
                continue

            existing_pairs: list[tuple[time, time]] = []
            if existing_by_date is not None:
                for existing_slot in existing_by_date.get(target_date, []) or []:
                    existing_pairs.append((existing_slot["start_time"], existing_slot["end_time"]))
            else:
                bits = self._bitmap_repo().get_day_bits(instructor_id, target_date)
                if bits:
                    for start_str, end_str in availability_service_module().windows_from_bits(bits):
                        start_obj = string_to_time(start_str)
                        end_obj = time(0, 0) if end_str == "24:00:00" else string_to_time(end_str)
                        existing_pairs.append((start_obj, end_obj))

            existing_ranges = set(existing_pairs)
            filtered: list[ProcessedSlot] = []
            for slot in slots:
                key = (slot["start_time"], slot["end_time"])
                if key not in existing_ranges:
                    filtered.append(slot)
            schedule_by_date[target_date] = filtered

            intervals: list[tuple[time, time, str]] = [
                (start, end, "existing") for start, end in existing_pairs
            ]
            intervals.extend((slot["start_time"], slot["end_time"], "new") for slot in filtered)
            if not intervals:
                continue

            intervals.sort(key=lambda item: (item[0], item[1]))
            active_start, active_end, active_origin = intervals[0]
            self._ensure_valid_interval(target_date, active_start, active_end)
            _, active_end_min = self._minutes_range(active_start, active_end)

            for start, end, origin in intervals[1:]:
                self._ensure_valid_interval(target_date, start, end)
                start_min, end_min = self._minutes_range(start, end)
                if start_min < active_end_min:
                    if origin == "new":
                        new_range = (start, end)
                        conflict = (active_start, active_end)
                    elif active_origin == "new":
                        new_range = (active_start, active_end)
                        conflict = (start, end)
                    else:
                        new_range = (start, end)
                        conflict = (active_start, active_end)
                    self._raise_overlap(target_date, new_range, conflict)
                if end_min > active_end_min or (
                    end_min == active_end_min and origin == "new" and active_origin != "new"
                ):
                    active_start, active_end, active_origin = start, end, origin
                    active_end_min = end_min

    @staticmethod
    def _minutes_range(start: time, end: time) -> tuple[int, int]:
        start_min = time_to_minutes(start, is_end_time=False)
        end_min = time_to_minutes(end, is_end_time=True)
        return start_min, end_min

    @staticmethod
    def _format_interval(start: time, end: time) -> str:
        return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"

    def _ensure_valid_interval(self, target_date: date, start: time, end: time) -> None:
        start_min, end_min = self._minutes_range(start, end)
        if start_min >= end_min:
            formatted = self._format_interval(start, end)
            raise AvailabilityOverlapException(
                specific_date=target_date.isoformat(),
                new_range=formatted,
                conflicting_range=formatted,
            )

    def _raise_overlap(
        self,
        target_date: date,
        new_range: tuple[time | None, time | None],
        conflict_range: tuple[time | None, time | None],
    ) -> None:
        new_start, new_end = new_range
        conflict_start, conflict_end = conflict_range
        if new_start is None or new_end is None or conflict_start is None or conflict_end is None:
            raise AvailabilityOverlapException(
                specific_date=target_date.isoformat(),
                new_range="unknown",
                conflicting_range="unknown",
            )
        raise AvailabilityOverlapException(
            specific_date=target_date.isoformat(),
            new_range=self._format_interval(new_start, new_end),
            conflicting_range=self._format_interval(conflict_start, conflict_end),
        )
