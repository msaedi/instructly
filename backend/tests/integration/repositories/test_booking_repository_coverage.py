from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import RoleName
from app.core.exceptions import RepositoryException
from app.models.booking import BookingStatus, PaymentStatus
from app.repositories.booking_repository import BookingRepository

try:  # pragma: no cover - allow running from backend/ root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe
    from tests.utils.booking_timezone import booking_timezone_fields


def _create_booking(
    db,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    status: BookingStatus,
    offset_index: int,
    allow_overlap: bool = False,
    **overrides,
):
    base_fields = {
        "service_name": "Test Service",
        "hourly_rate": 50.0,
        "total_price": 50.0,
        "duration_minutes": 60,
        "meeting_location": "Test Location",
        "service_area": "Manhattan",
        "location_type": "neutral",
    }
    base_fields.update(booking_timezone_fields(booking_date, start_time, end_time))
    base_fields.update(overrides)
    return create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        status=status,
        allow_overlap=allow_overlap,
        offset_index=offset_index,
        **base_fields,
    )


def test_time_conflict_and_opportunities(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)

    overlapping = repo.get_bookings_by_time_range(
        instructor_id=test_instructor_with_availability.id,
        booking_date=test_booking.booking_date,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )
    assert overlapping

    assert (
        repo.check_time_conflict(
            instructor_id=test_instructor_with_availability.id,
            booking_date=test_booking.booking_date,
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        is True
    )
    assert (
        repo.check_time_conflict(
            instructor_id=test_instructor_with_availability.id,
            booking_date=test_booking.booking_date,
            start_time=time(13, 0),
            end_time=time(14, 0),
        )
        is False
    )

    student_conflicts = repo.check_student_time_conflict(
        student_id=test_student.id,
        booking_date=test_booking.booking_date,
        start_time=time(10, 0),
        end_time=time(11, 0),
    )
    assert len(student_conflicts) == 1

    target_date = test_booking.booking_date + timedelta(days=2)
    _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=target_date,
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=0,
    )
    db.commit()

    slots = [{"start_time": time(9, 0), "end_time": time(12, 0)}]
    opportunities = repo.find_booking_opportunities(
        available_slots=slots,
        instructor_id=test_instructor_with_availability.id,
        target_date=target_date,
        duration_minutes=60,
    )
    assert [o["start_time"] for o in opportunities] == ["10:00:00", "11:00:00"]


def test_student_instructor_filters_and_counts(
    db, test_student, test_instructor_with_availability, test_instructor_2, test_booking
):
    repo = BookingRepository(db)
    today = datetime.now(timezone.utc).date()

    completed_booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today - timedelta(days=2),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.COMPLETED,
        offset_index=1,
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
        total_price=120.0,
    )
    past_confirmed = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today - timedelta(days=1),
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=2,
    )
    future_cancelled = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=3),
        start_time=time(13, 0),
        end_time=time(14, 0),
        status=BookingStatus.CANCELLED,
        offset_index=3,
        cancelled_at=datetime.now(timezone.utc),
        cancellation_reason="Test",
    )
    _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=4),
        start_time=time(15, 0),
        end_time=time(16, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=4,
    )
    db.commit()

    upcoming = repo.get_student_bookings(
        test_student.id, upcoming_only=True
    )
    assert all(b.status == BookingStatus.CONFIRMED for b in upcoming)

    history = repo.get_student_bookings(
        test_student.id, exclude_future_confirmed=True
    )
    history_ids = {b.id for b in history}
    assert completed_booking.id in history_ids
    assert past_confirmed.id in history_ids
    assert future_cancelled.id in history_ids

    past_completed = repo.get_student_bookings(
        test_student.id,
        status=BookingStatus.COMPLETED,
        include_past_confirmed=True,
    )
    assert [b.id for b in past_completed] == [completed_booking.id]

    instructor_upcoming = repo.get_instructor_bookings(
        test_instructor_with_availability.id, upcoming_only=True
    )
    assert instructor_upcoming

    distinct_dates = repo.get_distinct_booking_dates(
        test_instructor_with_availability.id
    )
    assert completed_booking.booking_date in distinct_dates

    count_last_30 = repo.count_instructor_completed_last_30d(
        test_instructor_with_availability.id
    )
    assert count_last_30 >= 1
    assert repo.get_instructor_last_completed_at(
        test_instructor_with_availability.id
    ) is not None

    start = today - timedelta(days=5)
    end = today + timedelta(days=5)
    assert repo.count_bookings_in_date_range(start, end) >= 1
    assert repo.sum_total_price_in_date_range(start, end) >= 50

    status_counts = repo.count_bookings_by_status(
        test_student.id, RoleName.STUDENT
    )
    assert status_counts[BookingStatus.CONFIRMED.value] >= 1

    instructor_date_bookings = repo.get_instructor_bookings_for_date(
        test_instructor_with_availability.id, past_confirmed.booking_date
    )
    assert instructor_date_bookings

    week_dates = [
        (today - timedelta(days=3)) + timedelta(days=offset) for offset in range(7)
    ]
    week_bookings = repo.get_bookings_for_week(
        test_instructor_with_availability.id,
        week_dates=week_dates,
    )
    assert week_bookings

    pair_bookings = repo.get_bookings_by_student_and_instructor(
        test_student.id, test_instructor_with_availability.id
    )
    assert pair_bookings

    other_pair = repo.get_bookings_by_student_and_instructor(
        test_student.id, test_instructor_2.id
    )
    assert other_pair == []


