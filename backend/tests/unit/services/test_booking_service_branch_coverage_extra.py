"""Additional branch coverage tests for BookingService helper paths."""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import BusinessRuleException
from app.models.booking import BookingStatus, PaymentStatus
from app.services.booking_service import BookingService


def _service() -> BookingService:
    service = BookingService.__new__(BookingService)
    service.repository = MagicMock()
    service.db = MagicMock()
    return service


def test_check_student_time_conflict_returns_bool_and_handles_exceptions():
    service = _service()

    service.repository.check_student_time_conflict.return_value = ["conflict"]
    assert (
        service.check_student_time_conflict(
            student_id="student-1",
            booking_date=date(2030, 1, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        is True
    )

    service.repository.check_student_time_conflict.side_effect = RuntimeError("boom")
    assert (
        service.check_student_time_conflict(
            student_id="student-1",
            booking_date=date(2030, 1, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        is False
    )


def test_validate_reschedule_allowed_branches():
    service = _service()
    service.repository.get_reschedule_by_booking_id.return_value = None

    locked = SimpleNamespace(
        id="booking-locked", payment_status=PaymentStatus.LOCKED.value, late_reschedule_used=False
    )
    with pytest.raises(BusinessRuleException):
        service.validate_reschedule_allowed(locked)

    normal = SimpleNamespace(id="booking-normal", payment_status="authorized", late_reschedule_used=False)
    service.get_hours_until_start = MagicMock(return_value=10)
    with pytest.raises(BusinessRuleException):
        service.validate_reschedule_allowed(normal)

    late_used = SimpleNamespace(
        id="booking-late", payment_status="authorized", late_reschedule_used=False
    )
    service.get_hours_until_start = MagicMock(return_value=30)
    service.repository.get_reschedule_by_booking_id.return_value = SimpleNamespace(
        late_reschedule_used=True
    )
    with pytest.raises(BusinessRuleException):
        service.validate_reschedule_allowed(late_used)


def test_get_booking_with_payment_summary_only_for_student():
    service = _service()
    booking = SimpleNamespace(id="booking-1", student_id="student-1")
    user = SimpleNamespace(id="student-1")

    service.get_booking_for_user = MagicMock(return_value=booking)

    with patch("app.services.config_service.ConfigService") as config_cls, patch(
        "app.repositories.factory.RepositoryFactory"
    ) as factory, patch(
        "app.repositories.review_repository.ReviewTipRepository"
    ) as tip_repo_cls, patch(
        "app.services.payment_summary_service.build_student_payment_summary",
        return_value=SimpleNamespace(total=123),
    ) as build_summary:
        config_cls.return_value.get_pricing_config.return_value = ({}, None)
        factory.create_payment_repository.return_value = MagicMock()
        tip_repo_cls.return_value = MagicMock()

        booking_out, summary = service.get_booking_with_payment_summary("booking-1", user)

    assert booking_out is booking
    assert summary is not None
    build_summary.assert_called_once()

    # Non-student accessor should not receive summary.
    service.get_booking_for_user = MagicMock(return_value=SimpleNamespace(id="booking-2", student_id="other"))
    other_booking, other_summary = service.get_booking_with_payment_summary(
        "booking-2", user
    )
    assert other_booking is not None
    assert other_summary is None


def test_determine_service_area_summary_prefers_metadata_and_compacts():
    service = _service()
    service.service_area_repository = MagicMock()

    areas = [
        SimpleNamespace(
            neighborhood=SimpleNamespace(parent_region="Queens", region_metadata={"borough": "Bronx"})
        ),
        SimpleNamespace(neighborhood=SimpleNamespace(parent_region="Manhattan", region_metadata={})),
        SimpleNamespace(neighborhood=SimpleNamespace(parent_region="Brooklyn", region_metadata={})),
    ]
    service.service_area_repository.list_for_instructor.return_value = areas

    summary = service._determine_service_area_summary("instructor-1")

    # Sorted set should compact to "<first> + N more" for 3+ boroughs.
    assert summary == "Bronx + 2 more"


def test_format_booking_time_and_service_name_fallbacks():
    assert BookingService._format_booking_time(SimpleNamespace(start_time=None)) == ""
    assert BookingService._format_booking_time(SimpleNamespace(start_time="9am")) == "9am"

    assert (
        BookingService._resolve_service_name(
            SimpleNamespace(service_name="   ", instructor_service=SimpleNamespace(name="Guitar"))
        )
        == "Guitar"
    )
    assert (
        BookingService._resolve_service_name(
            SimpleNamespace(service_name=None, instructor_service=SimpleNamespace(name="   "))
        )
        == "Lesson"
    )


def test_send_cancellation_notifications_uses_detailed_booking_for_instructor_role():
    service = _service()
    service.notification_service = MagicMock()
    service.repository = MagicMock()

    booking = SimpleNamespace(
        id="booking-1",
        student=None,
        instructor=None,
        student_id="student-1",
        instructor_id="instructor-1",
    )
    detailed = SimpleNamespace(
        id="booking-1",
        student_id="student-1",
        instructor_id="instructor-1",
        booking_date=None,
        service_name="Piano",
        instructor=SimpleNamespace(first_name="Alex", last_name="Stone"),
        student=SimpleNamespace(first_name="Sam", last_name="Learner"),
    )
    service.repository.get_booking_with_details.return_value = detailed

    service._send_cancellation_notifications(booking, "instructor")

    service.repository.get_booking_with_details.assert_called_once_with("booking-1")
    service.notification_service.notify_user_best_effort.assert_called_once()
    kwargs = service.notification_service.notify_user_best_effort.call_args.kwargs
    assert kwargs["user_id"] == "student-1"
    assert kwargs["template"]


def test_send_cancellation_notifications_noop_without_notification_service():
    service = _service()
    service.notification_service = None
    service._send_cancellation_notifications(SimpleNamespace(id="booking-1"), "student")


def test_handle_post_booking_tasks_event_publish_paths():
    service = _service()
    service.event_publisher = MagicMock()
    service.system_message_service = MagicMock()
    service._send_booking_notifications = MagicMock()
    service._invalidate_booking_caches = MagicMock()

    confirmed_booking = SimpleNamespace(
        id="booking-1",
        status=BookingStatus.CONFIRMED,
        student_id="student-1",
        instructor_id="instructor-1",
        booking_date=None,
        start_time=None,
        created_at=None,
        instructor_service=None,
    )

    service._handle_post_booking_tasks(confirmed_booking, is_reschedule=False)
    service.event_publisher.publish.assert_called_once()
    service.system_message_service.create_booking_created_message.assert_called_once()
    service._send_booking_notifications.assert_called_once_with(confirmed_booking, False)
    service._invalidate_booking_caches.assert_called_once_with(confirmed_booking)

    service.event_publisher.publish.reset_mock()
    cancelled_booking = SimpleNamespace(
        id="booking-2",
        status=BookingStatus.CANCELLED,
        student_id="student-1",
        instructor_id="instructor-1",
        booking_date=None,
        start_time=None,
        created_at=None,
        instructor_service=None,
    )
    service._handle_post_booking_tasks(cancelled_booking, is_reschedule=False)
    service.event_publisher.publish.assert_not_called()
