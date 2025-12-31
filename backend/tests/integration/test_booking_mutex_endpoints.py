"""
Integration tests for booking mutex on API endpoints.

These tests assert that protected endpoints return 429 and avoid downstream
side effects when the booking lock is unavailable.
"""

from contextlib import asynccontextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from fastapi import status
import pytest

from app.api.dependencies.services import get_booking_service
from app.main import fastapi_app as app
from app.services.booking_service import BookingService


@asynccontextmanager
async def _lock_unavailable(*_args, **_kwargs):
    yield False


@pytest.fixture
def mock_booking_service():
    service = MagicMock(spec=BookingService)
    service.db = MagicMock()
    service.cancel_booking = MagicMock()
    service.get_booking_for_user = MagicMock()
    service.validate_reschedule_allowed = MagicMock()
    service.check_availability = MagicMock()
    service.create_rescheduled_booking_with_existing_payment = MagicMock()
    service.report_no_show = MagicMock()
    service.instructor_dispute_completion = MagicMock()
    return service


@pytest.fixture
def client_with_mock_booking_service(client, mock_booking_service):
    app.dependency_overrides[get_booking_service] = lambda: mock_booking_service
    yield client
    app.dependency_overrides.clear()


def test_cancel_returns_429_when_locked(
    client_with_mock_booking_service, auth_headers_student, mock_booking_service, test_booking
):
    with patch("app.routes.v1.bookings.booking_lock", _lock_unavailable):
        response = client_with_mock_booking_service.post(
            f"/api/v1/bookings/{test_booking.id}/cancel",
            json={"reason": "Test cancellation"},
            headers=auth_headers_student,
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Operation in progress"
    mock_booking_service.cancel_booking.assert_not_called()


def test_reschedule_returns_429_when_locked(
    client_with_mock_booking_service, auth_headers_student, mock_booking_service, test_booking
):
    payload = {
        "booking_date": (date.today() + timedelta(days=2)).isoformat(),
        "start_time": "10:00",
        "selected_duration": 60,
    }
    with patch("app.routes.v1.bookings.booking_lock", _lock_unavailable):
        response = client_with_mock_booking_service.post(
            f"/api/v1/bookings/{test_booking.id}/reschedule",
            json=payload,
            headers=auth_headers_student,
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Operation in progress"
    mock_booking_service.get_booking_for_user.assert_not_called()


def test_no_show_returns_429_when_locked(
    client_with_mock_booking_service, auth_headers_student, mock_booking_service, test_booking
):
    with patch("app.routes.v1.bookings.booking_lock", _lock_unavailable):
        response = client_with_mock_booking_service.post(
            f"/api/v1/bookings/{test_booking.id}/no-show",
            json={"no_show_type": "instructor", "reason": "Did not show up"},
            headers=auth_headers_student,
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Operation in progress"
    mock_booking_service.report_no_show.assert_not_called()


def test_instructor_dispute_returns_429_when_locked(
    client_with_mock_booking_service, auth_headers_instructor, mock_booking_service, test_booking
):
    with patch("app.routes.v1.instructor_bookings.booking_lock", _lock_unavailable):
        response = client_with_mock_booking_service.post(
            f"/api/v1/instructor-bookings/{test_booking.id}/dispute",
            json={"reason": "Dispute reason"},
            headers=auth_headers_instructor,
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Operation in progress"
    mock_booking_service.instructor_dispute_completion.assert_not_called()


def test_admin_cancel_returns_429_when_locked(client, auth_headers_admin, test_booking):
    with patch("app.routes.v1.admin.bookings.booking_lock", _lock_unavailable), patch(
        "app.routes.v1.admin.bookings.AdminBookingService.cancel_booking"
    ) as mock_cancel:
        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/cancel",
            json={"reason": "Admin cancellation", "refund": False},
            headers=auth_headers_admin,
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Operation in progress"
    mock_cancel.assert_not_called()


def test_admin_refund_returns_429_when_locked(client, auth_headers_admin, test_booking):
    with patch("app.routes.v1.admin.refunds.booking_lock", _lock_unavailable), patch(
        "app.routes.v1.admin.refunds.AdminRefundService.get_booking"
    ) as mock_get_booking:
        response = client.post(
            f"/api/v1/admin/bookings/{test_booking.id}/refund",
            json={"reason": "platform_error"},
            headers=auth_headers_admin,
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Operation in progress"
    mock_get_booking.assert_not_called()
