from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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


def test_filter_by_availability_requires_dates_without_target_date() -> None:
    repo = FilterRepository(_db_for_rows([]))

    with pytest.raises(ValueError, match="dates_to_check is required"):
        repo.filter_by_availability(["inst-1"])


def test_filter_by_availability_returns_empty_without_querying_for_empty_dates_to_check() -> None:
    db = _db_for_rows([])
    repo = FilterRepository(db)

    assert repo.filter_by_availability(["inst-1"], dates_to_check=[]) == {}
    db.execute.assert_not_called()


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


def _query_for_rows(rows: list[object]) -> Mock:
    query = Mock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = rows
    return query


def test_get_buffered_availability_context_skips_queries_when_inputs_are_empty() -> None:
    db = Mock()
    repo = FilterRepository(db)
    expected = {
        "bits_by_key": {},
        "format_tags_by_key": {},
        "bookings_by_key": {},
        "profiles_by_instructor": {},
        "timezones_by_instructor": {},
    }

    assert repo.get_buffered_availability_context([], [date.today()]) == expected
    assert repo.get_buffered_availability_context(["inst-1"], []) == expected
    db.query.assert_not_called()


def test_get_buffered_availability_context_groups_rows_by_instructor_and_date() -> None:
    today = date.today()
    availability_rows = [
        SimpleNamespace(
            instructor_id="inst-1",
            day_date=today,
            bits=b"bits-1",
            format_tags=b"tags-1",
        ),
        SimpleNamespace(
            instructor_id="inst-2",
            day_date=today,
            bits=None,
            format_tags=None,
        ),
        SimpleNamespace(
            instructor_id="inst-1",
            day_date=today + timedelta(days=1),
            bits=b"bits-2",
            format_tags=None,
        ),
    ]
    booking_one = SimpleNamespace(
        instructor_id="inst-1",
        booking_date=today,
        start_time=time(9, 0),
    )
    booking_two = SimpleNamespace(
        instructor_id="inst-1",
        booking_date=today,
        start_time=time(10, 0),
    )
    profile = SimpleNamespace(user_id="inst-1", travel_buffer_minutes=60, non_travel_buffer_minutes=15)
    timezone_row = SimpleNamespace(id="inst-1", timezone="America/New_York")
    db = Mock()
    db.query.side_effect = [
        _query_for_rows(availability_rows),
        _query_for_rows([booking_one, booking_two]),
        _query_for_rows([profile]),
        _query_for_rows([timezone_row]),
    ]
    repo = FilterRepository(db)

    result = repo.get_buffered_availability_context(["inst-1", "inst-2"], [today, today + timedelta(days=1)])

    assert result["bits_by_key"] == {
        ("inst-1", today): b"bits-1",
        ("inst-1", today + timedelta(days=1)): b"bits-2",
    }
    assert result["format_tags_by_key"] == {
        ("inst-1", today): b"tags-1",
    }
    assert result["bookings_by_key"] == {
        ("inst-1", today): [booking_one, booking_two],
    }
    assert result["profiles_by_instructor"] == {"inst-1": profile}
    assert result["timezones_by_instructor"] == {"inst-1": "America/New_York"}