def test_payment_and_status_updates(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    today = datetime.now(timezone.utc).date()

    scheduled = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today,
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=5,
        payment_status=PaymentStatus.SCHEDULED.value,
        payment_method_id="pm_test",
    )
    retry = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=1),
        start_time=time(10, 0),
        end_time=time(11, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=6,
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        payment_method_id="pm_retry",
    )
    _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today - timedelta(days=1),
        start_time=time(12, 0),
        end_time=time(13, 0),
        status=BookingStatus.COMPLETED,
        offset_index=7,
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_test",
        completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    auto_completion = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=2),
        start_time=time(14, 0),
        end_time=time(15, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=8,
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_auto",
    )
    no_show = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today - timedelta(days=5),
        start_time=time(16, 0),
        end_time=time(17, 0),
        status=BookingStatus.NO_SHOW,
        offset_index=9,
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(days=2),
        payment_status=PaymentStatus.MANUAL_REVIEW.value,
    )
    db.commit()

    assert repo.get_bookings_for_payment_authorization()
    assert repo.get_bookings_for_payment_retry()
    assert repo.get_bookings_for_payment_capture()
    assert repo.get_bookings_for_auto_completion()
    assert repo.get_bookings_with_expired_auth()

    overdue = repo.count_overdue_authorizations(today)
    assert overdue >= 1

    completed_count = repo.count_completed_lessons(
        instructor_user_id=test_instructor_with_availability.id,
        window_start=datetime.now(timezone.utc) - timedelta(days=7),
        window_end=datetime.now(timezone.utc),
    )
    assert completed_count >= 1
    assert repo.count_instructor_total_completed(
        test_instructor_with_availability.id
    ) >= 1
    assert repo.count_student_completed_lifetime(test_student.id) >= 1
    assert repo.get_student_most_recent_completed_at(test_student.id) is not None

    owned = repo.filter_owned_booking_ids(
        [scheduled.id, retry.id], test_student.id
    )
    assert scheduled.id in owned

    upcoming = repo.find_upcoming_for_pair(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    assert upcoming

    batch = repo.batch_find_upcoming_for_pairs(
        pairs=[(test_student.id, test_instructor_with_availability.id)],
        user_id=test_student.id,
    )
    assert batch[(test_student.id, test_instructor_with_availability.id)]

    completed = repo.complete_booking(scheduled.id)
    assert completed.status == BookingStatus.COMPLETED

    cancelled = repo.cancel_booking(retry.id, test_student.id, reason="Cancel")
    assert cancelled.status == BookingStatus.CANCELLED

    no_show_marked = repo.mark_no_show(auto_completion.id)
    assert no_show_marked.status == BookingStatus.NO_SHOW

    due = repo.get_no_show_reports_due_for_resolution(
        reported_before=datetime.now(timezone.utc) - timedelta(days=1)
    )
    assert no_show.id in [b.id for b in due]


def test_booking_details_and_future_queries(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    today = datetime.now(timezone.utc).date()

    future_confirmed = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=2),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=10,
    )
    future_cancelled = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=3),
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.CANCELLED,
        offset_index=11,
    )
    db.commit()

    details = repo.get_booking_with_details(test_booking.id)
    assert details is not None
    assert details.student is not None
    assert details.instructor is not None

    pricing = repo.get_with_pricing_context(test_booking.id)
    assert pricing is not None
    assert pricing.instructor_service is not None

    locked = repo.get_by_id_for_update(test_booking.id)
    assert locked is not None
    assert repo.get_by_id_for_update("missing") is None

    upcoming = repo.get_instructor_future_bookings(
        test_instructor_with_availability.id, from_date=None, exclude_cancelled=True
    )
    assert future_confirmed.id in [b.id for b in upcoming]
    assert future_cancelled.id not in [b.id for b in upcoming]

    all_future = repo.get_instructor_future_bookings(
        test_instructor_with_availability.id, from_date=None, exclude_cancelled=False
    )
    assert future_cancelled.id in [b.id for b in all_future]

    day_bookings = repo.get_instructor_bookings_for_date(
        test_instructor_with_availability.id,
        today + timedelta(days=2),
        status_filter=[BookingStatus.CONFIRMED],
    )
    assert future_confirmed.id in [b.id for b in day_bookings]


