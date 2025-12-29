"""
Integration test for booking mutex on /complete endpoint.
"""

from contextlib import asynccontextmanager
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
    service.complete_booking = MagicMock()
    return service


@pytest.fixture
def client_with_mock_booking_service(client, mock_booking_service):
    app.dependency_overrides[get_booking_service] = lambda: mock_booking_service
    yield client
    app.dependency_overrides.clear()


def test_complete_returns_429_when_locked(
    client_with_mock_booking_service, auth_headers_instructor, mock_booking_service, test_booking
):
    with patch("app.routes.v1.bookings.booking_lock", _lock_unavailable):
        response = client_with_mock_booking_service.post(
            f"/api/v1/bookings/{test_booking.id}/complete",
            headers=auth_headers_instructor,
        )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Operation in progress"
    mock_booking_service.complete_booking.assert_not_called()
