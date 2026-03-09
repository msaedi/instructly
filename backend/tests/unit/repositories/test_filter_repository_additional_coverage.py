from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from app.repositories.filter_repository import FilterRepository


def _db_for_rows(rows, *, dialect: str = "postgresql") -> Mock:
    db = Mock()
    db.bind = None if dialect is None else SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    db.execute.return_value = rows
    return db


def test_get_instructor_min_distance_to_regions_returns_empty_for_non_postgres() -> None:
    db = _db_for_rows([], dialect="sqlite")
    repo = FilterRepository(db)

    assert repo.get_instructor_min_distance_to_regions(["inst-1"], ["region-1"]) == {}
    db.execute.assert_not_called()


def test_get_instructor_min_distance_to_regions_skips_null_distances() -> None:
    db = Mock()
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.execute.return_value.fetchall.return_value = [
        ("inst-1", None),
        ("inst-1", 12.5),
        ("inst-2", 3.0),
    ]
    repo = FilterRepository(db)

    result = repo.get_instructor_min_distance_to_regions(["inst-1", "inst-2"], ["region-1"])

    assert result == {"inst-1": 12.5, "inst-2": 3.0}


def test_filter_by_availability_groups_multiple_days_for_same_instructor() -> None:
    today = date.today()
    rows = [
        SimpleNamespace(instructor_id="inst-1", day_date=today),
        SimpleNamespace(instructor_id="inst-1", day_date=today + timedelta(days=1)),
        SimpleNamespace(instructor_id="inst-2", day_date=today),
    ]
    repo = FilterRepository(_db_for_rows(rows))

    result = repo.filter_by_availability(["inst-1", "inst-2"], target_date=today)

    assert result == {
        "inst-1": [today, today + timedelta(days=1)],
        "inst-2": [today],
    }


def test_check_weekend_availability_groups_duplicate_instructor_rows() -> None:
    saturday = date.today()
    sunday = saturday + timedelta(days=1)
    rows = [
        SimpleNamespace(instructor_id="inst-1", day_date=saturday),
        SimpleNamespace(instructor_id="inst-1", day_date=sunday),
    ]
    repo = FilterRepository(_db_for_rows(rows))

    result = repo.check_weekend_availability(["inst-1"], saturday, sunday)

    assert result == {"inst-1": [saturday, sunday]}


def test_get_lesson_type_rates_rejects_any_and_unknown_types_without_querying() -> None:
    db = _db_for_rows([])
    repo = FilterRepository(db)

    assert repo.get_lesson_type_rates(["service-1"], "any") == {}
    assert repo.get_lesson_type_rates(["service-1"], "hybrid") == {}
    db.execute.assert_not_called()