def test_service_catalog_and_week_queries(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    today = datetime.now(timezone.utc).date()

    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=1),
        start_time=time(13, 0),
        end_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=12,
    )
    db.commit()

    service_catalog_id = booking.instructor_service.service_catalog_id

    service_bookings = repo.get_bookings_for_service_catalog(
        service_catalog_id, from_date=today - timedelta(days=1), to_date=today + timedelta(days=2)
    )
    assert booking.id in [b.id for b in service_bookings]

    grouped = repo.get_all_bookings_by_service_catalog(
        from_date=today - timedelta(days=1), to_date=today + timedelta(days=2)
    )
    assert str(service_catalog_id) in grouped

    week_dates = [(today - timedelta(days=1)) + timedelta(days=i) for i in range(7)]
    week = repo.get_bookings_for_week(
        test_instructor_with_availability.id, week_dates=week_dates
    )
    assert booking.id in [b.id for b in week]


def test_admin_and_date_filters(db, test_student, test_instructor_with_availability, test_booking):
    repo = BookingRepository(db)
    today = datetime.now(timezone.utc).date()

    refunded = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today,
        start_time=time(15, 0),
        end_time=time(16, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=13,
        payment_status=PaymentStatus.SETTLED.value,
        settlement_outcome="admin_refund",
        payment_intent_id="pi_refund",
    )
    pending = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today,
        start_time=time(17, 0),
        end_time=time(18, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=14,
        payment_status=None,
    )
    db.commit()

    results, total = repo.list_admin_bookings(
        search=test_student.email,
        statuses=[BookingStatus.CONFIRMED.value],
        payment_statuses=["refunded"],
        date_from=today - timedelta(days=1),
        date_to=today + timedelta(days=1),
        needs_action=False,
        now=None,
        page=1,
        per_page=10,
    )
    assert total >= 1
    assert refunded.id in [b.id for b in results]

    pending_results, pending_total = repo.list_admin_bookings(
        search=None,
        statuses=None,
        payment_statuses=["pending"],
        date_from=None,
        date_to=None,
        needs_action=None,
        now=None,
        page=1,
        per_page=10,
    )
    assert pending_total >= 1
    assert pending.id in [b.id for b in pending_results]

    future_now = datetime.now(timezone.utc) + timedelta(days=1)
    needs_action_results, _ = repo.list_admin_bookings(
        search=None,
        statuses=None,
        payment_statuses=None,
        date_from=None,
        date_to=None,
        needs_action=True,
        now=future_now,
        page=1,
        per_page=10,
    )
    assert pending.id in [b.id for b in needs_action_results]

    assert repo.count_pending_completion(future_now) >= 1
    assert repo.get_instructor_bookings_for_stats(
        test_instructor_with_availability.id
    )

    daily = repo.get_bookings_for_date(today, status=BookingStatus.CONFIRMED, with_relationships=True)
    assert pending.id in [b.id for b in daily]

    by_status = repo.get_bookings_by_date_and_status(today, BookingStatus.CONFIRMED.value)
    assert pending.id in [b.id for b in by_status]

    by_range = repo.get_bookings_by_date_range_and_status(
        today - timedelta(days=1), today + timedelta(days=1), BookingStatus.CONFIRMED.value
    )
    assert pending.id in [b.id for b in by_range]

    assert repo.count_old_bookings(datetime.now(timezone.utc) + timedelta(days=1)) >= 1


