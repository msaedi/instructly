from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from tests.utils.availability_builders import future_week_start, slot_entry

from app.models.availability import AvailabilitySlot
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService


def test_slot_ending_at_midnight_round_trips(db, test_instructor) -> None:
    """A slot finishing at 00:00 renders without losing the midnight boundary."""
    monday = future_week_start()
    slot_day = monday
    db.add(
        AvailabilitySlot(
            instructor_id=test_instructor.id,
            specific_date=slot_day,
            start_time=time(22, 30),
            end_time=time(0, 0),
        )
    )
    db.commit()

    service = AvailabilityService(db)
    result = service.get_week_availability(test_instructor.id, monday)

    day_entries = result[slot_day.isoformat()]
    assert len(day_entries) == 1
    entry = day_entries[0]
    assert entry["start_time"] == "22:30:00"
    assert entry["end_time"] == "00:00:00"

    next_day = slot_day + timedelta(days=1)
    assert next_day.isoformat() not in result


@pytest.mark.asyncio
async def test_overnight_slot_splits_across_midnight(db, test_instructor) -> None:
    """Overnight inputs split into two segments across the boundary."""
    service = AvailabilityService(db)
    monday = future_week_start()
    payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[
            slot_entry(monday, "22:00", "01:00"),  # crosses midnight
        ],
    )

    await service.save_week_availability(test_instructor.id, payload)
    result = service.get_week_availability(test_instructor.id, monday)
    day_entry = result[monday.isoformat()]
    assert len(day_entry) == 1
    assert day_entry[0]["start_time"] == "22:00:00"
    assert day_entry[0]["end_time"] == "00:00:00"

    tuesday = monday + timedelta(days=1)
    spill_entry = result[tuesday.isoformat()]
    assert len(spill_entry) == 1
    assert spill_entry[0]["start_time"] == "00:00:00"
    assert spill_entry[0]["end_time"] == "01:00:00"


def test_week_rollover_aligns_with_requested_monday(db, test_instructor) -> None:
    """Week map keys should stay within the requested Monday..Sunday window."""
    monday = date(2025, 12, 1)  # explicit future Monday for determinism in tests
    sunday = monday + timedelta(days=6)
    db.add_all(
        [
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=monday,
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=sunday,
                start_time=time(11, 0),
                end_time=time(12, 0),
            ),
        ]
    )
    db.commit()

    service = AvailabilityService(db)
    result = service.get_week_availability(test_instructor.id, monday)

    assert list(sorted(result.keys())) == [monday.isoformat(), sunday.isoformat()]
