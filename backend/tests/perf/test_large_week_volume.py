from __future__ import annotations

from datetime import time, timedelta

import pytest
from tests.utils.availability_builders import fan_out_day_slots, future_week_start

from app.models.availability import AvailabilitySlot
from app.services.availability_service import AvailabilityService


@pytest.mark.slow
def test_get_week_handles_large_slot_volume(db, test_instructor) -> None:
    """
    Seed ~1k slots and ensure the week fetch still returns everything quickly.
    """

    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=2)

    total_slots = 0
    for day_offset in range(7):
        day = monday + timedelta(days=day_offset)
        schedule = fan_out_day_slots(
            day,
            start=time(6, 0),
            occurrences=150,
            step_minutes=5,
        )
        total_slots += len(schedule)
        for slot in schedule:
            db.add(
                AvailabilitySlot(
                    instructor_id=test_instructor.id,
                    specific_date=day,
                    start_time=time.fromisoformat(slot["start_time"]),
                    end_time=time.fromisoformat(slot["end_time"]),
                )
            )

    db.commit()

    week_map = service.get_week_availability(test_instructor.id, monday)
    returned = sum(len(entries) for entries in week_map.values())
    assert returned == total_slots
