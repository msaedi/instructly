"""Additional branch coverage tests for BookingService helper paths."""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import BusinessRuleException
from app.models.booking import PaymentStatus
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

    locked = SimpleNamespace(payment_status=PaymentStatus.LOCKED.value, late_reschedule_used=False)
    with pytest.raises(BusinessRuleException):
        service.validate_reschedule_allowed(locked)

    normal = SimpleNamespace(payment_status="authorized", late_reschedule_used=False)
    service.get_hours_until_start = MagicMock(return_value=10)
    with pytest.raises(BusinessRuleException):
        service.validate_reschedule_allowed(normal)

    late_used = SimpleNamespace(payment_status="authorized", late_reschedule_used=True)
    service.get_hours_until_start = MagicMock(return_value=30)
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