def test_booking_repository_branch_filters(
    db, test_student, test_instructor_with_availability, test_booking, monkeypatch
):
    repo = BookingRepository(db)
    fixed_now = datetime(2026, 1, 14, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "app.repositories.booking_repository.get_user_now_by_id",
        lambda *_: fixed_now,
    )
    monkeypatch.setattr(
        "app.repositories.booking_repository.get_user_today_by_id",
        lambda *_: fixed_now.date(),
    )

    past_completed = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.COMPLETED,
        offset_index=15,
        allow_overlap=True,
        completed_at=fixed_now - timedelta(hours=2),
    )
    today_ended = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date(),
        start_time=time(8, 0),
        end_time=time(9, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=16,
        allow_overlap=True,
    )
    today_future = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date(),
        start_time=time(13, 0),
        end_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=17,
        allow_overlap=True,
    )
    future_date = fixed_now.date() + timedelta(days=5)
    future_confirmed = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=future_date,
        start_time=time(13, 0),
        end_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=18,
        allow_overlap=True,
    )
    future_cancelled_visible = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=future_date,
        start_time=time(15, 0),
        end_time=time(16, 0),
        status=BookingStatus.CANCELLED,
        offset_index=19,
        allow_overlap=True,
        cancellation_reason="Student cancelled",
    )
    future_cancelled_hidden = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=future_date,
        start_time=time(17, 0),
        end_time=time(18, 0),
        status=BookingStatus.CANCELLED,
        offset_index=20,
        allow_overlap=True,
        cancellation_reason="Rescheduled",
    )
    db.commit()

    conflicts = repo.get_bookings_by_time_range(
        instructor_id=test_instructor_with_availability.id,
        booking_date=fixed_now.date(),
        start_time=time(13, 0),
        end_time=time(14, 0),
        exclude_booking_id=today_future.id,
    )
    assert today_future.id not in [b.id for b in conflicts]
    assert (
        repo.check_time_conflict(
            instructor_id=test_instructor_with_availability.id,
            booking_date=fixed_now.date(),
            start_time=time(13, 0),
            end_time=time(14, 0),
            exclude_booking_id=today_future.id,
        )
        is False
    )
    assert (
        repo.check_student_time_conflict(
            student_id=test_student.id,
            booking_date=fixed_now.date(),
            start_time=time(13, 0),
            end_time=time(14, 0),
            exclude_booking_id=today_future.id,
        )
        == []
    )

    history = repo.get_student_bookings(
        test_student.id,
        exclude_future_confirmed=True,
    )
    history_ids = {b.id for b in history}
    assert past_completed.id in history_ids
    assert today_ended.id in history_ids
    assert future_cancelled_visible.id in history_ids
    assert future_confirmed.id not in history_ids
    assert future_cancelled_hidden.id not in history_ids

    book_again = repo.get_student_bookings(
        test_student.id,
        status=BookingStatus.COMPLETED,
        include_past_confirmed=True,
    )
    assert past_completed.id in [b.id for b in book_again]

    instructor_history = repo.get_instructor_bookings(
        test_instructor_with_availability.id,
        exclude_future_confirmed=True,
        limit=2,
    )
    assert instructor_history
    assert len(instructor_history) <= 2
    assert future_confirmed.id not in [b.id for b in instructor_history]

    full_history = repo.get_instructor_bookings(
        test_instructor_with_availability.id,
        exclude_future_confirmed=True,
    )
    assert past_completed.id in [b.id for b in full_history]

    instructor_book_again = repo.get_instructor_bookings(
        test_instructor_with_availability.id,
        status=BookingStatus.COMPLETED,
        include_past_confirmed=True,
    )
    assert past_completed.id in [b.id for b in instructor_book_again]

    week_dates = [fixed_now.date() + timedelta(days=offset) for offset in range(7)]
    filtered_week = repo.get_bookings_for_week(
        test_instructor_with_availability.id,
        week_dates=week_dates,
        status_filter=[BookingStatus.CONFIRMED],
    )
    assert future_confirmed.id in [b.id for b in filtered_week]

    instructor_counts = repo.count_bookings_by_status(
        test_instructor_with_availability.id, RoleName.INSTRUCTOR
    )
    assert instructor_counts[BookingStatus.CONFIRMED.value] >= 1
    assert repo.count_bookings_by_status(test_student.id, "unknown") == {
        status.value: 0 for status in BookingStatus
    }


