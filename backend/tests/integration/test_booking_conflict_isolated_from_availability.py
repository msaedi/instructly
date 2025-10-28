from __future__ import annotations

from contextlib import contextmanager
from datetime import time, timedelta
from typing import Iterator, List

from sqlalchemy import event
from sqlalchemy.engine import Engine
from tests.utils.availability_builders import future_week_start

from app.database import engine as global_engine
from app.models.availability import AvailabilitySlot
from app.services.availability_service import AvailabilityService


@contextmanager
def capture_booking_queries(engine: Engine) -> Iterator[List[str]]:
    statements: List[str] = []

    def _listener(conn, cursor, statement, *args) -> None:
        lowered = statement.lower()
        if " bookings" in lowered or "bookings " in lowered:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _listener)


def test_availability_routes_do_not_touch_bookings(db, test_instructor) -> None:
    """Availability fetch/save should not query the bookings tables."""

    monday = future_week_start()
    db.add(
        AvailabilitySlot(
            instructor_id=test_instructor.id,
            specific_date=monday,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    )
    db.commit()

    service = AvailabilityService(db)

    with capture_booking_queries(global_engine) as statements:
        service.get_week_availability(test_instructor.id, monday)
        service.compute_week_version(test_instructor.id, monday, monday + timedelta(days=6))

    assert statements == []
