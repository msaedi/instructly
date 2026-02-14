from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.booking_payment import BookingPayment
from app.models.payment import PaymentEvent
from app.models.user import User
from app.services.admin_ops_service import AdminOpsService

try:  # pragma: no cover - support running from repo root or backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _ensure_payment(db, booking, **fields):
    """Create or update BookingPayment satellite for a booking."""
    bp = db.query(BookingPayment).filter(BookingPayment.booking_id == booking.id).first()
    if bp:
        for key, value in fields.items():
            setattr(bp, key, value)
    else:
        bp = BookingPayment(booking_id=booking.id, **fields)
        db.add(bp)
    db.flush()
    booking.payment_detail = bp
    return bp


@pytest.mark.asyncio
async def test_payment_timeline_redacts_and_categorizes(db, test_booking):
    now = datetime.now(timezone.utc)
    event = PaymentEvent(
        booking_id=test_booking.id,
        event_type="auth_failed",
        event_data={
            "payment_intent_id": "pi_1234567890",
            "refund_id": "re_abcdef1234",
            "error": "Card was declined",
            "error_type": "card_declined",
            "card_last4": "4242",
        },
        created_at=now - timedelta(minutes=5),
    )
    db.add(event)
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=test_booking.id,
        user_id=None,
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
    )

    assert result["payments"]
    entry = result["payments"][0]

    refs = entry["provider_refs"]
    assert refs["payment_intent"].endswith("7890")
    assert refs["refund"].endswith("1234")
    assert entry["failure"]["category"] == "card_declined"
    assert result["flags"]["has_failed_payment"] is True
    assert result["flags"]["has_pending_refund"] is False
    assert result["summary"]["by_status"]["failed"] == 1

    payload = str(entry)
    assert "pi_1234567890" not in payload
    assert "re_abcdef1234" not in payload


@pytest.mark.asyncio
async def test_payment_timeline_double_charge_flag(db, test_booking):
    now = datetime.now(timezone.utc)
    event_one = PaymentEvent(
        booking_id=test_booking.id,
        event_type="payment_captured",
        event_data={"amount_captured_cents": 5000},
        created_at=now,
    )
    event_two = PaymentEvent(
        booking_id=test_booking.id,
        event_type="payment_captured",
        event_data={"amount_captured_cents": 5000},
        created_at=now + timedelta(minutes=4),
    )
    event_three = PaymentEvent(
        booking_id=test_booking.id,
        event_type="payment_captured",
        event_data={"amount_captured_cents": 5000},
        created_at=now + timedelta(minutes=9),
    )
    db.add_all([event_one, event_two, event_three])
    db.flush()
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=test_booking.id,
        user_id=None,
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
    )

    assert result["flags"]["possible_double_charge"] is True


@pytest.mark.asyncio
async def test_payment_timeline_pending_refund_flag(db, test_booking):
    now = datetime.now(timezone.utc)
    event = PaymentEvent(
        booking_id=test_booking.id,
        event_type="refund_requested",
        event_data={"refund_id": "re_pending1234", "amount_refunded": 1500},
        created_at=now - timedelta(minutes=1),
    )
    db.add(event)
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=test_booking.id,
        user_id=None,
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
    )

    assert result["flags"]["has_pending_refund"] is True


@pytest.mark.asyncio
async def test_payment_timeline_includes_scheduled_payments(db, test_booking):
    _ensure_payment(db, test_booking, payment_status="scheduled")
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=test_booking.id,
        user_id=None,
        start_time=datetime.now(timezone.utc) - timedelta(hours=1),
        end_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    assert result["payments"]
    assert result["payments"][0]["status"] == "scheduled"


@pytest.mark.asyncio
async def test_payment_timeline_includes_authorized_payments(db, test_booking):
    now = datetime.now(timezone.utc)
    _ensure_payment(
        db, test_booking,
        payment_status="authorized",
        auth_scheduled_for=now - timedelta(hours=2),
        auth_attempted_at=now - timedelta(hours=1),
    )
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=test_booking.id,
        user_id=None,
        start_time=now - timedelta(hours=4),
        end_time=now + timedelta(hours=1),
    )

    entry = result["payments"][0]
    assert entry["status"] == "authorized"
    assert entry["scheduled_capture_at"] is not None
    states = {state["state"] for state in entry["status_timeline"]}
    assert "scheduled" in states
    assert "authorized" in states


