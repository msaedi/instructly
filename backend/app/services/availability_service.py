# backend/app/services/availability_service.py
"""
Availability Service for InstaInstru Platform

This service handles all availability-related business logic.

"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, NamedTuple, Optional, Tuple, TypedDict, cast

from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.exceptions import (
    AvailabilityOverlapException,
    ConflictException,
    NotFoundException,
    RepositoryException,
)
from ..core.timezone_utils import get_user_today_by_id
from ..models.audit_log import AuditLog
from ..models.availability import AvailabilitySlot, BlackoutDate
from ..monitoring.availability_perf import (
    WEEK_GET_ENDPOINT,
    WEEK_SAVE_ENDPOINT,
    availability_perf_span,
    estimate_payload_size_bytes,
)
from ..repositories.availability_day_repository import AvailabilityDayRepository
from ..repositories.factory import RepositoryFactory
from ..schemas.availability_window import (
    BlackoutDateCreate,
    SpecificDateAvailabilityCreate,
    WeekSpecificScheduleCreate,
)
from ..utils.bitset import bits_from_windows, new_empty_bits, windows_from_bits
from ..utils.time_helpers import time_to_string
from .audit_redaction import redact
from .base import BaseService

# TYPE_CHECKING import to avoid circular dependencies
if TYPE_CHECKING:
    from ..repositories.audit_repository import AuditRepository
    from ..repositories.availability_repository import AvailabilityRepository
    from ..repositories.bulk_operation_repository import BulkOperationRepository
    from ..repositories.conflict_checker_repository import ConflictCheckerRepository
    from .cache_service import CacheService

logger = logging.getLogger(__name__)

AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}
ALLOW_PAST = os.getenv("AVAILABILITY_ALLOW_PAST", "true").lower() in {"1", "true", "yes"}


def build_availability_idempotency_key(
    instructor_id: str, week_start: date, event_type: str, version: str
) -> str:
    """Compose a deterministic idempotency key for availability events."""
    return f"avail:{instructor_id}:{week_start.isoformat()}:{event_type}:{version}"


# Type definitions for better type safety
class ScheduleSlotInput(TypedDict):
    """Input format for schedule slots from API."""

    date: str
    start_time: str
    end_time: str


class ProcessedSlot(TypedDict):
    """Internal format after processing schedule slots."""

    start_time: time
    end_time: time


class AvailabilitySlotInput(TypedDict):
    """Normalized slot ready for persistence."""

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
    slots: list[AvailabilitySlot | SlotSnapshot]


class PreparedWeek(NamedTuple):
    slots: list[AvailabilitySlotInput]
    affected_dates: set[date]


class SaveWeekBitsResult(NamedTuple):
    rows_written: int
    days_written: int
    skipped_past_window: int
    skipped_past_forbidden: int
    bits_by_day: Dict[date, bytes]
    version: str
    written_dates: List[date]
    skipped_dates: List[date]
    past_written_dates: List[date]
    edited_dates: List[str]


class AvailabilityService(BaseService):
    """
    Service layer for availability operations.

    Works directly with AvailabilitySlot objects.
    """

    audit_repository: "AuditRepository"

    def __init__(
        self,
        db: Session,
        cache_service: Optional["CacheService"] = None,
        repository: Optional["AvailabilityRepository"] = None,
        bulk_repository: Optional["BulkOperationRepository"] = None,
        conflict_repository: Optional["ConflictCheckerRepository"] = None,
    ):
        """Initialize availability service with optional cache and repositories."""
        super().__init__(db, cache=cache_service)
        self.cache_service = cache_service

        # Initialize repositories
        self.repository = repository or RepositoryFactory.create_availability_repository(db)
        self.bulk_repository = (
            bulk_repository or RepositoryFactory.create_bulk_operation_repository(db)
        )
        self.conflict_repository = (
            conflict_repository or RepositoryFactory.create_conflict_checker_repository(db)
        )
        self.event_outbox_repository = RepositoryFactory.create_event_outbox_repository(db)
        self.audit_repository = RepositoryFactory.create_audit_repository(db)

    # ----- V2 (bitmaps) helpers -----

    def _bitmap_repo(self) -> AvailabilityDayRepository:
        return AvailabilityDayRepository(self.db)

    @BaseService.measure_operation("get_week_bits")
    def get_week_bits(
        self, instructor_id: str, week_start: date, *, use_cache: bool = True
    ) -> Dict[date, bytes]:
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
                logger.warning(f"Cache read error for week bits: {cache_error}")

        repo = self._bitmap_repo()
        rows = repo.get_week_rows(instructor_id, monday)
        existing = {row.day_date: row.bits for row in rows}
        bits_by_day: Dict[date, bytes] = {}
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
                logger.warning(f"Cache write error for week bits: {cache_error}")

        return bits_by_day

    @BaseService.measure_operation("compute_week_version_bits")
    def compute_week_version_bits(self, bits_by_day: Dict[date, bytes]) -> str:
        """Stable SHA1 of concatenated 7×bits ordered chronologically."""
        if not bits_by_day:
            concat = new_empty_bits() * 7
        else:
            anchor = min(bits_by_day.keys())
            monday = anchor - timedelta(days=anchor.weekday())
            ordered_days = [monday + timedelta(days=i) for i in range(7)]
            concat = b"".join(bits_by_day.get(day, new_empty_bits()) for day in ordered_days)
        return hashlib.sha1(concat).hexdigest()

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

    @BaseService.measure_operation("save_week_bits")
    def save_week_bits(
        self,
        instructor_id: str,
        week_start: date,
        windows_by_day: Dict[date, List[Tuple[str, str]]],
        base_version: Optional[str],
        override: bool,
        clear_existing: bool,
        *,
        actor: Any | None = None,
    ) -> SaveWeekBitsResult:
        """
        Persist week availability using bitmap storage.

        Returns:
            SaveWeekBitsResult with persistence metadata.
        """
        current = self.get_week_bits(instructor_id, week_start, use_cache=False)
        allow_past = os.getenv("AVAILABILITY_ALLOW_PAST", "true").lower() in {"1", "true", "yes"}
        server_version = self.compute_week_version_bits(current)

        if base_version and (base_version != server_version) and not override:
            raise ConflictException("Week has changed; please refresh and retry")

        items: List[Tuple[date, bytes]] = []
        instructor_today = get_user_today_by_id(instructor_id, self.db)
        perf_debug = os.getenv("AVAILABILITY_PERF_DEBUG", "0").lower() in {"1", "true", "yes"}
        window_days = max(0, settings.past_edit_window_days)
        past_cutoff: Optional[date] = None
        if window_days > 0:
            past_cutoff = instructor_today - timedelta(days=window_days)

        changed_dates: List[date] = []
        past_written_dates: List[date] = []
        skipped_window_dates: List[date] = []
        skipped_forbidden_dates: List[date] = []

        for offset in range(7):
            day = week_start + timedelta(days=offset)
            has_payload = day in windows_by_day
            previous_bits = current.get(day, new_empty_bits())
            day_windows = windows_by_day.get(day, [])

            if not allow_past and day < instructor_today:
                bits = previous_bits
                if has_payload or clear_existing:
                    skipped_forbidden_dates.append(day)
            else:
                should_skip = False
                window_skip = False
                if past_cutoff and day < past_cutoff and (has_payload or clear_existing):
                    should_skip = True
                    window_skip = True

                if should_skip:
                    bits = previous_bits
                    if window_skip:
                        skipped_window_dates.append(day)
                    else:
                        skipped_forbidden_dates.append(day)
                elif not clear_existing and not has_payload:
                    bits = previous_bits
                else:
                    bits = bits_from_windows(day_windows) if day_windows else new_empty_bits()

            bits_changed = bits != previous_bits
            items.append((day, bits))
            if perf_debug:
                logger.debug(
                    "bitmap_write day=%s override=%s bits_changed=%s",
                    day.isoformat(),
                    override,
                    "true" if bits_changed else "false",
                )
            if bits_changed:
                changed_dates.append(day)
                if day < instructor_today:
                    past_written_dates.append(day)

        repo = self._bitmap_repo()
        rows_written = repo.upsert_week(instructor_id, items)
        after = self.get_week_bits(instructor_id, week_start, use_cache=False)
        if self.cache_service:
            try:
                week_map_after, _ = self._week_map_from_bits(
                    after,
                    include_snapshots=False,
                )
                self._persist_week_cache(
                    instructor_id=instructor_id,
                    week_start=week_start,
                    week_map=week_map_after,
                )
            except Exception as cache_error:
                logger.warning(f"Cache update error after bitmap save: {cache_error}")
        new_version = self.compute_week_version_bits(after)
        days_written = len(changed_dates)
        skipped_past_window = len(skipped_window_dates)
        skipped_past_forbidden = len(skipped_forbidden_dates)

        audit_dates = sorted(
            set(changed_dates) | set(skipped_window_dates) | set(skipped_forbidden_dates)
        )

        def _windows_payload(
            bits_map: Dict[date, bytes], target_dates: List[date]
        ) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for target in target_dates:
                result[target.isoformat()] = [
                    {"start_time": start, "end_time": end}
                    for start, end in windows_from_bits(bits_map.get(target, new_empty_bits()))
                ]
            return result

        if audit_dates and AUDIT_ENABLED:
            before_payload = {
                "week_start": week_start.isoformat(),
                "windows": _windows_payload(current, audit_dates),
            }
            after_payload = {
                "week_start": week_start.isoformat(),
                "windows": _windows_payload(after, audit_dates),
                "edited_dates": [d.isoformat() for d in changed_dates],
                "skipped_dates": [d.isoformat() for d in skipped_window_dates],
                "skipped_forbidden_dates": [d.isoformat() for d in skipped_forbidden_dates],
                "historical_edit": bool(
                    past_written_dates or skipped_window_dates or skipped_forbidden_dates
                ),
                "skipped_past_window": bool(skipped_window_dates),
                "skipped_past_forbidden": bool(skipped_forbidden_dates),
                "days_written": days_written,
            }
            try:
                self._write_availability_audit(
                    instructor_id,
                    week_start,
                    "save_week_bitmap",
                    actor=actor,
                    before=before_payload,
                    after=after_payload,
                )
            except Exception as audit_err:
                logger.warning(
                    "Audit write failed for bitmap save_week_bits",
                    extra={
                        "instructor_id": instructor_id,
                        "week_start": week_start.isoformat(),
                        "error": str(audit_err),
                    },
                )

        event_dates = [
            d
            for d in changed_dates
            if not (settings.suppress_past_availability_events and d < instructor_today)
        ]
        if event_dates:
            try:
                prepared = PreparedWeek(slots=[], affected_dates=set(event_dates))
                self._enqueue_week_save_event(
                    instructor_id,
                    week_start,
                    week_dates=[week_start + timedelta(days=i) for i in range(7)],
                    prepared=prepared,
                    created_count=days_written,
                    deleted_count=0,
                    clear_existing=bool(clear_existing),
                )
            except Exception as enqueue_err:
                logger.warning(
                    "Outbox enqueue failed for bitmap save_week_bits",
                    extra={
                        "instructor_id": instructor_id,
                        "week_start": week_start.isoformat(),
                        "error": str(enqueue_err),
                    },
                )

        edited_date_strings = [d.isoformat() for d in sorted(set(changed_dates))]

        return SaveWeekBitsResult(
            rows_written=rows_written,
            days_written=days_written,
            skipped_past_window=skipped_past_window,
            skipped_past_forbidden=skipped_past_forbidden,
            bits_by_day=after,
            version=new_version,
            written_dates=changed_dates,
            skipped_dates=skipped_window_dates,
            past_written_dates=past_written_dates,
            edited_dates=edited_date_strings,
        )

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
        """Persist outbox entry describing week availability save operation."""
        self.repository.flush()
        week_end = week_start + timedelta(days=6)
        version = self.compute_week_version(instructor_id, week_start, week_end)
        affected_dates = list(prepared.affected_dates)
        if settings.suppress_past_availability_events:
            today = get_user_today_by_id(instructor_id, self.db)
            affected_dates = [d for d in affected_dates if d >= today]
        if not affected_dates:
            logger.info(
                "Skipping availability.week_saved event due to past-only edits",
                extra={
                    "instructor_id": instructor_id,
                    "week_start": week_start.isoformat(),
                },
            )
            return
        affected = {d.isoformat() for d in affected_dates}
        if clear_existing and not affected:
            affected = {d.isoformat() for d in week_dates}

        payload = {
            "instructor_id": instructor_id,
            "week_start": week_start.isoformat(),
            "affected_dates": sorted(affected),
            "clear_existing": bool(clear_existing),
            "created_slots": created_count,
            "deleted_slots": deleted_count,
            "version": version,
        }
        aggregate_id = f"{instructor_id}:{week_start.isoformat()}"
        key = build_availability_idempotency_key(
            instructor_id, week_start, "availability.week_saved", version
        )
        self.event_outbox_repository.enqueue(
            event_type="availability.week_saved",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=key,
        )

    def _resolve_actor_payload(
        self, actor: Any | None, default_role: str = "instructor"
    ) -> dict[str, Any]:
        """Normalize actor metadata for audit logging."""
        if actor is None:
            return {"role": default_role}

        if isinstance(actor, dict):
            actor_id = actor.get("id") or actor.get("actor_id") or actor.get("user_id")
            raw_role = actor.get("role") or actor.get("actor_role") or actor.get("role_name")
            resolved_role = str(raw_role) if raw_role is not None else default_role
            return {"id": actor_id, "role": resolved_role}

        actor_id = getattr(actor, "id", None)
        role_value: Any = getattr(actor, "role", None) or getattr(actor, "role_name", None)
        if role_value is None:
            roles = getattr(actor, "roles", None)
            if isinstance(roles, (list, tuple)):
                for role_obj in roles:
                    candidate = getattr(role_obj, "name", None)
                    if candidate:
                        role_value = candidate
                        break
        if role_value is None:
            role_value = default_role
        return {"id": actor_id, "role": str(role_value)}

    def _build_week_audit_payload(
        self,
        instructor_id: str,
        week_start: date,
        dates: list[date],
        *,
        clear_existing: bool,
        created: int = 0,
        deleted: int = 0,
        slot_cache: dict[date, list[AvailabilitySlot]] | None = None,
    ) -> dict[str, Any]:
        """Construct a compact snapshot for audit logging."""
        unique_dates = sorted({d for d in dates})
        slot_counts: dict[str, int] = {}
        for target in unique_dates:
            if slot_cache is not None and target in slot_cache:
                slots_for_day = slot_cache[target]
            else:
                slots_for_day = self.repository.get_slots_by_date(instructor_id, target)
                if slot_cache is not None:
                    slot_cache[target] = list(slots_for_day)
            slot_counts[target.isoformat()] = len(slots_for_day)

        week_end = week_start + timedelta(days=6)
        payload: dict[str, Any] = {
            "week_start": week_start.isoformat(),
            "affected_dates": [d.isoformat() for d in unique_dates],
            "slot_counts": slot_counts,
            "clear_existing": bool(clear_existing),
            "version": self.compute_week_version(instructor_id, week_start, week_end),
        }
        if created or deleted:
            payload["delta"] = {"created": created, "deleted": deleted}
        return redact(payload) or {}

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
        """Persist audit entry for availability changes."""
        actor_payload = self._resolve_actor_payload(actor, default_role=default_role)
        audit_entry = AuditLog.from_change(
            entity_type="availability",
            entity_id=f"{instructor_id}:{week_start.isoformat()}",
            action=action,
            actor=actor_payload,
            before=before,
            after=after,
        )
        if AUDIT_ENABLED:
            self.audit_repository.write(audit_entry)

    @BaseService.measure_operation("get_availability_for_date")
    def get_availability_for_date(
        self, instructor_id: str, target_date: date
    ) -> Optional[dict[str, Any]]:
        """
        Get availability for a specific date using cache-aside pattern.

        Args:
            instructor_id: The instructor ID
            target_date: The specific date

        Returns:
            Availability data for the date or None if no slots
        """
        # Try cache first (cache-aside pattern)
        if self.cache_service:
            try:
                # Use the new date range caching for single dates
                cached = self.cache_service.get_instructor_availability_date_range(
                    instructor_id, target_date, target_date
                )
                if cached is not None and len(cached) > 0:
                    return cached[0]  # Return the single date's data
            except Exception as cache_error:
                logger.warning(f"Cache error for date availability: {cache_error}")

        # Cache miss - query database
        try:
            slots = self.repository.get_slots_by_date(instructor_id, target_date)
        except RepositoryException as e:
            logger.error(f"Repository error getting availability: {e}")
            return None

        if not slots:
            return None

        result = {
            "date": target_date.isoformat(),
            "slots": [
                TimeSlotResponse(
                    start_time=time_to_string(slot.start_time),
                    end_time=time_to_string(slot.end_time),
                )
                for slot in slots
            ],
        }

        # Cache the result with 5-minute TTL for better performance
        if self.cache_service:
            try:
                self.cache_service.cache_instructor_availability_date_range(
                    instructor_id, target_date, target_date, [result]
                )
            except Exception as cache_error:
                logger.warning(f"Failed to cache date availability: {cache_error}")

        return result

    @BaseService.measure_operation("get_availability_summary")
    def get_availability_summary(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> dict[str, int]:
        """
        Get summary of availability (slot counts) for date range.

        Args:
            instructor_id: The instructor ID
            start_date: Start of range
            end_date: End of range

        Returns:
            Dict mapping date strings to slot counts
        """
        try:
            return self.repository.get_availability_summary(instructor_id, start_date, end_date)
        except RepositoryException as e:
            logger.error(f"Error getting availability summary: {e}")
            return {}

    @BaseService.measure_operation("compute_week_version")
    def compute_week_version(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        slots: Optional[list[AvailabilitySlot | SlotSnapshot]] = None,
    ) -> str:
        """Compute a deterministic week version using bitmap contents only."""
        week_start = start_date - timedelta(days=start_date.weekday())
        bits_by_day = self.get_week_bits(instructor_id, week_start)
        return self.compute_week_version_bits(bits_by_day)

    @BaseService.measure_operation("get_week_last_modified")
    def get_week_last_modified(
        self,
        instructor_id: str,
        start_date: date,
        end_date: date,
        slots: Optional[list[AvailabilitySlot | SlotSnapshot]] = None,
    ) -> Optional[datetime]:
        """Return last-modified timestamp derived from bitmap rows only."""
        week_start = start_date - timedelta(days=start_date.weekday())
        return self.get_week_bitmap_last_modified(instructor_id, week_start)

    @BaseService.measure_operation("get_week_availability")
    def get_week_availability(
        self, instructor_id: str, start_date: date
    ) -> dict[str, list[TimeSlotResponse]]:
        result = self._get_week_availability_common(
            instructor_id,
            start_date,
            allow_cache_read=True,
            include_slots=False,
        )
        return result.week_map

    @BaseService.measure_operation("get_week_availability_with_slots")
    def get_week_availability_with_slots(
        self, instructor_id: str, start_date: date
    ) -> WeekAvailabilityResult:
        return self._get_week_availability_common(
            instructor_id,
            start_date,
            allow_cache_read=True,
            include_slots=True,
        )

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
                            return WeekAvailabilityResult(week_map=week_map, slots=[])

                except Exception as cache_error:
                    logger.warning(f"Cache error for week availability: {cache_error}")

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
                    logger.warning(f"Failed to cache week availability: {cache_error}")

            if perf:
                perf(cache_used=cache_used)

            slots_union = cast(list[AvailabilitySlot | SlotSnapshot], slot_snapshots)
            return WeekAvailabilityResult(week_map=week_map, slots=slots_union)

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

    def _week_cache_keys(self, instructor_id: str, week_start: date) -> tuple[str, str]:
        assert self.cache_service is not None
        base_key = self.cache_service.key_builder.build(
            "availability", "week", instructor_id, week_start
        )
        return base_key, f"{base_key}:with_slots"

    def _week_cache_ttl_seconds(self, instructor_id: str, week_start: date) -> int:
        assert self.cache_service is not None
        today = get_user_today_by_id(instructor_id, self.db)
        tier = "hot" if week_start >= today else "warm"
        return self.cache_service.TTL_TIERS.get(tier, self.cache_service.TTL_TIERS["warm"])

    def _extract_cached_week_result(
        self,
        payload: Any,
        *,
        include_slots: bool,
    ) -> Optional[WeekAvailabilityResult]:
        if payload is None:
            return None

        map_candidate: Any = payload
        slots_payload: Any = None

        if isinstance(payload, dict):
            payload["_metadata"] = self._coerce_metadata_list(payload.get("_metadata"))
            if "map" in payload:
                map_candidate = payload.get("map")
            elif "week_map" in payload:
                map_candidate = payload.get("week_map")

            if "slots" in payload:
                slots_payload = payload.get("slots")
            elif "slot_meta" in payload:
                slots_payload = payload.get("slot_meta")

        week_map = self._sanitize_week_map(map_candidate)
        if week_map is None:
            return None

        if not include_slots:
            return WeekAvailabilityResult(week_map=week_map, slots=[])

        slot_snapshots: list[SlotSnapshot]
        if isinstance(slots_payload, list):
            deserialized = self._deserialize_slot_meta(slots_payload)
            slot_snapshots = cast(list[SlotSnapshot], deserialized)
        else:
            slot_snapshots = []
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
                                start_time=time.fromisoformat(str(start)),
                                end_time=time.fromisoformat(str(end)),
                                created_at=None,
                                updated_at=None,
                            )
                        )
                    except ValueError:
                        continue

        slots_union = cast(list[AvailabilitySlot | SlotSnapshot], slot_snapshots)
        return WeekAvailabilityResult(week_map=week_map, slots=slots_union)

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

    def _week_map_from_bits(
        self,
        bits_by_day: Dict[date, bytes],
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
                            start_time=time.fromisoformat(start_str),
                            end_time=time.fromisoformat(end_str),
                            created_at=None,
                            updated_at=None,
                        )
                    )
            week_schedule[date_str] = entries
        return week_schedule, snapshots

    @staticmethod
    def _bits_from_week_map(
        week_map: dict[str, list[TimeSlotResponse]],
        week_start: date,
    ) -> Dict[date, bytes]:
        monday = week_start - timedelta(days=week_start.weekday())
        bits_by_day: Dict[date, bytes] = {}
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

    @staticmethod
    def _serialize_slot_meta(slots: list[AvailabilitySlot]) -> list[dict[str, Optional[str]]]:
        meta: list[dict[str, Optional[str]]] = []
        for slot in slots:
            meta.append(
                {
                    "specific_date": slot.specific_date.isoformat(),
                    "start_time": slot.start_time.isoformat(),
                    "end_time": slot.end_time.isoformat(),
                    "created_at": slot.created_at.isoformat() if slot.created_at else None,
                    "updated_at": slot.updated_at.isoformat() if slot.updated_at else None,
                }
            )
        return meta

    @staticmethod
    def _deserialize_slot_meta(meta: list[dict[str, Optional[str]]]) -> list[SlotSnapshot]:
        slots: list[SlotSnapshot] = []
        for item in meta:
            specific_date = date.fromisoformat(cast(str, item.get("specific_date")))
            start_time_obj = time.fromisoformat(cast(str, item.get("start_time")))
            end_time_obj = time.fromisoformat(cast(str, item.get("end_time")))
            created_at = (
                datetime.fromisoformat(cast(str, item.get("created_at")))
                if item.get("created_at")
                else None
            )
            updated_at = (
                datetime.fromisoformat(cast(str, item.get("updated_at")))
                if item.get("updated_at")
                else None
            )
            slots.append(
                SlotSnapshot(
                    specific_date=specific_date,
                    start_time=start_time_obj,
                    end_time=end_time_obj,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
        return slots

    @BaseService.measure_operation("get_instructor_availability_for_date_range")
    def get_instructor_availability_for_date_range(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """
        Get instructor availability for a date range using enhanced caching.

        Args:
            instructor_id: The instructor's ID
            start_date: Start date of range
            end_date: End date of range

        Returns:
            List of availability data for each date
        """
        # Try cache first
        if self.cache_service:
            try:
                cached_data = self.cache_service.get_instructor_availability_date_range(
                    instructor_id, start_date, end_date
                )
                if cached_data is not None:
                    return cached_data
            except Exception as cache_error:
                logger.warning(f"Cache error for date range availability: {cache_error}")

        # Cache miss - query database
        try:
            slots = self.repository.get_week_availability(instructor_id, start_date, end_date)
        except RepositoryException as e:
            logger.error(f"Error getting date range availability: {e}")
            return []

        # Group slots by date
        availability_by_date: dict[str, list[dict[str, Any]]] = {}
        for slot in slots:
            date_str = slot.specific_date.isoformat()
            if date_str not in availability_by_date:
                availability_by_date[date_str] = []

            availability_by_date[date_str].append(
                {
                    "start_time": time_to_string(slot.start_time),
                    "end_time": time_to_string(slot.end_time),
                }
            )

        # Convert to list format
        result = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.isoformat()
            result.append({"date": date_str, "slots": availability_by_date.get(date_str, [])})
            current_date += timedelta(days=1)

        # Cache the result
        if self.cache_service:
            try:
                self.cache_service.cache_instructor_availability_date_range(
                    instructor_id, start_date, end_date, result
                )
            except Exception as cache_error:
                logger.warning(f"Failed to cache date range availability: {cache_error}")

        return result

    @BaseService.measure_operation("get_all_availability")
    def get_all_instructor_availability(
        self, instructor_id: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> list[AvailabilitySlot]:
        """
        Get all availability slots for an instructor with optional date filtering.

        Args:
            instructor_id: The instructor's ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of availability slots ordered by date and time
        """
        self.log_operation(
            "get_all_instructor_availability",
            instructor_id=instructor_id,
            start_date=start_date,
            end_date=end_date,
        )

        try:
            # Use repository method for date range queries
            # If no dates provided, use a large range based on instructor's timezone
            if not start_date:
                start_date = get_user_today_by_id(instructor_id, self.db)
            if not end_date:
                end_date = get_user_today_by_id(instructor_id, self.db) + timedelta(
                    days=365
                )  # One year ahead

            slots = self.repository.get_week_availability(instructor_id, start_date, end_date)
            return slots

        except RepositoryException as e:
            logger.error(f"Error retrieving all availability: {str(e)}")
            raise

    def _validate_and_parse_week_data(
        self, week_data: WeekSpecificScheduleCreate, instructor_id: str
    ) -> tuple[date, list[date], dict[date, list[ProcessedSlot]]]:
        """
        Validate week data and parse into organized structure.

        Args:
            week_data: The week schedule data to validate and parse

        Returns:
            Tuple of (monday, week_dates, schedule_by_date)
        """
        # Determine week dates
        monday = self._determine_week_start(week_data, instructor_id)
        week_dates = self._calculate_week_dates(monday)

        # Group schedule by date
        schedule_by_date = self._group_schedule_by_date(week_data.schedule, instructor_id)

        return monday, week_dates, schedule_by_date

    def _prepare_slots_for_creation(
        self,
        instructor_id: str,
        week_dates: list[date],
        schedule_by_date: dict[date, list[ProcessedSlot]],
        ignore_existing: bool = False,
    ) -> PreparedWeek:
        """
        Convert time slots to database-ready format.

        Args:
            instructor_id: The instructor ID
            week_dates: List of dates in the week
            schedule_by_date: Schedule data grouped by date

        Returns:
            PreparedWeek containing normalized slots and affected dates
        """
        # Only validate for internal conflicts; existing slots are handled later.
        self._validate_no_overlaps(instructor_id, schedule_by_date, ignore_existing=True)

        slots_to_create: list[AvailabilitySlotInput] = []
        instructor_today = get_user_today_by_id(instructor_id, self.db)

        affected_dates: set[date] = set()

        for target_date in sorted(schedule_by_date.keys()):
            if not ALLOW_PAST and target_date < instructor_today:
                continue

            slots = schedule_by_date.get(target_date, [])
            if not slots:
                continue

            affected_dates.add(target_date)
            for slot in slots:
                slot_input = cast(
                    AvailabilitySlotInput,
                    {
                        "instructor_id": instructor_id,
                        "specific_date": target_date,
                        "start_time": slot["start_time"],
                        "end_time": slot["end_time"],
                    },
                )
                slots_to_create.append(slot_input)

        return PreparedWeek(slots=slots_to_create, affected_dates=affected_dates)

    async def _save_week_slots_transaction(
        self,
        instructor_id: str,
        week_start: date,
        week_dates: list[date],
        week_data: WeekSpecificScheduleCreate,
        prepared: PreparedWeek,
        actor: Any | None = None,
    ) -> int:
        """
        Execute the database transaction to save slots.

        Args:
            instructor_id: The instructor ID
            week_data: Original week data for clear_existing flag
            prepared: Normalized slots and affected dates ready for persistence

        Returns:
            Number of slots created

        Raises:
            RepositoryException: If database operation fails
        """
        affected_dates = sorted(prepared.affected_dates)
        deleted_count = 0
        created_count = 0
        change_detected = False
        if week_data.clear_existing:
            snapshot_dates = list(week_dates)
        elif affected_dates:
            snapshot_dates = list(affected_dates)
        else:
            snapshot_dates = list(week_dates)

        existing_slots_cache: dict[date, list[AvailabilitySlot]] = {}

        def get_existing_slots(target_date: date) -> list[AvailabilitySlot]:
            cached = existing_slots_cache.get(target_date)
            if cached is None:
                slots_for_day = list(self.repository.get_slots_by_date(instructor_id, target_date))
                existing_slots_cache[target_date] = slots_for_day
                return slots_for_day
            return cached

        slots_by_date: dict[date, list[ProcessedSlot]] = {}
        for slot in prepared.slots:
            target_date = slot["specific_date"]
            normalized_slot: ProcessedSlot = {
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
            }
            slots_by_date.setdefault(target_date, []).append(normalized_slot)

        for slot_list in slots_by_date.values():
            slot_list.sort(key=lambda s: (s["start_time"], s["end_time"]))

        try:
            with self.transaction():
                instructor_today = get_user_today_by_id(instructor_id, self.db)
                before_payload = self._build_week_audit_payload(
                    instructor_id,
                    week_start,
                    snapshot_dates,
                    clear_existing=bool(week_data.clear_existing),
                    slot_cache=existing_slots_cache,
                )

                # If clearing existing, delete only slots for TODAY and future within this week
                if week_data.clear_existing:
                    dates_to_clear = (
                        list(week_dates)
                        if ALLOW_PAST
                        else [d for d in week_dates if d >= instructor_today]
                    )
                    if dates_to_clear:
                        with availability_perf_span(
                            "repository.delete_slots_by_dates",
                            endpoint=WEEK_SAVE_ENDPOINT,
                            instructor_id=instructor_id,
                        ):
                            deleted_count = self.repository.delete_slots_by_dates(
                                instructor_id, dates_to_clear
                            )
                            change_detected = change_detected or deleted_count > 0
                            for cleared_date in dates_to_clear:
                                existing_slots_cache[cleared_date] = []
                    else:
                        deleted_count = 0
                    logger.info(
                        f"Deleted {deleted_count} existing slots for instructor {instructor_id}"
                    )

                existing_by_date: dict[date, list[AvailabilitySlot]] | None = None
                if not week_data.clear_existing and slots_by_date:
                    existing_by_date = {}
                    for target_date in affected_dates:
                        existing_by_date[target_date] = list(get_existing_slots(target_date))

                if slots_by_date:
                    self._validate_no_overlaps(
                        instructor_id,
                        slots_by_date,
                        ignore_existing=bool(week_data.clear_existing),
                        existing_by_date=existing_by_date,
                    )

                slots_to_create: list[dict[str, Any]] = []
                for target_date in sorted(slots_by_date.keys()):
                    if not ALLOW_PAST and target_date < instructor_today:
                        continue
                    existing_slots_cache.setdefault(
                        target_date, existing_slots_cache.get(target_date, [])
                    )
                    for processed_slot in slots_by_date[target_date]:
                        slots_to_create.append(
                            {
                                "instructor_id": instructor_id,
                                "specific_date": target_date,
                                "start_time": processed_slot["start_time"],
                                "end_time": processed_slot["end_time"],
                            }
                        )

                # Bulk create all slots at once
                if slots_to_create:
                    with availability_perf_span(
                        "repository.bulk_create_slots",
                        endpoint=WEEK_SAVE_ENDPOINT,
                        instructor_id=instructor_id,
                    ):
                        created_slots = self.bulk_repository.bulk_create_slots(slots_to_create)
                    created_count = len(created_slots)
                    change_detected = change_detected or created_count > 0
                    logger.info(f"Created {created_count} new slots for instructor {instructor_id}")
                    for created_slot in created_slots:
                        existing_slots_cache.setdefault(created_slot.specific_date, []).append(
                            created_slot
                        )

                if change_detected or week_data.clear_existing:
                    self._enqueue_week_save_event(
                        instructor_id=instructor_id,
                        week_start=week_start,
                        week_dates=week_dates,
                        prepared=prepared,
                        created_count=created_count,
                        deleted_count=deleted_count,
                        clear_existing=bool(week_data.clear_existing),
                    )
                    after_payload = self._build_week_audit_payload(
                        instructor_id,
                        week_start,
                        snapshot_dates,
                        clear_existing=bool(week_data.clear_existing),
                        created=created_count,
                        deleted=deleted_count,
                        slot_cache=existing_slots_cache,
                    )
                    self._write_availability_audit(
                        instructor_id,
                        week_start,
                        "save_week",
                        actor=actor,
                        before=before_payload,
                        after=after_payload,
                    )

                return created_count
        except RepositoryException as e:
            logger.error(
                f"Database error saving week availability for instructor {instructor_id}: {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error saving week availability for instructor {instructor_id}: {e}"
            )
            raise

    async def _warm_cache_after_save(
        self,
        instructor_id: str,
        monday: date,
        affected_dates: set[date],
        slot_count: int,
    ) -> dict[str, list[TimeSlotResponse]]:
        """
        Warm cache with new availability data.

        Args:
            instructor_id: The instructor ID
            monday: Monday of the week
            affected_dates: Dates touched by the operation (including spillover)
            slot_count: Number of slots created

        Returns:
            Updated availability data

        Note:
            Cache failures do not prevent the operation from succeeding
        """
        # Expire all cached objects to ensure fresh data for the final query
        # This is necessary after bulk operations to prevent stale data issues
        self.db.expire_all()

        cache_dates = set(affected_dates)
        cache_dates.add(monday)
        cache_dates_sorted = sorted(cache_dates)

        week_starts = {day - timedelta(days=day.weekday()) for day in cache_dates_sorted} | {monday}
        week_starts_sorted = sorted(week_starts)

        # Handle cache warming
        if self.cache_service:
            try:
                from .cache_strategies import CacheWarmingStrategy

                warmer = CacheWarmingStrategy(self.cache_service, self.db)
                updated_availability: dict[str, list[TimeSlotResponse]] | None = None

                for week_start in week_starts_sorted:
                    warmed = await warmer.warm_with_verification(
                        instructor_id, week_start, expected_slot_count=None
                    )
                    if week_start == monday:
                        updated_availability = warmed

                logger.debug(
                    "Cache warmed successfully for instructor %s across %d week(s), slot_count=%d",
                    instructor_id,
                    len(week_starts_sorted),
                    slot_count,
                )

                if updated_availability is not None:
                    return updated_availability
                return self.get_week_availability(instructor_id, monday)
            except ImportError:
                logger.warning("Cache strategies not available, using direct fetch")
            except Exception as cache_error:
                logger.warning(
                    f"Cache warming failed for instructor {instructor_id}: {cache_error}"
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
        """
        Save availability for specific dates in a week - NOW UNDER 50 LINES!

        Args:
            instructor_id: The instructor's user ID
            week_data: The week schedule data

        Returns:
            Updated week availability
        """
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
            # 1. Validate and parse
            monday, week_dates, schedule_by_date = self._validate_and_parse_week_data(
                week_data, instructor_id
            )

            # Optional optimistic concurrency check
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
            except Exception as _e:
                logger.debug(f"Version check skipped: {_e}")

            # 2. Prepare slots for creation
            prepared_week = self._prepare_slots_for_creation(
                instructor_id,
                week_dates,
                schedule_by_date,
                ignore_existing=bool(week_data.clear_existing),
            )

            # 3. Save to database
            slot_count = await self._save_week_slots_transaction(
                instructor_id,
                monday,
                week_dates,
                week_data,
                prepared_week,
                actor=actor,
            )

            # 4. Warm cache and return response
            updated_availability = await self._warm_cache_after_save(
                instructor_id, monday, prepared_week.affected_dates, slot_count
            )

            return updated_availability

    @BaseService.measure_operation("add_specific_date")
    def add_specific_date_availability(
        self, instructor_id: str, availability_data: SpecificDateAvailabilityCreate
    ) -> AvailabilitySlot:
        """
        Add availability for a specific date.

        Args:
            instructor_id: The instructor's user ID
            availability_data: The specific date and time slot

        Returns:
            Created availability slot information
        """
        with self.transaction():
            # Check for duplicate slot
            if self.repository.slot_exists(
                instructor_id,
                target_date=availability_data.specific_date,
                start_time=availability_data.start_time,
                end_time=availability_data.end_time,
            ):
                raise ConflictException("This time slot already exists")

            # Ensure the new slot does not overlap existing slots on that date
            existing_for_date = self.repository.get_slots_by_date(
                instructor_id, availability_data.specific_date
            )
            candidate_slots: list[ProcessedSlot] = [
                ProcessedSlot(start_time=slot.start_time, end_time=slot.end_time)
                for slot in existing_for_date
            ]
            candidate_slots.append(
                ProcessedSlot(
                    start_time=availability_data.start_time,
                    end_time=availability_data.end_time,
                )
            )
            self._validate_no_overlaps(
                instructor_id,
                {availability_data.specific_date: candidate_slots},
                ignore_existing=True,
            )

            # Create new slot
            slot = self.repository.create_slot(
                instructor_id=instructor_id,
                target_date=availability_data.specific_date,
                start_time=availability_data.start_time,
                end_time=availability_data.end_time,
            )

            # Invalidate cache
            self._invalidate_availability_caches(instructor_id, [availability_data.specific_date])

            return slot  # Just return the model object

    @BaseService.measure_operation("get_blackout_dates")
    def get_blackout_dates(self, instructor_id: str) -> list[BlackoutDate]:
        """
        Get instructor's future blackout dates.

        Args:
            instructor_id: The instructor's user ID

        Returns:
            List of future blackout dates
        """
        try:
            return self.repository.get_future_blackout_dates(instructor_id)
        except RepositoryException as e:
            logger.error(f"Error getting blackout dates: {e}")
            return []

    @BaseService.measure_operation("add_blackout_date")
    def add_blackout_date(
        self, instructor_id: str, blackout_data: BlackoutDateCreate
    ) -> BlackoutDate:
        """
        Add a blackout date for an instructor.

        Args:
            instructor_id: The instructor's user ID
            blackout_data: The blackout date information

        Returns:
            Created blackout date
        """
        # Check if already exists
        existing_blackouts = self.repository.get_future_blackout_dates(instructor_id)
        if any(b.date == blackout_data.date for b in existing_blackouts):
            raise ConflictException("Blackout date already exists")

        with self.transaction():
            try:
                blackout = self.repository.create_blackout_date(
                    instructor_id, blackout_data.date, blackout_data.reason
                )
                return blackout
            except RepositoryException as e:
                if "already exists" in str(e):
                    raise ConflictException("Blackout date already exists")
                raise

    @BaseService.measure_operation("delete_blackout_date")
    def delete_blackout_date(self, instructor_id: str, blackout_id: str) -> bool:
        """
        Delete a blackout date.

        Args:
            instructor_id: The instructor's user ID
            blackout_id: The blackout date ID

        Returns:
            True if deleted successfully
        """
        with self.transaction():
            try:
                success = self.repository.delete_blackout_date(blackout_id, instructor_id)
                if not success:
                    raise NotFoundException("Blackout date not found")
                return True
            except RepositoryException as e:
                logger.error(f"Error deleting blackout date: {e}")
                raise

    @BaseService.measure_operation("compute_public_availability")
    def compute_public_availability(
        self, instructor_id: str, start_date: date, end_date: date
    ) -> dict[str, list[tuple[time, time]]]:
        """
        Compute per-date availability intervals merged and with booked times subtracted.

        Returns dict: { 'YYYY-MM-DD': [(start_time, end_time), ...] }
        """
        # Fetch availability windows
        slots = self.repository.get_week_availability(instructor_id, start_date, end_date)

        # Group by date
        by_date: dict[date, list[tuple[time, time]]] = {}
        for s in slots:
            by_date.setdefault(s.specific_date, []).append((s.start_time, s.end_time))

        # Helpers
        from datetime import time as dtime

        def merge_intervals(intervals: list[tuple[time, time]]) -> list[tuple[time, time]]:
            if not intervals:
                return []
            mins = sorted(
                [(a.hour * 60 + a.minute, b.hour * 60 + b.minute) for a, b in intervals],
                key=lambda x: x[0],
            )
            merged = []
            cs, ce = mins[0]
            for s, e in mins[1:]:
                if s <= ce:
                    ce = max(ce, e)
                else:
                    merged.append((cs, ce))
                    cs, ce = s, e
            merged.append((cs, ce))
            return [(dtime(m // 60, m % 60), dtime(n // 60, n % 60)) for m, n in merged]

        def subtract(
            bases: list[tuple[time, time]], cuts: list[tuple[time, time]]
        ) -> list[tuple[time, time]]:
            if not bases:
                return []
            if not cuts:
                return merge_intervals(bases)

            def tmin(t: time) -> int:
                return t.hour * 60 + t.minute

            cutm = [(tmin(a), tmin(b)) for a, b in merge_intervals(cuts)]
            out = []
            for bs, be in bases:
                segs = [(tmin(bs), tmin(be))]
                for cs, ce in cutm:
                    new = []
                    for s, e in segs:
                        if e <= cs or s >= ce:
                            new.append((s, e))
                        else:
                            if s < cs:
                                new.append((s, max(s, cs)))
                            if e > ce:
                                new.append((min(e, ce), e))
                    segs = [p for p in new if p[1] > p[0]]
                    if not segs:
                        break
                for s, e in segs:
                    out.append((dtime(s // 60, s % 60), dtime(e // 60, e % 60)))
            return merge_intervals(out)

        # Build result
        result: dict[str, list[tuple[time, time]]] = {}
        cur = start_date
        while cur <= end_date:
            bases = merge_intervals(by_date.get(cur, []))
            booked = [
                (b.start_time, b.end_time)
                for b in self.conflict_repository.get_bookings_for_date(instructor_id, cur)
            ]
            remaining = subtract(bases, booked)
            result[cur.isoformat()] = remaining
            cur += timedelta(days=1)
        return result

    # Private helper methods

    def _calculate_week_dates(self, monday: date) -> list[date]:
        """Calculate all dates for a week starting from Monday."""
        return [monday + timedelta(days=i) for i in range(7)]

    def _validate_no_overlaps(
        self,
        instructor_id: str,
        schedule_by_date: dict[date, list[ProcessedSlot]],
        *,
        ignore_existing: bool,
        existing_by_date: dict[date, list[AvailabilitySlot]] | None = None,
    ) -> None:
        """Ensure proposed slots obey the half-open interval rules."""

        for target_date, slots in list(schedule_by_date.items()):
            if not slots:
                continue

            slots.sort(key=lambda s: (s["start_time"], s["end_time"]))
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

            if existing_by_date is not None:
                existing_slots = existing_by_date.get(target_date, [])
            else:
                existing_slots = self.repository.get_slots_by_date(instructor_id, target_date)
            existing_ranges = {(slot.start_time, slot.end_time) for slot in existing_slots}

            filtered: list[ProcessedSlot] = []
            for slot in slots:
                key = (slot["start_time"], slot["end_time"])
                if key not in existing_ranges:
                    filtered.append(slot)
            schedule_by_date[target_date] = filtered

            intervals: list[tuple[time, time, str]] = [
                (slot.start_time, slot.end_time, "existing") for slot in existing_slots
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
        start_min = start.hour * 60 + start.minute
        end_min = end.hour * 60 + end.minute
        if end == time(0, 0) and start != time(0, 0):
            end_min = 24 * 60
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

    def _determine_week_start(
        self, week_data: WeekSpecificScheduleCreate, instructor_id: str
    ) -> date:
        """Determine the Monday of the week from schedule data."""
        if week_data.week_start:
            return week_data.week_start
        elif week_data.schedule:
            # Get Monday from the first date in schedule
            first_date = min(date.fromisoformat(slot["date"]) for slot in week_data.schedule)
            return first_date - timedelta(days=first_date.weekday())
        else:
            # Fallback to current week in instructor's timezone
            instructor_today = get_user_today_by_id(instructor_id, self.db)
            return instructor_today - timedelta(days=instructor_today.weekday())

    def _group_schedule_by_date(
        self, schedule: list[dict[str, str]], instructor_id: str
    ) -> dict[date, list[ProcessedSlot]]:
        """Group schedule entries by date, normalizing overnight spans."""

        schedule_by_date: dict[date, list[ProcessedSlot]] = {}
        instructor_today = get_user_today_by_id(instructor_id, self.db)

        for slot in schedule:
            slot_date = date.fromisoformat(slot["date"])
            start_time_obj = time.fromisoformat(slot["start_time"])
            end_time_obj = time.fromisoformat(slot["end_time"])

            if not ALLOW_PAST and slot_date < instructor_today:
                logger.warning(
                    f"Skipping past date: {slot_date} (instructor today: {instructor_today})"
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

        if not ALLOW_PAST and target_date < instructor_today:
            logger.warning(
                f"Skipping past date: {target_date} (instructor today: {instructor_today})"
            )
            return

        schedule_by_date.setdefault(target_date, []).append(
            ProcessedSlot(start_time=start_time_obj, end_time=end_time_obj)
        )

    def _invalidate_availability_caches(self, instructor_id: str, dates: list[date]) -> None:
        """Invalidate caches for affected dates using enhanced cache service."""
        if self.cache_service:
            try:
                # Use the new cache service invalidation method
                self.cache_service.invalidate_instructor_availability(instructor_id, dates)
            except Exception as cache_error:
                logger.warning(f"Cache invalidation failed: {cache_error}")

        # Fallback to legacy cache invalidation
        self.invalidate_cache(f"instructor_availability:{instructor_id}")

        # Invalidate date-specific caches
        for target_date in dates:
            self.invalidate_cache(f"instructor_availability:{instructor_id}:{target_date}")

        # Invalidate week caches
        weeks = set()
        for target_date in dates:
            monday = target_date - timedelta(days=target_date.weekday())
            weeks.add(monday)

        if self.cache_service:
            for week_start in weeks:
                try:
                    map_key, composite_key = self._week_cache_keys(instructor_id, week_start)
                    self.invalidate_cache(map_key, composite_key)
                except Exception as cache_error:
                    logger.warning(
                        f"Failed to invalidate availability cache keys for week {week_start}: {cache_error}"
                    )

        for week_start in weeks:
            self.invalidate_cache(f"week_availability:{instructor_id}:{week_start}")
