"""Additional branch coverage tests for AnalyticsRepository."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.repositories.analytics_repository import AnalyticsRepository


def _query(*, all_result=None, scalar_result=None):
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.distinct.return_value = q
    q.offset.return_value = q
    q.options.return_value = q
    q.update.return_value = 1
    q.all.return_value = [] if all_result is None else all_result
    q.scalar.return_value = scalar_result
    return q


def _dt() -> datetime:
    return datetime(2030, 1, 1, tzinfo=timezone.utc)


def test_booking_aggregate_filters_and_joins():
    db = MagicMock()
    q_count = _query(scalar_result=5)
    q_sum = _query(scalar_result=123.45)
    q_payout = _query(scalar_result=88)
    q_duration = _query(scalar_result=90)
    db.query.side_effect = [q_count, q_sum, q_payout, q_duration]

    repo = AnalyticsRepository(db)

    assert (
        repo.count_bookings(
            start=_dt(),
            end=_dt(),
            date_field="created_at",
            statuses=["CONFIRMED"],
            instructor_ids=["instructor-1"],
            service_catalog_ids=["service-1"],
        )
        == 5
    )
    assert (
        repo.sum_total_price(
            start=_dt(),
            end=_dt(),
            date_field="booking_start_utc",
            statuses=["CONFIRMED"],
            instructor_ids=["instructor-1"],
            service_catalog_ids=["service-1"],
        )
        == 123.45
    )
    assert (
        repo.sum_instructor_payout_cents(
            start=_dt(),
            end=_dt(),
            date_field="created_at",
            statuses=["SETTLED"],
            instructor_ids=["instructor-1"],
        )
        == 88
    )
    assert (
        repo.sum_booking_duration_minutes(
            start=_dt(),
            end=_dt(),
            statuses=["CONFIRMED"],
            instructor_ids=["instructor-1"],
        )
        == 90
    )

    assert q_count.join.called
    assert q_sum.join.called


def test_resolution_helpers_cover_empty_and_populated_inputs():
    db = MagicMock()
    repo = AnalyticsRepository(db)

    assert repo.resolve_category_ids(None) == []
    assert repo.resolve_region_ids(None) == []

    q_category = _query(all_result=[("cat1",), ("cat2",)])
    q_region = _query(all_result=[("reg1",)])
    db.query.side_effect = [q_category, q_region]

    assert repo.resolve_category_ids("music") == ["cat1", "cat2"]
    assert repo.resolve_region_ids("brooklyn") == ["reg1"]


def test_instructor_and_user_count_filters():
    db = MagicMock()
    q_active = _query(all_result=[("u1",), ("u2",)])
    q_created = _query(scalar_result=3)
    q_churned = _query(scalar_result=2)
    q_users_created = _query(scalar_result=7)
    db.query.side_effect = [q_active, q_created, q_churned, q_users_created]

    repo = AnalyticsRepository(db)

    assert (
        repo.list_active_instructor_ids(category_ids=["cat"], region_ids=["reg"])
        == ["u1", "u2"]
    )
    assert (
        repo.count_instructors_created(
            start=_dt(), end=_dt(), category_ids=["cat"], region_ids=["reg"]
        )
        == 3
    )
    assert (
        repo.count_instructors_churned(
            start=_dt(), end=_dt(), category_ids=["cat"], region_ids=["reg"]
        )
        == 2
    )
    assert (
        repo.count_users_created(
            start=_dt(),
            end=_dt(),
            role_name="student",
            phone_verified=True,
        )
        == 7
    )


def test_search_segment_and_booking_role_helpers():
    db = MagicMock()
    q_device = _query(all_result=[("mobile", 4), (None, 1)])
    q_source = _query(all_result=[("google", 2)])
    q_type = _query(all_result=[("keyword", 3)])
    q_bookings_student = _query(all_result=[SimpleNamespace(student_id="s1", instructor_id="i1")])
    q_bookings_instructor = _query(all_result=[SimpleNamespace(student_id="s2", instructor_id="i2")])
    q_availability_ids = _query(all_result=[("ins-1",), ("ins-2",)])
    db.query.side_effect = [
        q_device,
        q_source,
        q_type,
        q_bookings_student,
        q_bookings_instructor,
        q_availability_ids,
    ]

    repo = AnalyticsRepository(db)

    assert repo.get_search_event_segment_counts(start=_dt(), end=_dt(), segment_by="device") == {
        "mobile": 4,
        "unknown": 1,
    }
    assert repo.get_search_event_segment_counts(start=_dt(), end=_dt(), segment_by="source") == {
        "google": 2,
    }
    assert repo.get_search_event_segment_counts(start=_dt(), end=_dt(), segment_by="other") == {
        "keyword": 3,
    }

    assert repo.list_user_ids_with_bookings(user_ids=[], role="student", start=_dt(), end=_dt()) == set()
    assert (
        repo.list_user_ids_with_bookings(
            user_ids=["s1"], role="student", start=_dt(), end=_dt()
        )
        == {"s1"}
    )
    assert (
        repo.list_user_ids_with_bookings(
            user_ids=["i2"], role="instructor", start=_dt(), end=_dt()
        )
        == {"i2"}
    )
    assert repo.list_availability_instructor_ids(["cat"]) == ["ins-1", "ins-2"]


def test_misc_result_mappers():
    db = MagicMock()
    q_rows = _query(
        all_result=[
            ("booking-1", "cat-1", "Music", "CONFIRMED", 100, 80, "student-1", "inst-1"),
        ]
    )
    q_days = _query(all_result=[SimpleNamespace(day_date=date(2030, 1, 1))])
    db.query.side_effect = [q_rows, q_days]

    repo = AnalyticsRepository(db)

    rows = repo.list_category_booking_rows(start=_dt(), end=_dt(), statuses=["CONFIRMED"])
    assert rows[0].category_name == "Music"
    assert repo.list_availability_days(instructor_ids=[], start_date=date(2030, 1, 1), end_date=date(2030, 1, 2)) == []
    out = repo.list_availability_days(
        instructor_ids=["inst-1"], start_date=date(2030, 1, 1), end_date=date(2030, 1, 2)
    )
    assert len(out) == 1
