"""Week save orchestration for availability bitmap persistence."""

from __future__ import annotations

from datetime import date, time, timedelta
import logging
from typing import Any, cast

from ...core.exceptions import ConflictException
from ...monitoring.availability_perf import (
    WEEK_SAVE_ENDPOINT,
    availability_perf_span,
    estimate_payload_size_bytes,
)
from ...schemas.availability_window import ScheduleItem, WeekSpecificScheduleCreate
from ...utils.time_helpers import string_to_time
from ..base import BaseService
from .mixin_base import AvailabilityMixinBase
from .types import (
    AvailabilityWindowInput,
    PreparedWeek,
    ProcessedSlot,
    TimeSlotResponse,
    availability_service_module,
)

logger = logging.getLogger(__name__)


class AvailabilityWeekSaveMixin(AvailabilityMixinBase):
    """Week save orchestration: validation, parsing, and cache warming."""

    def _calculate_week_dates(self, monday: date) -> list[date]:
        """Calculate all dates for a week starting from Monday."""
        return [monday + timedelta(days=offset) for offset in range(7)]

    def _validate_and_parse_week_data(
        self, week_data: WeekSpecificScheduleCreate, instructor_id: str
    ) -> tuple[date, list[date], dict[date, list[ProcessedSlot]]]:
        """Validate week data and parse into organized structure."""
        monday = self._determine_week_start(week_data, instructor_id)
        week_dates = self._calculate_week_dates(monday)
        schedule_by_date = self._group_schedule_by_date(week_data.schedule, instructor_id)
        return monday, week_dates, schedule_by_date

    def _prepare_slots_for_creation(
        self,
        instructor_id: str,
        week_dates: list[date],
        schedule_by_date: dict[date, list[ProcessedSlot]],
        ignore_existing: bool = False,
    ) -> PreparedWeek:
        """Convert time slots to database-ready format."""
        self._validate_no_overlaps(instructor_id, schedule_by_date, ignore_existing=True)
        windows_to_create: list[AvailabilityWindowInput] = []
        service_module = availability_service_module()
        instructor_today = service_module.get_user_today_by_id(instructor_id, self.db)
        affected_dates: set[date] = set()

        for target_date in sorted(schedule_by_date.keys()):
            if not service_module.ALLOW_PAST and target_date < instructor_today:
                continue

            windows = schedule_by_date.get(target_date, [])
            if not windows:
                continue

            affected_dates.add(target_date)
            for window in windows:
                window_input = cast(
                    AvailabilityWindowInput,
                    {
                        "instructor_id": instructor_id,
                        "specific_date": target_date,
                        "start_time": window["start_time"],
                        "end_time": window["end_time"],
                    },
                )
                windows_to_create.append(window_input)

        return PreparedWeek(windows=windows_to_create, affected_dates=affected_dates)

    async def _warm_cache_after_save(
        self,
        instructor_id: str,
        monday: date,
        affected_dates: set[date],
        window_count: int,
    ) -> dict[str, list[TimeSlotResponse]]:
        """
        Warm cache with new availability data.

        Cache failures do not prevent the operation from succeeding.
        """
        self.db.expire_all()
        cache_dates = set(affected_dates)
        cache_dates.add(monday)
        cache_dates_sorted = sorted(cache_dates)
        week_starts = {day - timedelta(days=day.weekday()) for day in cache_dates_sorted} | {monday}
        week_starts_sorted = sorted(week_starts)

        if self.cache_service:
            try:
                from ..cache_strategies import CacheWarmingStrategy

                warmer = CacheWarmingStrategy(self.cache_service, self.db)
                updated_availability: dict[str, list[TimeSlotResponse]] | None = None

                for week_start in week_starts_sorted:
                    warmed = await warmer.warm_with_verification(
                        instructor_id, week_start, expected_window_count=None
                    )
                    if week_start == monday:
                        updated_availability = warmed

                logger.debug(
                    "Cache warmed successfully for instructor %s across %d week(s), window_count=%d",
                    instructor_id,
                    len(week_starts_sorted),
                    window_count,
                )
                if updated_availability is not None:
                    return updated_availability
                return self.get_week_availability(instructor_id, monday)
            except ImportError:
                logger.warning("Cache strategies not available, using direct fetch")
            except Exception as cache_error:
                logger.warning(
                    "Cache warming failed for instructor %s: %s", instructor_id, cache_error
                )

            self._invalidate_availability_caches(instructor_id, cache_dates_sorted)
            return self.get_week_availability(instructor_id, monday)

        logger.debug(
            "No cache service available, fetching availability directly for instructor %s",
            instructor_id,
        )
        return self.get_week_availability(instructor_id, monday)

    @BaseService.measure_operation("save_week_availability")
    async def save_week_availability(
        self,
        instructor_id: str,
        week_data: WeekSpecificScheduleCreate,
        *,
        actor: Any | None = None,
    ) -> dict[str, Any]:
        """Save availability for specific dates in a week."""
        endpoint = WEEK_SAVE_ENDPOINT
        payload_size = estimate_payload_size_bytes(week_data)
        self.log_operation(
            "save_week_availability",
            instructor_id=instructor_id,
            clear_existing=week_data.clear_existing,
            schedule_count=len(week_data.schedule),
        )

        with availability_perf_span(
            "service.save_week_availability",
            endpoint=endpoint,
            instructor_id=instructor_id,
            payload_size_bytes=payload_size,
        ):
            monday, _week_dates, schedule_by_date = self._validate_and_parse_week_data(
                week_data, instructor_id
            )
            client_version = getattr(week_data, "version", None) or getattr(
                week_data, "base_version", None
            )
            try:
                if client_version and not getattr(week_data, "override", False):
                    expected = self.compute_week_version(
                        instructor_id, monday, monday + timedelta(days=6)
                    )
                    if client_version != expected:
                        raise ConflictException("Week has changed; please refresh and retry")
            except ConflictException:
                raise
            except Exception as error:
                # This optimistic version check is intentionally best-effort so stale version
                # metadata never blocks a valid save when the read path cannot compute it.
                logger.debug("Version check skipped: %s", error)

            self._validate_no_overlaps(
                instructor_id,
                schedule_by_date,
                ignore_existing=bool(week_data.clear_existing),
            )

            windows_by_day: dict[date, list[tuple[str, str]]] = {}
            for target_date, slots in schedule_by_date.items():
                normalized: list[tuple[str, str]] = []
                for slot in slots:
                    start_time = slot["start_time"].strftime("%H:%M:%S")
                    end_time = slot["end_time"].strftime("%H:%M:%S")
                    normalized.append((start_time, end_time))
                if normalized:
                    windows_by_day[target_date] = normalized

            save_result = self.save_week_bits(
                instructor_id=instructor_id,
                week_start=monday,
                windows_by_day=windows_by_day,
                base_version=client_version,
                override=getattr(week_data, "override", False),
                clear_existing=bool(week_data.clear_existing),
                actor=actor,
            )
            edited_dates = {date.fromisoformat(day_str) for day_str in save_result.edited_dates}
            return await self._warm_cache_after_save(
                instructor_id,
                monday,
                edited_dates,
                save_result.windows_created,
            )

    def _determine_week_start(
        self, week_data: WeekSpecificScheduleCreate, instructor_id: str
    ) -> date:
        """Determine the Monday of the week from schedule data."""
        if week_data.week_start:
            week_start = week_data.week_start
            if isinstance(week_start, date):
                return week_start
            return date.fromisoformat(str(week_start))
        if week_data.schedule:
            first_date = min(date.fromisoformat(slot.date) for slot in week_data.schedule)
            return first_date - timedelta(days=first_date.weekday())

        instructor_today = availability_service_module().get_user_today_by_id(
            instructor_id, self.db
        )
        return instructor_today - timedelta(days=instructor_today.weekday())

    def _group_schedule_by_date(
        self, schedule: list[ScheduleItem], instructor_id: str
    ) -> dict[date, list[ProcessedSlot]]:
        """Group schedule entries by date, normalizing overnight spans."""
        schedule_by_date: dict[date, list[ProcessedSlot]] = {}
        service_module = availability_service_module()
        instructor_today = service_module.get_user_today_by_id(instructor_id, self.db)

        for slot in schedule:
            slot_date = date.fromisoformat(slot.date)
            start_time_obj = string_to_time(slot.start_time)
            end_time_obj = string_to_time(slot.end_time)
            if not service_module.ALLOW_PAST and slot_date < instructor_today:
                logger.warning(
                    "Skipping past date: %s (instructor today: %s)", slot_date, instructor_today
                )
                continue

            self._append_normalized_slot(
                schedule_by_date, slot_date, start_time_obj, end_time_obj, instructor_today
            )

        return schedule_by_date

    def _append_normalized_slot(
        self,
        schedule_by_date: dict[date, list[ProcessedSlot]],
        target_date: date,
        start_time_obj: time,
        end_time_obj: time,
        instructor_today: date,
    ) -> None:
        if start_time_obj == end_time_obj:
            self._ensure_valid_interval(target_date, start_time_obj, end_time_obj)
            return

        is_midnight_close = end_time_obj == time(0, 0) and start_time_obj != time(0, 0)
        if start_time_obj > end_time_obj and not is_midnight_close:
            self._append_normalized_slot(
                schedule_by_date, target_date, start_time_obj, time(0, 0), instructor_today
            )
            self._append_normalized_slot(
                schedule_by_date,
                target_date + timedelta(days=1),
                time(0, 0),
                end_time_obj,
                instructor_today,
            )
            return

        if not availability_service_module().ALLOW_PAST and target_date < instructor_today:
            logger.warning(
                "Skipping past date: %s (instructor today: %s)", target_date, instructor_today
            )
            return

        schedule_by_date.setdefault(target_date, []).append(
            ProcessedSlot(start_time=start_time_obj, end_time=end_time_obj)
        )
