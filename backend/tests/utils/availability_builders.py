from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Sequence

from app.utils.bitmap_base64 import decode_bitmap_bytes, encode_bitmap_bytes
from app.utils.bitset import bits_from_windows, new_empty_tags, windows_from_bits


def next_monday(today: date | None = None) -> date:
    """Return the next Monday strictly after today (or the provided date)."""
    current = today or date.today()
    days_ahead = (7 - current.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return current + timedelta(days=days_ahead)


def future_week_start(weeks_ahead: int = 1) -> date:
    """Return a Monday in the future used for availability tests."""
    if weeks_ahead <= 0:
        raise ValueError("weeks_ahead must be positive")
    base = next_monday()
    return base + timedelta(days=7 * (weeks_ahead - 1))


def _group_slot_windows(slots: Sequence[Dict[str, str]]) -> Dict[str, List[tuple[str, str]]]:
    grouped: Dict[str, List[tuple[str, str]]] = {}
    for slot in slots:
        grouped.setdefault(slot["date"], []).append((slot["start_time"], slot["end_time"]))
    return grouped


def build_week_payload(week_start: date, slot_count: int, clear_existing: bool = True) -> Dict[str, object]:
    """Build a bitmap-native week payload with non-overlapping slots across the week."""

    if slot_count <= 0:
        raise ValueError("slot_count must be positive")

    schedule = []
    days = [week_start + timedelta(days=i) for i in range(7)]
    duration_minutes = 60

    for idx in range(slot_count):
        target_day = days[idx % len(days)]
        hour_block = (idx // len(days)) % 8  # keep within daytime hours
        start_hour = 8 + hour_block
        start_dt = datetime.combine(  # tz-pattern-ok: test utility builds fixtures
            target_day, time(start_hour, 0)
        )
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        schedule.append(
            {
                "date": target_day.isoformat(),
                "start_time": start_dt.strftime("%H:%M"),
                "end_time": end_dt.strftime("%H:%M"),
            }
        )

    return build_week_payload_from_slots(week_start, schedule, clear_existing=clear_existing)


def slot_entry(target_date: date, start_time: str, end_time: str) -> Dict[str, str]:
    """Return a minimal schedule entry for the given date."""
    return {
        "date": target_date.isoformat(),
        "start_time": start_time,
        "end_time": end_time,
    }


def build_week_payload_from_slots(
    week_start: date,
    slots: Iterable[Dict[str, str]],
    *,
    clear_existing: bool = True,
) -> Dict[str, object]:
    """Construct a bitmap-native payload from pre-built slot dictionaries."""
    grouped = _group_slot_windows(list(slots))
    days = [
        {
            "date": day,
            "bits": encode_bitmap_bytes(bits_from_windows(windows)),
            "format_tags": encode_bitmap_bytes(new_empty_tags()),
        }
        for day, windows in sorted(grouped.items())
    ]
    return {
        "week_start": week_start.isoformat(),
        "clear_existing": clear_existing,
        "days": days,
    }


def build_week_payload_from_windows_by_date(
    week_start: date,
    windows_by_date: Dict[str, Sequence[Dict[str, str]]],
    *,
    clear_existing: bool = True,
) -> Dict[str, object]:
    """Construct a bitmap-native payload from a date -> windows mapping."""
    slots: list[Dict[str, str]] = []
    for day, windows in windows_by_date.items():
        for window in windows:
            slots.append(
                {
                    "date": day,
                    "start_time": window["start_time"],
                    "end_time": window["end_time"],
                }
            )
    return build_week_payload_from_slots(week_start, slots, clear_existing=clear_existing)


def decode_week_response_to_windows(body: Dict[str, object]) -> Dict[str, List[Dict[str, str]]]:
    """Decode the bitmap-native GET /week response body into date -> windows."""
    result: Dict[str, List[Dict[str, str]]] = {}
    for day in body.get("days", []):
        if not isinstance(day, dict):
            continue
        day_date = day.get("date")
        bits_b64 = day.get("bits")
        if not isinstance(day_date, str) or not isinstance(bits_b64, str):
            continue
        bits = decode_bitmap_bytes(bits_b64, 36)
        result[day_date] = [
            {"start_time": start_time, "end_time": end_time}
            for start_time, end_time in windows_from_bits(bits)
        ]
    return result


def fan_out_day_slots(
    day: date,
    *,
    start: time,
    occurrences: int,
    step_minutes: int,
) -> List[Dict[str, str]]:
    """
    Generate a series of fixed-width slots for a single day.

    Useful for bulk-tests (e.g., thousands of slots). Slots use the provided
    start time and repeat every ``step_minutes``.
    """
    slots: list[Dict[str, str]] = []
    base_dt = datetime.combine(day, start)  # tz-pattern-ok: test utility builds fixtures
    step = timedelta(minutes=step_minutes)
    for i in range(occurrences):
        begin = (base_dt + step * i).time()
        end = (datetime.combine(day, begin) + step).time()  # tz-pattern-ok: test utility builds fixtures
        slots.append(
            {
                "date": day.isoformat(),
                "start_time": begin.strftime("%H:%M"),
                "end_time": end.strftime("%H:%M"),
            }
        )
    return slots
