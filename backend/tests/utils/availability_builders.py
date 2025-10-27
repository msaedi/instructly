from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict


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
