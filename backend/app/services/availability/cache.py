"""Cache management internals for availability data."""

from __future__ import annotations

from datetime import date, time, timedelta
import logging
from typing import Any, Optional

from ...utils.time_helpers import string_to_time
from .mixin_base import AvailabilityMixinBase
from .types import (
    DayBitmaps,
    SlotSnapshot,
    TimeSlotResponse,
    WeekAvailabilityResult,
    availability_service_module,
)

logger = logging.getLogger(__name__)


class AvailabilityCacheMixin(AvailabilityMixinBase):
    """Cache management internals for availability data."""

    def _persist_week_cache(
        self,
        *,
        instructor_id: str,
        week_start: date,
        week_map: dict[str, list[TimeSlotResponse]],
        cache_keys: Optional[tuple[str, str]] = None,
    ) -> None:
        if not self.cache_service:
            return

        map_key: str
        composite_key: str
        if cache_keys:
            map_key, composite_key = cache_keys
        else:
            map_key, composite_key = self._week_cache_keys(instructor_id, week_start)

        ttl_seconds = self._week_cache_ttl_seconds(instructor_id, week_start)
        payload = {"week_map": week_map, "_metadata": []}
        self.cache_service.set_json(composite_key, payload, ttl=ttl_seconds)
        self.cache_service.set_json(map_key, week_map, ttl=ttl_seconds)

    def _update_bitmap_caches_after_save(
        self,
        *,
        instructor_id: str,
        monday: date,
        after_map: dict[date, DayBitmaps],
    ) -> None:
        if not self.cache_service:
            return
        try:
            week_map_after, _ = self._week_map_from_bits(
                {day: bitmaps.bits for day, bitmaps in after_map.items()},
                include_snapshots=False,
            )
            self._persist_week_cache(
                instructor_id=instructor_id,
                week_start=monday,
                week_map=week_map_after,
            )
        except Exception as cache_error:
            logger.warning("Cache update error after bitmap save: %s", cache_error)

    def _week_cache_keys(self, instructor_id: str, week_start: date) -> tuple[str, str]:
        if self.cache_service is None:
            raise RuntimeError("Cache service required for week cache keys")
        base_key = self.cache_service.key_builder.build(
            "availability", "week", instructor_id, week_start
        )
        return base_key, f"{base_key}:with_slots"

    def _week_cache_ttl_seconds(self, instructor_id: str, week_start: date) -> int:
        if self.cache_service is None:
            raise RuntimeError("Cache service required for week cache TTL calculation")
        today = availability_service_module().get_user_today_by_id(instructor_id, self.db)
        tier = "hot" if week_start >= today else "warm"
        return int(self.cache_service.TTL_TIERS.get(tier, self.cache_service.TTL_TIERS["warm"]))

    def _extract_cached_week_result(
        self,
        payload: Any,
        *,
        include_slots: bool,
    ) -> Optional[WeekAvailabilityResult]:
        if payload is None:
            return None

        map_candidate: Any = payload
        if isinstance(payload, dict):
            payload["_metadata"] = self._coerce_metadata_list(payload.get("_metadata"))
            if "map" in payload:
                map_candidate = payload.get("map")
            elif "week_map" in payload:
                map_candidate = payload.get("week_map")

        week_map = self._sanitize_week_map(map_candidate)
        if week_map is None:
            return None

        windows: list[tuple[date, time, time]] = []
        if not include_slots:
            return WeekAvailabilityResult(week_map=week_map, windows=windows)

        slot_snapshots: list[SlotSnapshot] = []
        for iso_date, entries in week_map.items():
            try:
                day = date.fromisoformat(iso_date)
            except ValueError:
                continue
            for entry in entries:
                start = entry.get("start_time")
                end = entry.get("end_time")
                if start is None or end is None:
                    continue
                try:
                    slot_snapshots.append(
                        SlotSnapshot(
                            specific_date=day,
                            start_time=string_to_time(str(start)),
                            end_time=string_to_time(str(end)),
                            created_at=None,
                            updated_at=None,
                        )
                    )
                except ValueError:
                    continue

        for snapshot in slot_snapshots:
            windows.append((snapshot.specific_date, snapshot.start_time, snapshot.end_time))
        return WeekAvailabilityResult(week_map=week_map, windows=windows)

    @staticmethod
    def _coerce_metadata_list(metadata: Any) -> list[Any]:
        if isinstance(metadata, list):
            return metadata
        if isinstance(metadata, dict):
            return [metadata]
        return []

    def _sanitize_week_map(self, payload: Any) -> Optional[dict[str, list[TimeSlotResponse]]]:
        if not isinstance(payload, dict):
            return None

        clean_map: dict[str, list[TimeSlotResponse]] = {}
        for iso_date, slots in payload.items():
            if iso_date == "_metadata":
                continue
            if not isinstance(iso_date, str) or not isinstance(slots, list):
                return None

            normalized: list[TimeSlotResponse] = []
            for slot in slots:
                if not isinstance(slot, dict):
                    return None
                start = slot.get("start_time")
                end = slot.get("end_time")
                if start is None or end is None:
                    return None
                normalized.append(
                    TimeSlotResponse(
                        start_time=str(start),
                        end_time=str(end),
                    )
                )

            clean_map[iso_date] = normalized

        return clean_map

    def _invalidate_availability_caches(self, instructor_id: str, dates: list[date]) -> None:
        """
        Invalidate caches for affected dates using enhanced cache service.

        Note: Ghost keys removed in v123 cleanup. The cache service's
        invalidate_instructor_availability() handles all active patterns:
        - avail:*:{instructor_id}:*
        - week:*:{instructor_id}:*
        - con:*:{instructor_id}:*
        - public_availability:{instructor_id}:*
        """
        if self.cache_service:
            try:
                self.cache_service.invalidate_instructor_availability(instructor_id, dates)
            except Exception as cache_error:
                logger.warning("Cache invalidation failed: %s", cache_error)

        weeks = {target_date - timedelta(days=target_date.weekday()) for target_date in dates}
        if self.cache_service:
            for week_start in weeks:
                try:
                    map_key, composite_key = self._week_cache_keys(instructor_id, week_start)
                    self.invalidate_cache(map_key, composite_key)
                except Exception as cache_error:
                    logger.warning(
                        "Failed to invalidate availability cache keys for week %s: %s",
                        week_start,
                        cache_error,
                    )
