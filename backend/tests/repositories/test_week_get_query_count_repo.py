from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.database import engine
from app.models.availability import AvailabilitySlot
from app.repositories.availability_repository import AvailabilityRepository
from tests.utils.sql_count import count_sql


@pytest.mark.usefixtures("STRICT_ON")
def test_repository_get_week_is_single_query(db, test_instructor) -> None:
    week_start = date(2025, 10, 20)
    db.query(AvailabilitySlot).filter(AvailabilitySlot.instructor_id == test_instructor.id).delete()

    slots = []
    for day in range(7):
        current_date = week_start + timedelta(days=day)
        slots.append(
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=current_date,
                start_time=time(9, 0),
                end_time=time(10, 0),
            )
        )
    db.add_all(slots)
    db.commit()

    repo = AvailabilityRepository(db)
    with count_sql(engine) as counter:
        repo.get_week_availability(test_instructor.id, week_start, week_start + timedelta(days=6))

    assert counter.value <= 1
