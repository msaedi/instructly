from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database import engine
from app.repositories.availability_day_repository import AvailabilityDayRepository
from tests._utils.bitmap_avail import seed_week
from tests.utils.sql_count import count_sql


@pytest.mark.usefixtures("STRICT_ON")
def test_repository_get_week_is_single_query(db, test_instructor) -> None:
    week_start = date(2025, 10, 20)

    # Seed week using bitmap storage
    week_map = {}
    for day in range(7):
        current_date = week_start + timedelta(days=day)
        week_map[current_date.isoformat()] = [("09:00", "10:00")]
    seed_week(db, test_instructor.id, week_start, week_map)

    repo = AvailabilityDayRepository(db)
    with count_sql(engine) as counter:
        repo.get_week(test_instructor.id, week_start)

    assert counter.value <= 1
