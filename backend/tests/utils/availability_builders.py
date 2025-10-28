from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict


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


def build_week_payload(week_start: date, slot_count: int, clear_existing: bool = True) -> Dict[str, object]:
    """Build a week payload with non-overlapping slots across the week."""

    if slot_count <= 0:
        raise ValueError("slot_count must be positive")

    schedule = []
    days = [week_start + timedelta(days=i) for i in range(7)]
    duration_minutes = 60

    for idx in range(slot_count):
        target_day = days[idx % len(days)]
        hour_block = (idx // len(days)) % 8  # keep within daytime hours
        start_hour = 8 + hour_block
        start_dt = datetime.combine(target_day, time(start_hour, 0))
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        schedule.append(
            {
                "date": target_day.isoformat(),
                "start_time": start_dt.strftime("%H:%M"),
                "end_time": end_dt.strftime("%H:%M"),
            }
        )

    return {
        "week_start": week_start.isoformat(),
        "clear_existing": clear_existing,
        "schedule": schedule,
    }