def test_admin_payment_status_filter_regular(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    today = datetime.now(timezone.utc).date()
    authorized = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today,
        start_time=time(9, 30),
        end_time=time(10, 30),
        status=BookingStatus.CONFIRMED,
        offset_index=21,
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_auth",
    )
    db.commit()

    results, _ = repo.list_admin_bookings(
        search=None,
        statuses=None,
        payment_statuses=[PaymentStatus.AUTHORIZED.value],
        date_from=None,
        date_to=None,
        needs_action=None,
        now=None,
        page=1,
        per_page=10,
    )
    assert authorized.id in [b.id for b in results]


def test_locked_funds_capture_and_auto_completion(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    now = datetime.now(timezone.utc)

    locked_capture = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=now.date(),
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.COMPLETED,
        offset_index=22,
        completed_at=now,
        has_locked_funds=True,
        rescheduled_from_booking_id=test_booking.id,
    )
    locked_auto = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=now.date() + timedelta(days=1),
        start_time=time(12, 0),
        end_time=time(13, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=23,
        has_locked_funds=True,
        rescheduled_from_booking_id=test_booking.id,
    )
    db.commit()

    capture_ids = {b.id for b in repo.get_bookings_for_payment_capture()}
    assert locked_capture.id in capture_ids
    auto_ids = {b.id for b in repo.get_bookings_for_auto_completion()}
    assert locked_auto.id in auto_ids


def test_service_catalog_without_to_date(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    today = datetime.now(timezone.utc).date()
    booking = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=today + timedelta(days=10),
        start_time=time(13, 0),
        end_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=24,
        allow_overlap=True,
    )
    db.commit()

    service_catalog_id = booking.instructor_service.service_catalog_id
    results = repo.get_bookings_for_service_catalog(
        service_catalog_id, from_date=today - timedelta(days=1), to_date=None
    )
    assert booking.id in [b.id for b in results]

    grouped = repo.get_all_bookings_by_service_catalog(
        from_date=today - timedelta(days=1), to_date=None
    )
    assert str(service_catalog_id) in grouped


def test_batch_find_upcoming_pairs_empty_and_student_recent_none(
    db, test_student, test_instructor_2
):
    repo = BookingRepository(db)
    assert repo.batch_find_upcoming_for_pairs([], user_id=test_student.id) == {}
    assert repo.get_student_most_recent_completed_at(test_instructor_2.id) is None


def test_admin_payment_status_combined_and_needs_action_same_day(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    booking_date = now.date()

    pending_none = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=booking_date,
        start_time=time(8, 0),
        end_time=time(9, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=25,
        payment_status=None,
        allow_overlap=True,
    )
    pending_method = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=booking_date,
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=26,
        payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value,
        allow_overlap=True,
    )
    refunded = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=booking_date,
        start_time=time(10, 0),
        end_time=time(11, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=27,
        payment_status=PaymentStatus.SETTLED.value,
        settlement_outcome="admin_refund",
        allow_overlap=True,
    )
    authorized = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=booking_date,
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=28,
        payment_status=PaymentStatus.AUTHORIZED.value,
        payment_intent_id="pi_auth_combo",
        allow_overlap=True,
    )
    needs_action = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=booking_date,
        start_time=time(6, 0),
        end_time=time(7, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=29,
        allow_overlap=True,
    )
    db.commit()

    results, _ = repo.list_admin_bookings(
        search=None,
        statuses=None,
        payment_statuses=[
            "pending",
            "refunded",
            PaymentStatus.AUTHORIZED.value,
        ],
        date_from=None,
        date_to=None,
        needs_action=None,
        now=None,
        page=1,
        per_page=20,
    )
    result_ids = {booking.id for booking in results}
    assert pending_none.id in result_ids
    assert pending_method.id in result_ids
    assert refunded.id in result_ids
    assert authorized.id in result_ids

    needs_action_results, _ = repo.list_admin_bookings(
        search=None,
        statuses=None,
        payment_statuses=None,
        date_from=None,
        date_to=None,
        needs_action=True,
        now=now,
        page=1,
        per_page=20,
    )
    assert needs_action.id in [booking.id for booking in needs_action_results]