@pytest.mark.asyncio
async def test_payment_timeline_summary_by_status(db, test_booking):
    _ensure_payment(db, test_booking, payment_status="scheduled")

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
        total_price=float(test_booking.total_price),
        duration_minutes=test_booking.duration_minutes,
        payment_status="locked",
    )
    db.add_all([test_booking, other_booking])
    db.commit()

    service = AdminOpsService(db)
    start_time = test_booking.booking_start_utc - timedelta(hours=1)
    end_time = other_booking.booking_start_utc + timedelta(hours=1)
    result = await service.get_payment_timeline(
        booking_id=None,
        user_id=test_booking.student_id,
        start_time=start_time,
        end_time=end_time,
    )

    summary = result["summary"]["by_status"]
    assert summary["scheduled"] == 1
    assert summary["locked"] == 1


@pytest.mark.asyncio
async def test_payment_timeline_includes_scheduling_fields(db, test_booking):
    scheduled_start = datetime(2026, 2, 20, 14, 0, tzinfo=timezone.utc)
    _ensure_payment(db, test_booking, payment_status="scheduled")
    test_booking.booking_start_utc = scheduled_start
    test_booking.booking_end_utc = scheduled_start + timedelta(minutes=30)
    test_booking.duration_minutes = 30
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=test_booking.id,
        user_id=None,
        start_time=scheduled_start - timedelta(days=2),
        end_time=scheduled_start + timedelta(days=2),
    )

    entry = result["payments"][0]
    assert entry["scheduled_authorize_at"] == scheduled_start - timedelta(hours=24)
    assert entry["scheduled_capture_at"] == scheduled_start + timedelta(minutes=30, hours=24)


@pytest.mark.asyncio
async def test_payment_timeline_scheduling_fields_only_for_pending_states(db, test_booking):
    scheduled_start = datetime(2026, 2, 20, 14, 0, tzinfo=timezone.utc)
    _ensure_payment(db, test_booking, payment_status="settled")
    test_booking.booking_start_utc = scheduled_start
    test_booking.booking_end_utc = scheduled_start + timedelta(minutes=30)
    test_booking.duration_minutes = 30
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=test_booking.id,
        user_id=None,
        start_time=scheduled_start - timedelta(days=2),
        end_time=scheduled_start + timedelta(days=2),
    )

    entry = result["payments"][0]
    assert entry["scheduled_authorize_at"] is None
    assert entry["scheduled_capture_at"] is None


@pytest.mark.asyncio
async def test_payment_timeline_time_window_filters_events(db, test_booking):
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
        total_price=float(test_booking.total_price),
        duration_minutes=test_booking.duration_minutes,
    )
    old_event = PaymentEvent(
        booking_id=other_booking.id,
        event_type="auth_succeeded",
        event_data={"amount_cents": 2500},
        created_at=now - timedelta(days=2),
    )
    recent_event = PaymentEvent(
        booking_id=test_booking.id,
        event_type="auth_succeeded",
        event_data={"amount_cents": 2500},
        created_at=now - timedelta(hours=2),
    )
    db.add_all([old_event, recent_event])
    db.flush()
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=None,
        user_id=test_booking.student_id,
        start_time=now - timedelta(hours=6),
        end_time=now,
    )

    booking_ids = {item["booking_id"] for item in result["payments"]}
    assert test_booking.id in booking_ids
    assert other_booking.id not in booking_ids


@pytest.mark.asyncio
async def test_payment_timeline_filters_by_user(db, test_booking):
    now = datetime.now(timezone.utc)
    other_user = User(
        email="other_student@example.com",
        hashed_password="hashed",
        first_name="Other",
        last_name="Student",
        zip_code="10001",
    )
    db.add(other_user)
    db.flush()

    other_booking = create_booking_pg_safe(
        db,
        student_id=other_user.id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=test_booking.booking_date + timedelta(days=1),
        start_time=test_booking.start_time,
        end_time=test_booking.end_time,
        service_name=test_booking.service_name,
        hourly_rate=test_booking.hourly_rate,
        total_price=float(test_booking.total_price),
        duration_minutes=test_booking.duration_minutes,
    )

    db.add_all(
        [
            PaymentEvent(
                booking_id=test_booking.id,
                event_type="auth_succeeded",
                event_data={"amount_cents": 5000},
                created_at=now - timedelta(minutes=10),
            ),
            PaymentEvent(
                booking_id=other_booking.id,
                event_type="auth_succeeded",
                event_data={"amount_cents": 5000},
                created_at=now - timedelta(minutes=10),
            ),
        ]
    )
    db.commit()

    service = AdminOpsService(db)
    result = await service.get_payment_timeline(
        booking_id=None,
        user_id=test_booking.student_id,
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
    )

    booking_ids = {entry["booking_id"] for entry in result["payments"]}
    assert test_booking.id in booking_ids
    assert other_booking.id not in booking_ids
