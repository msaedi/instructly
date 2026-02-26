from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
import pytest

from app.core.enums import PermissionName
from app.models.booking import Booking, BookingStatus
from app.routes.v1 import instructor_bookings as routes


def _booking_stub(**kwargs):
    booking = Booking(**kwargs)
    return booking


def test_check_permission_denied(monkeypatch, test_student, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(HTTPException) as exc:
        routes.check_permission(test_student, PermissionName.VIEW_INCOMING_BOOKINGS, db)
    assert exc.value.status_code == 403


def test_get_booking_end_utc_returns_existing():
    now = datetime.now(timezone.utc)
    booking = _booking_stub(
        booking_date=now.date(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        booking_end_utc=now,
    )
    assert routes._get_booking_end_utc(booking) == now


def test_paginate_bookings(test_booking):
    bookings = [test_booking, test_booking, test_booking]
    page = routes._paginate_bookings(bookings, page=2, per_page=2)
    assert page.has_prev is True
    assert page.has_next is False


@pytest.mark.asyncio
async def test_get_pending_completion_bookings(monkeypatch, test_instructor, test_booking, db):
    test_booking.booking_end_utc = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    class _Repo:
        def get_instructor_bookings(self, *args, **kwargs):
            return [test_booking]

    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.RepositoryFactory.create_booking_repository",
        lambda _db: _Repo(),
    )
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )

    result = await routes.get_pending_completion_bookings(
        db=db, current_user=test_instructor, page=1, per_page=10
    )
    assert result.total == 1


@pytest.mark.asyncio
async def test_get_upcoming_and_list_bookings(monkeypatch, test_instructor, test_booking, db):
    class _Repo:
        def get_instructor_bookings(self, *args, **kwargs):
            return [test_booking]

    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.RepositoryFactory.create_booking_repository",
        lambda _db: _Repo(),
    )
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )

    upcoming = await routes.get_upcoming_bookings(
        db=db, current_user=test_instructor, page=1, per_page=10
    )
    assert upcoming.total == 1

    listed = await routes.list_instructor_bookings(
        db=db,
        current_user=test_instructor,
        status=BookingStatus.CONFIRMED,
        upcoming=True,
        exclude_future_confirmed=False,
        include_past_confirmed=False,
        page=1,
        per_page=10,
    )
    assert listed.total == 1


@pytest.mark.asyncio
async def test_get_completed_bookings(monkeypatch, test_instructor, test_booking, db):
    class _Repo:
        def get_instructor_bookings(self, *args, **kwargs):
            return [test_booking]

    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.RepositoryFactory.create_booking_repository",
        lambda _db: _Repo(),
    )
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )

    completed = await routes.get_completed_bookings(
        db=db, current_user=test_instructor, page=1, per_page=10
    )
    assert completed.total == 1


@pytest.mark.asyncio
async def test_mark_lesson_complete_not_found(monkeypatch, test_instructor, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )

    class _Service:
        def instructor_mark_complete(self, *args, **kwargs):
            from app.core.exceptions import NotFoundException

            raise NotFoundException("missing")

    with pytest.raises(HTTPException) as exc:
        await routes.mark_lesson_complete(
            booking_id="01HF4G12ABCDEF3456789XYZAB",
            notes=None,
            db=db,
            current_user=test_instructor,
            booking_service=_Service(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_lesson_complete_business_rule(monkeypatch, test_instructor, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )

    class _Service:
        def instructor_mark_complete(self, *args, **kwargs):
            from app.core.exceptions import BusinessRuleException

            raise BusinessRuleException("rule")

    with pytest.raises(HTTPException) as exc:
        await routes.mark_lesson_complete(
            booking_id="01HF4G12ABCDEF3456789XYZAB",
            notes=None,
            db=db,
            current_user=test_instructor,
            booking_service=_Service(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_mark_lesson_complete_success(monkeypatch, test_instructor, test_booking, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )

    class _Service:
        def instructor_mark_complete(self, *args, **kwargs):
            return test_booking

    result = await routes.mark_lesson_complete(
        booking_id="01HF4G12ABCDEF3456789XYZAB",
        notes="done",
        db=db,
        current_user=test_instructor,
        booking_service=_Service(),
    )
    assert result.id == test_booking.id


@pytest.mark.asyncio
async def test_mark_lesson_complete_validation(monkeypatch, test_instructor, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )

    class _Service:
        def instructor_mark_complete(self, *args, **kwargs):
            from app.core.exceptions import ValidationException

            raise ValidationException("bad")

    with pytest.raises(HTTPException) as exc:
        await routes.mark_lesson_complete(
            booking_id="01HF4G12ABCDEF3456789XYZAB",
            notes=None,
            db=db,
            current_user=test_instructor,
            booking_service=_Service(),
        )
    assert exc.value.status_code == 422


@asynccontextmanager
async def _lock_acquired(value: bool):
    yield value


@pytest.mark.asyncio
async def test_dispute_completion_lock_unavailable(monkeypatch, test_instructor, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(routes, "booking_lock", lambda _booking_id: _lock_acquired(False))

    class _Service:
        def instructor_dispute_completion(self, *args, **kwargs):
            return None

    with pytest.raises(HTTPException) as exc:
        await routes.dispute_completion(
            booking_id="01HF4G12ABCDEF3456789XYZAB",
            reason="reason",
            db=db,
            current_user=test_instructor,
            booking_service=_Service(),
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_dispute_completion_validation(monkeypatch, test_instructor, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(routes, "booking_lock", lambda _booking_id: _lock_acquired(True))

    class _Service:
        def instructor_dispute_completion(self, *args, **kwargs):
            from app.core.exceptions import ValidationException

            raise ValidationException("bad")

    with pytest.raises(HTTPException) as exc:
        await routes.dispute_completion(
            booking_id="01HF4G12ABCDEF3456789XYZAB",
            reason="reason",
            db=db,
            current_user=test_instructor,
            booking_service=_Service(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_dispute_completion_not_found(monkeypatch, test_instructor, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(routes, "booking_lock", lambda _booking_id: _lock_acquired(True))

    class _Service:
        def instructor_dispute_completion(self, *args, **kwargs):
            from app.core.exceptions import NotFoundException

            raise NotFoundException("missing")

    with pytest.raises(HTTPException) as exc:
        await routes.dispute_completion(
            booking_id="01HF4G12ABCDEF3456789XYZAB",
            reason="reason",
            db=db,
            current_user=test_instructor,
            booking_service=_Service(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_dispute_completion_success(monkeypatch, test_instructor, test_booking, db):
    monkeypatch.setattr(
        "app.routes.v1.instructor_bookings.PermissionService.user_has_permission",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(routes, "booking_lock", lambda _booking_id: _lock_acquired(True))

    class _Service:
        def instructor_dispute_completion(self, *args, **kwargs):
            return test_booking

    result = await routes.dispute_completion(
        booking_id="01HF4G12ABCDEF3456789XYZAB",
        reason="reason",
        db=db,
        current_user=test_instructor,
        booking_service=_Service(),
    )
    assert result.id == test_booking.id