def test_filter_owned_booking_ids_empty_and_batch_limit(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)
    assert repo.filter_owned_booking_ids([], test_student.id) == []

    future_date = datetime.now(timezone.utc).date() + timedelta(days=2)
    _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=future_date,
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=30,
        allow_overlap=True,
    )
    _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=future_date,
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=31,
        allow_overlap=True,
    )
    db.commit()

    results = repo.batch_find_upcoming_for_pairs(
        pairs=[(test_student.id, test_instructor_with_availability.id)],
        user_id=test_student.id,
        limit_per_pair=1,
    )
    assert len(results[(test_student.id, test_instructor_with_availability.id)]) == 1


def test_student_and_instructor_booking_branch_filters(
    db, test_student, test_instructor_with_availability, test_booking, monkeypatch
):
    repo = BookingRepository(db)
    fixed_now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "app.repositories.booking_repository.get_user_now_by_id",
        lambda *_: fixed_now,
    )

    past_completed = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date() - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.COMPLETED,
        offset_index=32,
        allow_overlap=True,
        completed_at=fixed_now - timedelta(hours=2),
    )
    today_ended = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date(),
        start_time=time(8, 0),
        end_time=time(9, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=33,
        allow_overlap=True,
    )
    today_future = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date(),
        start_time=time(13, 0),
        end_time=time(14, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=34,
        allow_overlap=True,
    )
    future_confirmed = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date() + timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(10, 0),
        status=BookingStatus.CONFIRMED,
        offset_index=35,
        allow_overlap=True,
    )
    future_cancelled = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date() + timedelta(days=2),
        start_time=time(10, 0),
        end_time=time(11, 0),
        status=BookingStatus.CANCELLED,
        offset_index=36,
        allow_overlap=True,
        cancellation_reason="Student cancelled",
    )
    future_rescheduled = _create_booking(
        db,
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=fixed_now.date() + timedelta(days=3),
        start_time=time(11, 0),
        end_time=time(12, 0),
        status=BookingStatus.CANCELLED,
        offset_index=37,
        allow_overlap=True,
        cancellation_reason="Rescheduled",
    )
    db.commit()

    with repo.with_cache_disabled():
        upcoming = repo.get_student_bookings(test_student.id, upcoming_only=True)
    upcoming_ids = {b.id for b in upcoming}
    assert today_future.id in upcoming_ids
    assert future_confirmed.id in upcoming_ids
    assert today_ended.id not in upcoming_ids

    with repo.with_cache_disabled():
        history = repo.get_student_bookings(
            test_student.id,
            exclude_future_confirmed=True,
        )
    history_ids = {b.id for b in history}
    assert past_completed.id in history_ids
    assert today_ended.id in history_ids
    assert future_cancelled.id in history_ids
    assert future_confirmed.id not in history_ids
    assert future_rescheduled.id not in history_ids

    with repo.with_cache_disabled():
        past_only = repo.get_student_bookings(
            test_student.id,
            status=BookingStatus.COMPLETED,
            include_past_confirmed=True,
        )
    assert past_completed.id in [b.id for b in past_only]

    with repo.with_cache_disabled():
        cancelled_only = repo.get_student_bookings(
            test_student.id,
            status=BookingStatus.CANCELLED,
        )
    assert future_cancelled.id in [b.id for b in cancelled_only]

    instructor_upcoming = repo.get_instructor_bookings(
        test_instructor_with_availability.id,
        upcoming_only=True,
    )
    assert today_future.id in [b.id for b in instructor_upcoming]

    instructor_history = repo.get_instructor_bookings(
        test_instructor_with_availability.id,
        exclude_future_confirmed=True,
    )
    assert future_confirmed.id not in [b.id for b in instructor_history]

    instructor_book_again = repo.get_instructor_bookings(
        test_instructor_with_availability.id,
        status=BookingStatus.COMPLETED,
        include_past_confirmed=True,
    )
    assert past_completed.id in [b.id for b in instructor_book_again]


def test_booking_repository_additional_branches(
    db, test_student, test_instructor_with_availability, test_booking
):
    repo = BookingRepository(db)

    locked = repo.get_by_id_for_update(
        test_booking.id, load_relationships=False, populate_existing=False
    )
    assert locked is not None

    results, _ = repo.list_admin_bookings(
        search=None,
        statuses=[""],
        payment_statuses=[""],
        date_from=None,
        date_to=None,
        needs_action=None,
        now=None,
        page=1,
        per_page=5,
    )
    assert isinstance(results, list)

    today = test_booking.booking_date
    plain = repo.get_bookings_for_date(today, status=None, with_relationships=False)
    assert isinstance(plain, list)

    with repo.with_cache_disabled():
        limited = repo.get_student_bookings(test_student.id, limit=1)
    assert len(limited) <= 1

    limited_instructor = repo.get_instructor_bookings(
        test_instructor_with_availability.id, limit=1
    )
    assert len(limited_instructor) <= 1

    future = repo.get_instructor_future_bookings(
        test_instructor_with_availability.id,
        from_date=today,
        exclude_cancelled=False,
    )
    assert future

    duplicate_data = {
        col.name: getattr(test_booking, col.name)
        for col in test_booking.__table__.columns
    }
    # Avoid identity map warnings when intentionally inserting a duplicate PK.
    db.expunge_all()
    with pytest.raises(IntegrityError):
        repo.create(**duplicate_data)
    db.rollback()


