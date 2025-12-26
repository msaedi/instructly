"""
Shared seeding helpers for safety checks.

Provides booking creation utilities that respect the PostgreSQL exclusion
constraints by shifting proposed spans when conflicts are detected.

Includes optimized bulk-loading functions for remote databases (Supabase)
that pre-fetch all data and do in-memory conflict detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import json
import logging
import random
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.timezone_service import TimezoneService
from app.utils.bitset import windows_from_bits
from app.utils.time_utils import time_to_minutes

logger = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "America/New_York"


@dataclass
class SlotSearchDiagnostics:
    instructor_id: str
    student_id: str
    examined_start: date
    examined_end: date
    durations_order: Sequence[int]
    bitmap_days: int = 0
    instructor_conflicts: int = 0
    student_conflicts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instructor_id": self.instructor_id,
            "student_id": self.student_id,
            "examined_start": self.examined_start.isoformat(),
            "examined_end": self.examined_end.isoformat(),
            "durations_minutes": list(self.durations_order),
            "bitmap_days": self.bitmap_days,
            "instructor_conflicts": self.instructor_conflicts,
            "student_conflicts": self.student_conflicts,
        }

_ACTIVE_STATUSES: Mapping[str, BookingStatus] = {
    status.name: status
    for status in (BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED)
}


def _active_status_values() -> Iterable[str]:
    return (status.value for status in _ACTIVE_STATUSES.values())


def _minutes_between(start: time, end: time) -> int:
    start_dt = datetime.combine(date(2000, 1, 1), start)  # tz-pattern-ok: seed utility for test data
    end_dt = datetime.combine(date(2000, 1, 1), end)  # tz-pattern-ok: seed utility for test data
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(minutes=1)
    return int((end_dt - start_dt).total_seconds() // 60)


def _booking_timezone_fields(
    booking_date: date,
    start_time: time,
    end_time: time,
    *,
    lesson_timezone: Optional[str] = None,
    student_timezone: Optional[str] = None,
) -> dict[str, Any]:
    if start_time.tzinfo is not None:
        start_time = start_time.replace(tzinfo=None)
    if end_time.tzinfo is not None:
        end_time = end_time.replace(tzinfo=None)
    lesson_tz = lesson_timezone or DEFAULT_TIMEZONE
    student_tz = student_timezone or lesson_tz
    return {
        "booking_start_utc": TimezoneService.local_to_utc(booking_date, start_time, lesson_tz),
        "booking_end_utc": TimezoneService.local_to_utc(booking_date, end_time, lesson_tz),
        "lesson_timezone": lesson_tz,
        "instructor_tz_at_booking": lesson_tz,
        "student_tz_at_booking": student_tz,
    }


def _shift_time(base: time, minutes: int) -> time:
    shifted = datetime.combine(date(2000, 1, 1), base) + timedelta(  # tz-pattern-ok: seed utility for test data
        minutes=minutes
    )
    return shifted.time()


def _detect_conflicts(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> Tuple[int, int]:
    active_values = tuple(_active_status_values())
    instructor_conflicts = (
        session.query(Booking)
        .filter(
            Booking.instructor_id == instructor_id,
            Booking.booking_date == booking_date,
            Booking.start_time < end_time,
            Booking.end_time > start_time,
            Booking.cancelled_at.is_(None),
            Booking.status.in_(active_values),
        )
        .count()
    )
    student_conflicts = (
        session.query(Booking)
        .filter(
            Booking.student_id == student_id,
            Booking.booking_date == booking_date,
            Booking.start_time < end_time,
            Booking.end_time > start_time,
            Booking.cancelled_at.is_(None),
            Booking.status.in_(active_values),
        )
        .count()
    )
    return instructor_conflicts, student_conflicts


def _has_conflict(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    diagnostics: Optional[SlotSearchDiagnostics] = None,
) -> bool:
    instructor_conflicts, student_conflicts = _detect_conflicts(
        session,
        instructor_id=instructor_id,
        student_id=student_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
    )
    if diagnostics is not None:
        diagnostics.instructor_conflicts += instructor_conflicts
        diagnostics.student_conflicts += student_conflicts
    return (instructor_conflicts + student_conflicts) > 0


def _time_str_to_minutes(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    if hours == 24 and minutes == 0 and seconds == 0:
        return 24 * 60
    return hours * 60 + minutes


def _minutes_to_time(value: int) -> time:
    if value >= 24 * 60:
        return time(23, 59, 59)
    hours = value // 60
    minutes = value % 60
    return time(hours, minutes)


def _generate_candidate_span_minutes(
    window_start_minutes: int,
    window_end_minutes: int,
    duration_minutes: int,
    step_minutes: int,
) -> Iterable[Tuple[int, int]]:
    span_minutes = window_end_minutes - window_start_minutes
    if span_minutes < duration_minutes:
        return

    step = max(1, step_minutes)
    max_offset = span_minutes - duration_minutes
    for offset in range(0, max_offset + 1, step):
        start_minutes = window_start_minutes + offset
        end_minutes = start_minutes + duration_minutes
        if end_minutes > window_end_minutes:
            break
        yield start_minutes, end_minutes


def find_free_slot_in_bitmap(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    base_date: date,
    lookback_days: int = 90,
    horizon_days: int = 21,
    day_start_hour: int = 9,
    day_end_hour: int = 18,
    step_minutes: int = 15,
    durations_minutes: Optional[Sequence[int]] = None,
) -> Tuple[Optional[Tuple[date, time, time]], SlotSearchDiagnostics]:
    """
    Locate the first available span in the instructor's bitmap availability.

    Searches backward first (up to lookback_days), then forward (up to horizon_days),
    attempting durations in the supplied order until a conflict-free window is found.
    """

    lookback = max(0, lookback_days)
    horizon = max(0, horizon_days)
    durations = [int(d) for d in (durations_minutes or (60, 45, 30)) if int(d) > 0]
    if not durations:
        durations = [30]

    search_start = base_date - timedelta(days=lookback)
    search_end = base_date + timedelta(days=horizon)
    diagnostics = SlotSearchDiagnostics(
        instructor_id=instructor_id,
        student_id=student_id,
        examined_start=search_start,
        examined_end=search_end - timedelta(days=1) if horizon > 0 else base_date,
        durations_order=durations,
    )

    repo = AvailabilityDayRepository(session)
    day_start_minutes = max(0, day_start_hour) * 60
    day_end_minutes = min(24 * 60, max(day_start_minutes + 1, day_end_hour * 60))
    step = max(1, step_minutes)
    processed_dates: set[date] = set()

    def _attempt_for_date(target_date: date) -> Optional[Tuple[date, time, time]]:
        if target_date in processed_dates:
            return None
        processed_dates.add(target_date)

        bits = repo.get_day_bits(instructor_id, target_date)
        if bits is None:
            return None

        diagnostics.bitmap_days += 1
        windows = windows_from_bits(bits)
        if not windows:
            return None

        for start_str, end_str in windows:
            window_start_minutes = _time_str_to_minutes(start_str)
            window_end_minutes = _time_str_to_minutes(end_str)

            if window_end_minutes <= day_start_minutes or window_start_minutes >= day_end_minutes:
                continue

            clamped_start = max(window_start_minutes, day_start_minutes)
            clamped_end = min(window_end_minutes, day_end_minutes)
            available_span = clamped_end - clamped_start
            if available_span <= 0:
                continue

            for duration in durations:
                if available_span < duration:
                    continue

                for start_minutes, end_minutes in _generate_candidate_span_minutes(
                    clamped_start,
                    clamped_end,
                    duration,
                    step,
                ):
                    start_time = _minutes_to_time(start_minutes)
                    end_time = _minutes_to_time(end_minutes)
                    if _has_conflict(
                        session,
                        instructor_id=instructor_id,
                        student_id=student_id,
                        booking_date=target_date,
                        start_time=start_time,
                        end_time=end_time,
                        diagnostics=diagnostics,
                    ):
                        continue
                    logger.debug(
                        "bitmap_slot_search_summary %s",
                        json.dumps(
                            {
                                **diagnostics.to_dict(),
                                "slot_found": True,
                                "direction": "backward" if target_date < base_date else "forward",
                                "booking_date": target_date.isoformat(),
                                "start_time": start_time.isoformat(),
                                "end_time": end_time.isoformat(),
                                "duration_minutes": duration,
                            }
                        ),
                    )
                    return target_date, start_time, end_time
        return None

    for day_offset in range(1, lookback + 1):
        candidate_date = base_date - timedelta(days=day_offset)
        slot = _attempt_for_date(candidate_date)
        if slot:
            return slot, diagnostics

    for day_offset in range(0, horizon + 1):
        candidate_date = base_date + timedelta(days=day_offset)
        slot = _attempt_for_date(candidate_date)
        if slot:
            return slot, diagnostics

    logger.debug(
        "bitmap_slot_search_summary %s",
        json.dumps({**diagnostics.to_dict(), "slot_found": False}),
    )
    return None, diagnostics


def create_booking_safe(
    session: Session,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    status: BookingStatus | str = BookingStatus.CONFIRMED,
    max_attempts: int = 32,
    shift_minutes: int = 15,
    **extra_fields: Any,
) -> Optional[Booking]:
    """
    Attempt to create a booking while avoiding instructor/student overlaps.

    The span is shifted forward by `shift_minutes` (default 15) until it no longer
    conflicts. Returns None if a free window cannot be found within `max_attempts`.
    """

    if isinstance(status, str):
        status = BookingStatus(status)

    duration_minutes = _minutes_between(start_time, end_time)
    attempts = 0
    current_start = start_time
    current_end = end_time

    while attempts < max_attempts:
        if not _has_conflict(
            session,
            instructor_id=instructor_id,
            student_id=student_id,
            booking_date=booking_date,
            start_time=current_start,
            end_time=current_end,
        ):
            break

        attempts += 1
        next_start_dt = datetime.combine(  # tz-pattern-ok: seed utility for test data
            booking_date, current_start
        ) + timedelta(minutes=shift_minutes)
        next_end_dt = next_start_dt + timedelta(minutes=duration_minutes)

        if next_start_dt.date() != booking_date or next_end_dt.date() != booking_date:
            logger.warning(
                "Skipping seeded booking due to day overflow while avoiding overlap",
                extra={
                    "instructor_id": instructor_id,
                    "student_id": student_id,
                    "booking_date": booking_date.isoformat(),
                    "attempts": attempts,
                },
            )
            return None

        current_start = next_start_dt.time()
        current_end = next_end_dt.time()
    else:
        logger.warning(
            "Failed to seed booking after max attempts",
            extra={
                "instructor_id": instructor_id,
                "student_id": student_id,
                "booking_date": booking_date.isoformat(),
                "max_attempts": max_attempts,
            },
        )
        return None

    if current_start.tzinfo is not None:
        current_start = current_start.replace(tzinfo=None)
    if current_end.tzinfo is not None:
        current_end = current_end.replace(tzinfo=None)
    lesson_timezone = extra_fields.get("lesson_timezone") or extra_fields.get("instructor_tz_at_booking")
    student_timezone = extra_fields.get("student_tz_at_booking")
    timezone_fields = _booking_timezone_fields(
        booking_date,
        current_start,
        current_end,
        lesson_timezone=lesson_timezone,
        student_timezone=student_timezone,
    )

    booking = Booking(
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=current_start,
        end_time=current_end,
        status=status,
        **timezone_fields,
        **extra_fields,
    )
    session.add(booking)
    session.flush()

    return booking


def create_review_booking_pg_safe(
    session: Session,
    *,
    instructor_id: str,
    student_id: str,
    instructor_service_id: str,
    base_date: date,
    location_type: str,
    meeting_location: str,
    service_name: str,
    hourly_rate,
    total_price,
    student_note: str,
    completed_at: datetime,
    duration_minutes: int = 60,
    lookback_days: int = 90,
    horizon_days: int = 21,
    day_start_hour: int = 9,
    day_end_hour: int = 18,
    step_minutes: int = 15,
    durations_minutes: Optional[Sequence[int]] = None,
    **extra_fields: Any,
) -> Optional[Booking]:
    """
    Seed helper that finds a free slot in bitmap availability before creation.
    """

    slot, diagnostics = find_free_slot_in_bitmap(
        session,
        instructor_id=instructor_id,
        student_id=student_id,
        base_date=base_date,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
        day_start_hour=day_start_hour,
        day_end_hour=day_end_hour,
        step_minutes=step_minutes,
        durations_minutes=durations_minutes or (duration_minutes, 45, 30),
    )

    if not slot:
        context = {
            **diagnostics.to_dict(),
            "status": "skipped",
            "base_date": base_date.isoformat(),
            "lookback_days": lookback_days,
            "horizon_days": horizon_days,
            "day_start_hour": day_start_hour,
            "day_end_hour": day_end_hour,
            "step_minutes": step_minutes,
            "durations_attempted": list(durations_minutes or (duration_minutes, 45, 30)),
            "reason": "no_free_slot_within_span",
            "slot_found": False,
        }
        logger.warning("review_booking_skipped %s", json.dumps(context))
        return None

    booking_date, start_time, end_time = slot
    context = {
        **diagnostics.to_dict(),
        "status": "created",
        "base_date": base_date.isoformat(),
        "lookback_days": lookback_days,
        "horizon_days": horizon_days,
        "booking_date": booking_date.isoformat(),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_minutes": _minutes_between(start_time, end_time),
        "day_start_hour": day_start_hour,
        "day_end_hour": day_end_hour,
        "step_minutes": step_minutes,
        "durations_attempted": list(durations_minutes or (duration_minutes, 45, 30)),
        "slot_found": True,
    }
    logger.info("review_booking_seeded %s", json.dumps(context))
    return create_booking_safe(
        session,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=BookingStatus.COMPLETED,
        location_type=location_type,
        meeting_location=meeting_location,
        service_name=service_name,
        hourly_rate=hourly_rate,
        total_price=total_price,
        duration_minutes=duration_minutes,
        student_note=student_note,
        completed_at=completed_at,
        **extra_fields,
    )


# =============================================================================
# BULK LOADING UTILITIES FOR REMOTE DATABASES
# =============================================================================
# These functions pre-fetch all data in a small number of queries and do
# conflict detection in-memory, reducing network round-trips from ~40,000
# queries to ~4 queries for review seeding.


@dataclass
class BulkSeedingContext:
    """
    Pre-loaded data for bulk review seeding.

    Holds all bitmap availability and existing bookings in memory for O(1)
    conflict detection instead of O(queries) per slot check.
    """

    # {(instructor_id, date): bitmap_bytes}
    bitmap_data: Dict[Tuple[str, date], bytes] = field(default_factory=dict)

    # Set of (instructor_id, date, start_minute, end_minute) for existing bookings
    instructor_bookings: Set[Tuple[str, date, int, int]] = field(default_factory=set)

    # Set of (student_id, date, start_minute, end_minute) for existing bookings
    student_bookings: Set[Tuple[str, date, int, int]] = field(default_factory=set)

    # Track newly created bookings during seeding (update sets as we go)
    pending_instructor_bookings: Set[Tuple[str, date, int, int]] = field(default_factory=set)
    pending_student_bookings: Set[Tuple[str, date, int, int]] = field(default_factory=set)


def bulk_load_bitmap_data(
    session: Session,
    instructor_ids: List[str],
    start_date: date,
    end_date: date,
) -> Dict[Tuple[str, date], bytes]:
    """
    Load all bitmap availability for given instructors in a single query.

    Returns a dict mapping (instructor_id, date) -> bitmap_bytes.
    """
    if not instructor_ids:
        return {}

    rows = (
        session.query(AvailabilityDay.instructor_id, AvailabilityDay.day_date, AvailabilityDay.bits)
        .filter(
            AvailabilityDay.instructor_id.in_(instructor_ids),
            AvailabilityDay.day_date >= start_date,
            AvailabilityDay.day_date <= end_date,
        )
        .all()
    )

    result: Dict[Tuple[str, date], bytes] = {}
    for instructor_id, day_date, bits in rows:
        if bits is not None:
            result[(instructor_id, day_date)] = bits

    logger.info(
        "bulk_load_bitmap_data: loaded %d bitmap rows for %d instructors (%s to %s)",
        len(result),
        len(instructor_ids),
        start_date.isoformat(),
        end_date.isoformat(),
    )
    return result


def bulk_load_bookings(
    session: Session,
    instructor_ids: List[str],
    student_ids: List[str],
    start_date: date,
    end_date: date,
) -> Tuple[Set[Tuple[str, date, int, int]], Set[Tuple[str, date, int, int]]]:
    """
    Load all active bookings for conflict detection in a single query.

    Returns two sets:
    - instructor_bookings: {(instructor_id, date, start_minute, end_minute)}
    - student_bookings: {(student_id, date, start_minute, end_minute)}
    """
    # Short-circuit if both lists are empty - no bookings to load
    if not instructor_ids and not student_ids:
        return set(), set()

    active_values = tuple(_active_status_values())

    # Build base query
    query = session.query(
        Booking.instructor_id,
        Booking.student_id,
        Booking.booking_date,
        Booking.start_time,
        Booking.end_time,
    ).filter(
        Booking.booking_date >= start_date,
        Booking.booking_date <= end_date,
        Booking.cancelled_at.is_(None),
        Booking.status.in_(active_values),
    )

    # Build OR filter only for non-empty lists (avoids IN () syntax error)
    or_conditions = []
    if instructor_ids:
        or_conditions.append(Booking.instructor_id.in_(instructor_ids))
    if student_ids:
        or_conditions.append(Booking.student_id.in_(student_ids))

    rows = query.filter(or_(*or_conditions)).all()

    instructor_bookings: Set[Tuple[str, date, int, int]] = set()
    student_bookings: Set[Tuple[str, date, int, int]] = set()

    for instructor_id, student_id, booking_date, start_time, end_time in rows:
        start_min = time_to_minutes(start_time, is_end_time=False) if start_time else 0
        end_min = time_to_minutes(end_time, is_end_time=True) if end_time else 1440

        instructor_bookings.add((instructor_id, booking_date, start_min, end_min))
        student_bookings.add((student_id, booking_date, start_min, end_min))

    logger.info(
        "bulk_load_bookings: loaded %d instructor booking spans, %d student booking spans",
        len(instructor_bookings),
        len(student_bookings),
    )
    return instructor_bookings, student_bookings


def create_bulk_seeding_context(
    session: Session,
    instructor_ids: List[str],
    student_ids: List[str],
    lookback_days: int = 90,
    horizon_days: int = 21,
) -> BulkSeedingContext:
    """
    Create a pre-loaded context for bulk review seeding.

    This loads ALL necessary data in just 2 queries, enabling O(1) conflict
    detection instead of O(queries) per slot.
    """
    today = date.today()
    start_date = today - timedelta(days=lookback_days)
    end_date = today + timedelta(days=horizon_days)

    bitmap_data = bulk_load_bitmap_data(session, instructor_ids, start_date, end_date)
    instructor_bookings, student_bookings = bulk_load_bookings(
        session, instructor_ids, student_ids, start_date, end_date
    )

    return BulkSeedingContext(
        bitmap_data=bitmap_data,
        instructor_bookings=instructor_bookings,
        student_bookings=student_bookings,
    )


def _has_conflict_bulk(
    ctx: BulkSeedingContext,
    instructor_id: str,
    student_id: str,
    booking_date: date,
    start_minutes: int,
    end_minutes: int,
) -> bool:
    """
    In-memory conflict detection using pre-loaded data.

    O(n) where n is number of bookings on that date, but n is typically small.
    Much faster than database queries over network.
    """
    # Check instructor conflicts (existing + pending)
    for inst_id, bdate, start_min, end_min in ctx.instructor_bookings:
        if inst_id == instructor_id and bdate == booking_date:
            # Overlap check: start < other_end AND end > other_start
            if start_minutes < end_min and end_minutes > start_min:
                return True

    for inst_id, bdate, start_min, end_min in ctx.pending_instructor_bookings:
        if inst_id == instructor_id and bdate == booking_date:
            if start_minutes < end_min and end_minutes > start_min:
                return True

    # Check student conflicts (existing + pending)
    for stu_id, bdate, start_min, end_min in ctx.student_bookings:
        if stu_id == student_id and bdate == booking_date:
            if start_minutes < end_min and end_minutes > start_min:
                return True

    for stu_id, bdate, start_min, end_min in ctx.pending_student_bookings:
        if stu_id == student_id and bdate == booking_date:
            if start_minutes < end_min and end_minutes > start_min:
                return True

    return False


def find_free_slot_bulk(
    ctx: BulkSeedingContext,
    instructor_id: str,
    student_id: str,
    base_date: date,
    lookback_days: int = 90,
    horizon_days: int = 21,
    day_start_hour: int = 9,
    day_end_hour: int = 18,
    step_minutes: int = 15,
    durations_minutes: Optional[Sequence[int]] = None,
    randomize: bool = True,
    past_only: bool = False,
) -> Optional[Tuple[date, time, time]]:
    """
    Find a free slot using pre-loaded bitmap data and in-memory conflict detection.

    This is the bulk-optimized version of find_free_slot_in_bitmap that uses
    pre-loaded data instead of making database queries per slot check.

    If randomize=True, shuffles candidate dates to distribute bookings more evenly.
    """
    lookback = max(0, lookback_days)
    horizon = max(0, horizon_days)
    durations = [int(d) for d in (durations_minutes or (60, 45, 30)) if int(d) > 0]
    if not durations:
        durations = [30]

    day_start_minutes = max(0, day_start_hour) * 60
    day_end_minutes = min(24 * 60, max(day_start_minutes + 1, day_end_hour * 60))
    step = max(1, step_minutes)

    # Build candidate dates (backward then forward unless past_only=True)
    candidate_dates: List[date] = []
    for day_offset in range(1, lookback + 1):
        candidate_dates.append(base_date - timedelta(days=day_offset))
    if not past_only:
        for day_offset in range(0, horizon + 1):
            candidate_dates.append(base_date + timedelta(days=day_offset))

    # Optionally randomize to distribute slots more evenly
    if randomize:
        random.shuffle(candidate_dates)

    for target_date in candidate_dates:
        bits = ctx.bitmap_data.get((instructor_id, target_date))
        if bits is None:
            continue

        windows = windows_from_bits(bits)
        if not windows:
            continue

        for start_str, end_str in windows:
            window_start_minutes = _time_str_to_minutes(start_str)
            window_end_minutes = _time_str_to_minutes(end_str)

            if window_end_minutes <= day_start_minutes or window_start_minutes >= day_end_minutes:
                continue

            clamped_start = max(window_start_minutes, day_start_minutes)
            clamped_end = min(window_end_minutes, day_end_minutes)
            available_span = clamped_end - clamped_start
            if available_span <= 0:
                continue

            for duration in durations:
                if available_span < duration:
                    continue

                # Generate candidate spans
                candidates = list(
                    _generate_candidate_span_minutes(clamped_start, clamped_end, duration, step)
                )
                if randomize:
                    random.shuffle(candidates)

                for start_min, end_min in candidates:
                    if not _has_conflict_bulk(
                        ctx,
                        instructor_id=instructor_id,
                        student_id=student_id,
                        booking_date=target_date,
                        start_minutes=start_min,
                        end_minutes=end_min,
                    ):
                        return target_date, _minutes_to_time(start_min), _minutes_to_time(end_min)

    return None


def register_pending_booking(
    ctx: BulkSeedingContext,
    instructor_id: str,
    student_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> None:
    """
    Register a newly created booking in the context so subsequent slot searches
    see it for conflict detection.
    """
    start_min = time_to_minutes(start_time, is_end_time=False)
    end_min = time_to_minutes(end_time, is_end_time=True)
    ctx.pending_instructor_bookings.add((instructor_id, booking_date, start_min, end_min))
    ctx.pending_student_bookings.add((student_id, booking_date, start_min, end_min))


def create_booking_bulk(
    session: Session,
    ctx: BulkSeedingContext,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    status: BookingStatus = BookingStatus.COMPLETED,
    **extra_fields: Any,
) -> Booking:
    """
    Create a booking and register it in the bulk context for conflict tracking.
    """
    if start_time.tzinfo is not None:
        start_time = start_time.replace(tzinfo=None)
    if end_time.tzinfo is not None:
        end_time = end_time.replace(tzinfo=None)
    lesson_timezone = extra_fields.get("lesson_timezone") or extra_fields.get("instructor_tz_at_booking")
    student_timezone = extra_fields.get("student_tz_at_booking")
    timezone_fields = _booking_timezone_fields(
        booking_date,
        start_time,
        end_time,
        lesson_timezone=lesson_timezone,
        student_timezone=student_timezone,
    )

    booking = Booking(
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=status,
        **timezone_fields,
        **extra_fields,
    )
    session.add(booking)
    session.flush()

    # Register in context for subsequent conflict detection
    register_pending_booking(ctx, instructor_id, student_id, booking_date, start_time, end_time)

    return booking


__all__ = [
    "SlotSearchDiagnostics",
    "create_booking_safe",
    "find_free_slot_in_bitmap",
    "create_review_booking_pg_safe",
    # Bulk loading utilities
    "BulkSeedingContext",
    "bulk_load_bitmap_data",
    "bulk_load_bookings",
    "create_bulk_seeding_context",
    "find_free_slot_bulk",
    "register_pending_booking",
    "create_booking_bulk",
]
