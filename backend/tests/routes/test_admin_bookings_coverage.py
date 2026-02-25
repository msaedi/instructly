"""Coverage tests for admin bookings routes — error paths and branch coverage."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.core.exceptions import ServiceException
from app.routes.v1.admin import bookings as routes


class _FakeAdminBookingService:
    """Stub for AdminBookingService."""

    def __init__(
        self,
        *,
        cancel_result=None,
        cancel_error=None,
        update_result=None,
        update_error=None,
    ):
        self._cancel_result = cancel_result
        self._cancel_error = cancel_error
        self._update_result = update_result
        self._update_error = update_error

    def cancel_booking(self, **_kwargs):
        if self._cancel_error:
            raise self._cancel_error
        return self._cancel_result

    def update_booking_status(self, **_kwargs):
        if self._update_error:
            raise self._update_error
        return self._update_result


class _FakeBookingService:
    """Stub for BookingService."""

    def __init__(self, *, resolve_result=None, resolve_error=None):
        self._resolve_result = resolve_result
        self._resolve_error = resolve_error

    def resolve_no_show(self, **_kwargs):
        if self._resolve_error:
            raise self._resolve_error
        return self._resolve_result


def _admin_user():
    return SimpleNamespace(id="admin-1", email="admin@example.com")


def _cancel_request(refund: bool = True):
    return SimpleNamespace(reason="test", note="note", refund=refund)


def _status_request(status_val: str = "completed"):
    return SimpleNamespace(
        status=SimpleNamespace(value=status_val),
        note="test note",
    )


def _no_show_request():
    return SimpleNamespace(
        resolution=SimpleNamespace(value="student_no_show"),
        admin_notes="test admin notes",
    )


def _make_lock(acquired: bool = True):
    """Create a mock async context manager for booking_lock."""

    @asynccontextmanager
    async def _lock(booking_id, ttl_s=90):
        yield acquired

    return _lock


# ---- L167: ServiceException with code=stripe_error maps to 502 ----
@pytest.mark.asyncio
async def test_cancel_booking_stripe_error_returns_502(monkeypatch):
    service = _FakeAdminBookingService(
        cancel_error=ServiceException("Stripe API error", code="stripe_error"),
    )
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)
    monkeypatch.setattr(routes, "booking_lock", _make_lock(True))

    with pytest.raises(HTTPException) as exc:
        await routes.admin_cancel_booking(
            booking_id="01BOOKINGID00000000000000",
            request=_cancel_request(),
            db=None,
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 502


# ---- L171-174: ServiceException with non-stripe code maps to 400 ----
@pytest.mark.asyncio
async def test_cancel_booking_service_exception_returns_400(monkeypatch):
    service = _FakeAdminBookingService(
        cancel_error=ServiceException("Booking invalid", code="invalid_state"),
    )
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)
    monkeypatch.setattr(routes, "booking_lock", _make_lock(True))

    with pytest.raises(HTTPException) as exc:
        await routes.admin_cancel_booking(
            booking_id="01BOOKINGID00000000000000",
            request=_cancel_request(),
            db=None,
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 400


# ---- L177: booking is None after cancel -> 404 ----
@pytest.mark.asyncio
async def test_cancel_booking_returns_none_404(monkeypatch):
    service = _FakeAdminBookingService(cancel_result=(None, None))
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)
    monkeypatch.setattr(routes, "booking_lock", _make_lock(True))

    with pytest.raises(HTTPException) as exc:
        await routes.admin_cancel_booking(
            booking_id="01BOOKINGID00000000000000",
            request=_cancel_request(),
            db=None,
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 404


# ---- Cancel booking lock not acquired -> 429 ----
@pytest.mark.asyncio
async def test_cancel_booking_lock_not_acquired_429(monkeypatch):
    service = _FakeAdminBookingService(cancel_result=(None, None))
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)
    monkeypatch.setattr(routes, "booking_lock", _make_lock(False))

    with pytest.raises(HTTPException) as exc:
        await routes.admin_cancel_booking(
            booking_id="01BOOKINGID00000000000000",
            request=_cancel_request(),
            db=None,
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 429


# ---- L213-214: ServiceException in update_booking_status -> 400 ----
@pytest.mark.asyncio
async def test_update_booking_status_service_exception_400(monkeypatch):
    service = _FakeAdminBookingService(
        update_error=ServiceException("invalid transition"),
    )
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)

    with pytest.raises(HTTPException) as exc:
        await routes.admin_update_booking_status(
            booking_id="01BOOKINGID00000000000000",
            request=_status_request(),
            db=None,
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 400


# ---- L220: booking None after update -> 404 ----
@pytest.mark.asyncio
async def test_update_booking_status_returns_none_404(monkeypatch):
    service = _FakeAdminBookingService(update_result=None)
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)

    with pytest.raises(HTTPException) as exc:
        await routes.admin_update_booking_status(
            booking_id="01BOOKINGID00000000000000",
            request=_status_request(),
            db=None,
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 404


# ---- Successful update with status as enum (hasattr value) ----
@pytest.mark.asyncio
async def test_update_booking_status_success(monkeypatch):
    from app.models.booking import BookingStatus

    booking = SimpleNamespace(id="01BOOKINGID00000000000000", status=BookingStatus.COMPLETED)
    service = _FakeAdminBookingService(update_result=booking)
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)

    result = await routes.admin_update_booking_status(
        booking_id="01BOOKINGID00000000000000",
        request=_status_request(),
        db=None,
        current_user=_admin_user(),
    )
    assert result.success is True
    assert result.booking_id == "01BOOKINGID00000000000000"


# ---- L249: booking_lock not acquired in resolve_no_show -> 429 ----
@pytest.mark.asyncio
async def test_resolve_no_show_lock_not_acquired_429(monkeypatch):
    monkeypatch.setattr(routes, "booking_lock", _make_lock(False))

    with pytest.raises(HTTPException) as exc:
        await routes.resolve_no_show(
            booking_id="01BOOKINGID00000000000000",
            request=_no_show_request(),
            booking_service=_FakeBookingService(),
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 429


# ---- L260-261: ServiceException in resolve_no_show -> 400 ----
@pytest.mark.asyncio
async def test_resolve_no_show_service_exception_400(monkeypatch):
    monkeypatch.setattr(routes, "booking_lock", _make_lock(True))

    service = _FakeBookingService(
        resolve_error=ServiceException("no show resolution failed"),
    )

    with pytest.raises(HTTPException) as exc:
        await routes.resolve_no_show(
            booking_id="01BOOKINGID00000000000000",
            request=_no_show_request(),
            booking_service=service,
            current_user=_admin_user(),
        )
    assert exc.value.status_code == 400


# ---- Successful resolve_no_show ----
@pytest.mark.asyncio
async def test_resolve_no_show_success(monkeypatch):
    monkeypatch.setattr(routes, "booking_lock", _make_lock(True))

    service = _FakeBookingService(
        resolve_result={
            "success": True,
            "booking_id": "01BOOKINGID00000000000000",
            "resolution": "student_no_show",
            "settlement_outcome": "refund_denied",
        }
    )

    result = await routes.resolve_no_show(
        booking_id="01BOOKINGID00000000000000",
        request=_no_show_request(),
        booking_service=service,
        current_user=_admin_user(),
    )
    assert result.success is True
    assert result.resolution == "student_no_show"
    assert result.settlement_outcome == "refund_denied"


# ---- Successful cancel booking ----
@pytest.mark.asyncio
async def test_cancel_booking_success(monkeypatch):
    booking = SimpleNamespace(id="01BOOKINGID00000000000000", status="cancelled")
    service = _FakeAdminBookingService(cancel_result=(booking, "re_123"))
    monkeypatch.setattr(routes, "AdminBookingService", lambda _db: service)
    monkeypatch.setattr(routes, "booking_lock", _make_lock(True))

    result = await routes.admin_cancel_booking(
        booking_id="01BOOKINGID00000000000000",
        request=_cancel_request(refund=True),
        db=None,
        current_user=_admin_user(),
    )
    assert result.success is True
    assert result.refund_id == "re_123"
    assert result.refund_issued is True