def test_booking_repository_error_paths(
    db, test_student, test_instructor_with_availability, monkeypatch
):
    repo = BookingRepository(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db failure")

    monkeypatch.setattr(repo.db, "query", _boom)

    with pytest.raises(RepositoryException):
        repo.get_bookings_by_time_range(
            instructor_id=test_instructor_with_availability.id,
            booking_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    with pytest.raises(RepositoryException):
        repo.check_time_conflict(
            instructor_id=test_instructor_with_availability.id,
            booking_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    with pytest.raises(RepositoryException):
        repo.check_student_time_conflict(
            student_id=test_student.id,
            booking_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    with pytest.raises(RepositoryException):
        repo.get_bookings_by_student_and_instructor(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
    with pytest.raises(RepositoryException):
        repo.get_instructor_bookings_for_date(
            instructor_id=test_instructor_with_availability.id,
            target_date=date.today(),
            status_filter=None,
        )
    with pytest.raises(RepositoryException):
        repo.get_bookings_for_week(
            instructor_id=test_instructor_with_availability.id,
            week_dates=[date.today()],
        )
    with pytest.raises(RepositoryException):
        repo.count_instructor_completed_last_30d(test_instructor_with_availability.id)
    with pytest.raises(RepositoryException):
        repo.get_instructor_last_completed_at(test_instructor_with_availability.id)
    with pytest.raises(RepositoryException):
        repo.get_with_pricing_context("missing")
    with pytest.raises(RepositoryException):
        repo.get_instructor_bookings(
            test_instructor_with_availability.id,
            status=BookingStatus.CONFIRMED,
        )
    with pytest.raises(RepositoryException):
        repo.list_admin_bookings(
            search=None,
            statuses=None,
            payment_statuses=None,
            date_from=None,
            date_to=None,
            needs_action=None,
            now=None,
            page=1,
            per_page=5,
        )
    with pytest.raises(RepositoryException):
        repo.count_bookings_in_date_range(date.today(), date.today())
    with pytest.raises(RepositoryException):
        repo.sum_total_price_in_date_range(date.today(), date.today())
    with pytest.raises(RepositoryException):
        repo.get_bookings_for_date(date.today())
    with pytest.raises(RepositoryException):
        repo.count_pending_completion(datetime.now(timezone.utc))
    with pytest.raises(RepositoryException):
        repo.get_instructor_bookings_for_stats(test_instructor_with_availability.id)
    with pytest.raises(RepositoryException):
        repo.count_bookings_by_status(test_student.id, RoleName.STUDENT)
    with pytest.raises(RepositoryException):
        repo.complete_booking("missing")
    with pytest.raises(RepositoryException):
        repo.cancel_booking("missing", cancelled_by_id=test_student.id)
    with pytest.raises(RepositoryException):
        repo.mark_no_show("missing")
    with pytest.raises(RepositoryException):
        repo.get_no_show_reports_due_for_resolution(
            reported_before=datetime.now(timezone.utc)
        )
    with pytest.raises(RepositoryException):
        repo.get_instructor_future_bookings(test_instructor_with_availability.id)
    with pytest.raises(RepositoryException):
        repo.get_bookings_for_service_catalog("missing", from_date=date.today(), to_date=None)
    with pytest.raises(RepositoryException):
        repo.get_all_bookings_by_service_catalog(date.today(), date.today())
    with pytest.raises(RepositoryException):
        repo.get_booking_with_details("missing")
    with pytest.raises(RepositoryException):
        repo.get_by_id_for_update("missing")

    assert (
        repo.get_bookings_by_date_range_and_status(
            date.today(), date.today(), BookingStatus.CONFIRMED.value
        )
        == []
    )
