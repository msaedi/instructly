from datetime import date, time, timedelta

from scripts.seed_utils import SlotSearchDiagnostics, find_free_slot_in_bitmap
from sqlalchemy.orm import Session

from app.models.availability_day import AvailabilityDay
from app.utils.bitset import bits_from_windows


def _add_bitmap(session: Session, instructor_id: str, target_date: date, windows: list[tuple[str, str]]) -> None:
    session.add(
        AvailabilityDay(
            instructor_id=instructor_id,
            day_date=target_date,
            bits=bits_from_windows(windows),
        )
    )
    session.commit()


def test_backward_search_finds_past_slot(unit_db: Session):
    instructor_id = "test_instructor"
    student_id = "test_student"
    base_date = date.today()
    past_date = base_date - timedelta(days=10)

    _add_bitmap(unit_db, instructor_id, past_date, [("10:00:00", "11:00:00")])

    slot, diagnostics = find_free_slot_in_bitmap(
        session=unit_db,
        instructor_id=instructor_id,
        student_id=student_id,
        base_date=base_date,
        lookback_days=14,
        horizon_days=0,
        durations_minutes=[60],
    )

    assert slot is not None
    booking_date, start_time, end_time = slot
    assert booking_date == past_date
    assert start_time == time(10, 0)
    assert end_time == time(11, 0)
    assert isinstance(diagnostics, SlotSearchDiagnostics)
    assert diagnostics.bitmap_days >= 1
    assert diagnostics.instructor_conflicts == 0
    assert diagnostics.student_conflicts == 0


def test_multi_duration_fallback(unit_db: Session):
    instructor_id = "duration_instructor"
    student_id = "duration_student"
    base_date = date.today()

    # Only a 30-minute window exists
    _add_bitmap(unit_db, instructor_id, base_date, [("09:00:00", "09:30:00")])

    slot, diagnostics = find_free_slot_in_bitmap(
        session=unit_db,
        instructor_id=instructor_id,
        student_id=student_id,
        base_date=base_date,
        lookback_days=0,
        horizon_days=0,
        durations_minutes=[60, 45, 30],
    )

    assert slot is not None
    _, start_time, end_time = slot
    assert start_time == time(9, 0)
    assert end_time == time(9, 30)
    assert diagnostics.durations_order == [60, 45, 30]
