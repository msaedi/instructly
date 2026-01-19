from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import RepositoryException
from app.models.payment import PlatformCredit
from app.repositories.credit_repository import CreditRepository

try:
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ImportError:  # pragma: no cover - alternate import path in some envs
    from tests.factories.booking_builders import create_booking_pg_safe

def _add_credit(
    db,
    *,
    user_id,
    amount_cents,
    status="available",
    expires_at=None,
    reserved_amount_cents=0,
    reserved_for_booking_id=None,
    reserved_at=None,
    source_booking_id=None,
):
    credit = PlatformCredit(
        user_id=user_id,
        amount_cents=amount_cents,
        reason="test",
        status=status,
        expires_at=expires_at,
        reserved_amount_cents=reserved_amount_cents,
        reserved_for_booking_id=reserved_for_booking_id,
        reserved_at=reserved_at,
        source_booking_id=source_booking_id,
    )
    db.add(credit)
    return credit


def test_credit_repository_available_and_totals(db, test_student, test_booking):
    repo = CreditRepository(db)
    now = datetime.now(timezone.utc)

    _add_credit(db, user_id=test_student.id, amount_cents=1000, expires_at=now + timedelta(days=1))
    _add_credit(db, user_id=test_student.id, amount_cents=500, expires_at=None)
    _add_credit(db, user_id=test_student.id, amount_cents=250, status="reserved", reserved_amount_cents=250)
    _add_credit(db, user_id=test_student.id, amount_cents=100, status="available", expires_at=now - timedelta(days=1))
    db.commit()

    available = repo.get_available_credits(user_id=test_student.id, for_update=True)
    assert all(c.status in (None, "available") for c in available)
    assert all(c.expires_at is None or c.expires_at > now for c in available)

    total_available = repo.get_total_available_credits(user_id=test_student.id)
    assert total_available >= 1500

    total_reserved = repo.get_total_reserved_credits(user_id=test_student.id)
    assert total_reserved == 250


def test_credit_repository_reserved_and_for_booking(db, test_student, test_booking):
    repo = CreditRepository(db)
    now = datetime.now(timezone.utc)

    other_booking = create_booking_pg_safe(
        db,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=test_booking.booking_date + timedelta(days=1),
        start_time=test_booking.start_time,
        end_time=test_booking.end_time,
        service_name=test_booking.service_name,
        hourly_rate=test_booking.hourly_rate,
        total_price=test_booking.total_price,
        duration_minutes=test_booking.duration_minutes,
        service_area=test_booking.service_area,
        location_type=test_booking.location_type,
        meeting_location=test_booking.meeting_location,
    )

    _add_credit(
        db,
        user_id=test_student.id,
        amount_cents=300,
        status="reserved",
        reserved_amount_cents=300,
        reserved_for_booking_id=test_booking.id,
        reserved_at=now,
    )
    _add_credit(
        db,
        user_id=test_student.id,
        amount_cents=200,
        status="reserved",
        reserved_amount_cents=200,
        reserved_for_booking_id=other_booking.id,
        reserved_at=now,
    )
    db.commit()

    reserved = repo.get_reserved_credits(user_id=test_student.id)
    assert reserved

    reserved_for_booking = repo.get_reserved_credits_for_booking(booking_id=test_booking.id)
    assert len(reserved_for_booking) == 1
    assert reserved_for_booking[0].reserved_for_booking_id == test_booking.id


def test_credit_repository_source_and_expired(db, test_student, test_booking):
    repo = CreditRepository(db)
    now = datetime.now(timezone.utc)

    _add_credit(
        db,
        user_id=test_student.id,
        amount_cents=100,
        status="available",
        expires_at=now - timedelta(days=2),
    )
    source_credit = _add_credit(
        db,
        user_id=test_student.id,
        amount_cents=400,
        status="available",
        source_booking_id=test_booking.id,
    )
    db.commit()

    expired = repo.get_expired_available_credits(as_of=now)
    assert any(c.id == source_credit.id for c in repo.get_credits_for_source_booking(booking_id=test_booking.id))
    assert expired


def test_credit_repository_ordering_and_status_filter(db, test_student, test_booking):
    repo = CreditRepository(db)
    now = datetime.now(timezone.utc)

    _add_credit(
        db,
        user_id=test_student.id,
        amount_cents=200,
        status="available",
        expires_at=now + timedelta(days=5),
        source_booking_id=test_booking.id,
    )
    _add_credit(
        db,
        user_id=test_student.id,
        amount_cents=150,
        status="reserved",
        reserved_amount_cents=150,
        source_booking_id=test_booking.id,
    )
    db.commit()

    ordered = repo.get_available_credits(user_id=test_student.id, order_by="created_at")
    assert ordered

    filtered = repo.get_credits_for_source_booking(
        booking_id=test_booking.id, statuses=["available"]
    )
    assert all(c.status == "available" for c in filtered)


def test_credit_repository_error_paths(db, monkeypatch):
    repo = CreditRepository(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db failure")

    monkeypatch.setattr(repo.db, "query", _boom)

    with pytest.raises(RepositoryException):
        repo.get_available_credits(user_id="user")
    with pytest.raises(RepositoryException):
        repo.get_reserved_credits(user_id="user")
    with pytest.raises(RepositoryException):
        repo.get_reserved_credits_for_booking(booking_id="booking")
    with pytest.raises(RepositoryException):
        repo.get_credits_for_source_booking(booking_id="booking")
    with pytest.raises(RepositoryException):
        repo.get_total_available_credits(user_id="user")
    with pytest.raises(RepositoryException):
        repo.get_total_reserved_credits(user_id="user")
    with pytest.raises(RepositoryException):
        repo.get_expired_available_credits()
