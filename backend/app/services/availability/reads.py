"""Availability read APIs and cache-aware query methods."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
import logging
from typing import Any, Optional

from ...monitoring.availability_perf import WEEK_GET_ENDPOINT, availability_perf_span
from ...utils.bitset import new_empty_bits
from ...utils.time_helpers import string_to_time, time_to_string
from ..base import BaseService
from .mixin_base import AvailabilityMixinBase
from .types import TimeSlotResponse, WeekAvailabilityResult, availability_service_module

logger = logging.getLogger(__name__)


class AvailabilityReadMixin(AvailabilityMixinBase):
    """Public read/query APIs for availability data."""

    def _load_bits_by_date_for_range(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, bytes]:
        """Batch-load bitmap rows for a date range and group them by day."""
        rows = self._bitmap_repo().get_days_in_range(instructor_id, start_date, end_date)
        return {row.day_date: row.bits for row in rows if getattr(row, "bits", None)}

    @BaseService.measure_operation("get_week_last_modified")
    def get_week_last_modified(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        windows: Optional[list[tuple[date, time, time]]] = None,
    ) -> Optional[datetime]:
        """Return last-modified timestamp derived from bitmap rows only."""
        week_start = start_date - timedelta(days=start_date.weekday())
        return self.get_week_bitmap_last_modified(instructor_id, week_start)

    @BaseService.measure_operation("get_availability_for_date")
    def get_availability_for_date(
        self, instructor_id: str, target_date: date
    ) -> Optional[dict[str, Any]]:
        """Get availability for a specific date using bitmap storage."""
        if self.cache_service:
            try:
                cached = self.cache_service.get_instructor_availability_date_range(
                    instructor_id, target_date, target_date
                )
                if cached is not None and len(cached) > 0:
                    first_cached = cached[0]
                    if isinstance(first_cached, dict):
                        return {str(key): value for key, value in first_cached.items()}
            except Exception as cache_error:
                logger.warning("Cache error for date availability: %s", cache_error)

        try:
            bits = self._bitmap_repo().get_day_bits(instructor_id, target_date)
            if bits is None:
                return None

            windows_str: list[tuple[str, str]] = availability_service_module().windows_from_bits(
                bits
            )
            if not windows_str:
                return None

            result = {
                "date": target_date.isoformat(),
                "slots": [
                    TimeSlotResponse(
                        start_time=time_to_string(string_to_time(start_str)),
                        end_time=time_to_string(string_to_time(end_str)),
                    )
                    for start_str, end_str in windows_str
                ],
            }
            if self.cache_service:
                try:
                    self.cache_service.cache_instructor_availability_date_range(
                        instructor_id, target_date, target_date, [result]
                    )
                except Exception as cache_error:
                    logger.warning("Failed to cache date availability: %s", cache_error)

            return result
        except Exception as error:
            logger.error("Error getting availability for date: %s", error)
            return None

    @BaseService.measure_operation("get_availability_summary")
    def get_availability_summary(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> dict[str, int]:
        """Get summary of availability (window counts) for date range."""
        try:
            bitmap_repo = self._bitmap_repo()
            rows = bitmap_repo.get_days_in_range(instructor_id, start_date, end_date)
            result: dict[str, int] = {}
            for row in rows:
                bits = row.bits or new_empty_bits()
                windows = availability_service_module().windows_from_bits(bits)
                if windows:
                    result[row.day_date.isoformat()] = len(windows)
            return result
        except Exception as error:
            logger.error("Error getting availability summary: %s", error)
            return {}

    @BaseService.measure_operation("get_week_availability")
    def get_week_availability(
        self,
        instructor_id: str,
        start_date: date,
        *,
        use_cache: bool = True,
        include_empty: bool = False,
    ) -> dict[str, list[TimeSlotResponse]]:
        if include_empty:
            bits_by_day = self.get_week_bits(
                instructor_id,
                start_date,
                use_cache=use_cache,
            )
            monday = start_date - timedelta(days=start_date.weekday())
            full_map: dict[str, list[TimeSlotResponse]] = {}
            for offset in range(7):
                day = monday + timedelta(days=offset)
                windows = availability_service_module().windows_from_bits(
                    bits_by_day.get(day, new_empty_bits())
                )
                full_map[day.isoformat()] = [
                    {
                        "start_time": start,
                        "end_time": end,
                    }
                    for start, end in windows
                ]
            return full_map

        result = self._get_week_availability_common(
            instructor_id,
            start_date,
            allow_cache_read=use_cache,
            include_slots=False,
        )
        return result.week_map

    @BaseService.measure_operation("get_week_availability_with_slots")
    def get_week_availability_with_slots(
        self,
        instructor_id: str,
        start_date: date,
        *,
        use_cache: bool = True,
        include_empty: bool = False,
    ) -> WeekAvailabilityResult:
        result = self._get_week_availability_common(
            instructor_id,
            start_date,
            allow_cache_read=use_cache,
            include_slots=True,
        )
        if not include_empty:
            return result

        monday = start_date - timedelta(days=start_date.weekday())
        full_map: dict[str, list[TimeSlotResponse]] = {}
        for offset in range(7):
            day = monday + timedelta(days=offset)
            iso_key = day.isoformat()
            full_map[iso_key] = list(result.week_map.get(iso_key, []))
        return WeekAvailabilityResult(week_map=full_map, windows=result.windows)

    def _get_week_availability_common(
        self,
        instructor_id: str,
        start_date: date,
        *,
        allow_cache_read: bool,
        include_slots: bool,
    ) -> WeekAvailabilityResult:
        endpoint = WEEK_GET_ENDPOINT
        self.log_operation(
            "get_week_availability", instructor_id=instructor_id, start_date=start_date
        )

        with availability_perf_span(
            "service.get_week_availability",
            endpoint=endpoint,
            instructor_id=instructor_id,
        ) as perf:
            cache_used = "n"
            cache_keys: Optional[tuple[str, str]] = None
            cache_service = self.cache_service
            if cache_service:
                cache_keys = self._week_cache_keys(instructor_id, start_date)

            if allow_cache_read and cache_service and cache_keys:
                map_key, composite_key = cache_keys
                try:
                    cached_payload = cache_service.get_json(composite_key)
                    cached_result = self._extract_cached_week_result(
                        cached_payload,
                        include_slots=include_slots,
                    )
                    if cached_result:
                        cache_used = "y"
                        if perf:
                            perf(cache_used=cache_used)
                        return cached_result

                    if not include_slots:
                        cached_map = cache_service.get_json(map_key)
                        week_map = self._sanitize_week_map(cached_map)
                        if week_map is not None:
                            cache_used = "y"
                            if perf:
                                perf(cache_used=cache_used)
                            return WeekAvailabilityResult(week_map=week_map, windows=[])
                except Exception as cache_error:
                    logger.warning("Cache error for week availability: %s", cache_error)

            bits_by_day = self.get_week_bits(instructor_id, start_date)
            week_map, slot_snapshots = self._week_map_from_bits(
                bits_by_day,
                include_snapshots=include_slots,
            )

            if cache_service and cache_keys:
                try:
                    self._persist_week_cache(
                        instructor_id=instructor_id,
                        week_start=start_date,
                        week_map=week_map,
                        cache_keys=cache_keys,
                    )
                except Exception as cache_error:
                    logger.warning("Failed to cache week availability: %s", cache_error)

            if perf:
                perf(cache_used=cache_used)

            windows: list[tuple[date, time, time]] = []
            for snapshot in slot_snapshots:
                windows.append((snapshot.specific_date, snapshot.start_time, snapshot.end_time))
            return WeekAvailabilityResult(week_map=week_map, windows=windows)

    @BaseService.measure_operation("get_instructor_availability_for_date_range")
    def get_instructor_availability_for_date_range(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Get instructor availability for a date range using enhanced caching."""
        if self.cache_service:
            try:
                cached_data = self.cache_service.get_instructor_availability_date_range(
                    instructor_id, start_date, end_date
                )
                if cached_data is not None:
                    return [
                        {str(key): value for key, value in item.items()}
                        for item in cached_data
                        if isinstance(item, dict)
                    ]
            except Exception as cache_error:
                logger.warning("Cache error for date range availability: %s", cache_error)

        try:
            bits_by_date = self._load_bits_by_date_for_range(
                instructor_id,
                start_date,
                end_date,
            )
            result = []
            current_date = start_date
            while current_date <= end_date:
                bits = bits_by_date.get(current_date)
                windows_str: list[tuple[str, str]] = (
                    availability_service_module().windows_from_bits(bits) if bits else []
                )
                result.append(
                    {
                        "date": current_date.isoformat(),
                        "slots": [
                            {
                                "start_time": time_to_string(string_to_time(start_str)),
                                "end_time": time_to_string(string_to_time(end_str)),
                            }
                            for start_str, end_str in windows_str
                        ],
                    }
                )
                current_date += timedelta(days=1)

            if self.cache_service:
                try:
                    self.cache_service.cache_instructor_availability_date_range(
                        instructor_id, start_date, end_date, result
                    )
                except Exception as cache_error:
                    logger.warning("Failed to cache date range availability: %s", cache_error)

            return result
        except Exception as error:
            logger.error("Error getting date range availability: %s", error)
            return []

    @BaseService.measure_operation("get_all_availability")
    def get_all_instructor_availability(
        self, instructor_id: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> list[dict[str, Any]]:
        """Get all availability windows for an instructor with optional date filtering."""
        self.log_operation(
            "get_all_instructor_availability",
            instructor_id=instructor_id,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            if not start_date:
                start_date = availability_service_module().get_user_today_by_id(
                    instructor_id, self.db
                )
            if not end_date:
                end_date = availability_service_module().get_user_today_by_id(
                    instructor_id, self.db
                ) + timedelta(days=365)

            bits_by_date = self._load_bits_by_date_for_range(
                instructor_id,
                start_date,
                end_date,
            )
            windows: list[dict[str, Any]] = []
            for current_date in sorted(bits_by_date):
                bits = bits_by_date[current_date]
                if bits:
                    day_windows = availability_service_module().windows_from_bits(bits)
                    for start, end in day_windows:
                        windows.append(
                            {
                                "instructor_id": instructor_id,
                                "specific_date": current_date,
                                "start_time": start,
                                "end_time": end,
                            }
                        )
            return windows
        except Exception as error:
            logger.error("Error retrieving all availability: %s", str(error))
            raise

    @BaseService.measure_operation("get_week_windows_as_slot_like")
    def get_week_windows_as_slot_like(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """
        Get availability windows as slot-like objects for compatibility.

        Returns list of dicts with specific_date (date), start_time (time), end_time (time).
        """
        bits_by_date = self._load_bits_by_date_for_range(instructor_id, start_date, end_date)
        windows: list[dict[str, Any]] = []
        for current_date in sorted(bits_by_date):
            bits = bits_by_date[current_date]
            if bits:
                day_windows_str: list[
                    tuple[str, str]
                ] = availability_service_module().windows_from_bits(bits)
                for start_str, end_str in day_windows_str:
                    windows.append(
                        {
                            "specific_date": current_date,
                            "start_time": string_to_time(start_str),
                            "end_time": string_to_time(end_str),
                        }
                    )
        return windows
