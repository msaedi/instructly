"""Additional branch coverage tests for BookingDetailService internals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.booking import BookingStatus
from app.models.payment import PaymentEvent
from app.services.booking_detail_service import BookingDetailService


def _svc() -> BookingDetailService:
    service = BookingDetailService.__new__(BookingDetailService)
    service.payment_repo = SimpleNamespace()
    service.review_repo = SimpleNamespace()
    service.review_tip_repo = SimpleNamespace()
    service.conversation_repo = SimpleNamespace()
    service.message_repo = SimpleNamespace()
    service.webhook_repo = SimpleNamespace()
    return service


def test_build_service_info_handles_non_string_catalog_fields():
    service = _svc()
    booking = SimpleNamespace(
        service_name="Fallback Name",
        instructor_service=SimpleNamespace(
            catalog_entry=SimpleNamespace(
                slug=123,
                name=456,
                category=SimpleNamespace(name=789),
            )
        ),
    )

    info = service._build_service_info(booking)

    assert info.slug == "unknown"
    assert info.name == "Fallback Name"
    assert info.category == "Unknown"


def test_resolve_helpers_return_safe_defaults_on_errors():
    service = _svc()

    service.payment_repo.get_payment_by_intent_id = lambda _pi: (_ for _ in ()).throw(RuntimeError())
    service.payment_repo.get_payment_by_booking_id = lambda _id: (_ for _ in ()).throw(RuntimeError())
    service.payment_repo.get_payment_events_for_booking = (
        lambda _id: (_ for _ in ()).throw(RuntimeError())
    )
    service.review_repo.get_by_booking_id = lambda _id: (_ for _ in ()).throw(RuntimeError())
    service.review_tip_repo.get_by_booking_id = lambda _id: (_ for _ in ()).throw(RuntimeError())

    assert service._resolve_payment_intent(SimpleNamespace(payment_intent_id="pi_123", id="b1")) is None
    assert service._resolve_payment_intent(SimpleNamespace(payment_intent_id=None, id="b1")) is None
    assert service._resolve_payment_events("b1") == []
    assert service._resolve_review("b1") is None
    assert service._resolve_tip("b1") is None


def test_payment_status_and_failure_branches():
    service = _svc()
    now = datetime.now(timezone.utc)

    events = [
        PaymentEvent(booking_id="b1", event_type="fail_auth", event_data={}, created_at=now),
        PaymentEvent(
            booking_id="b1",
            event_type="refund_succeeded",
            event_data={},
            created_at=now + timedelta(seconds=1),
        ),
    ]

    failures = service._build_payment_failures(events)
    assert failures == []

    booking = SimpleNamespace(payment_status="unknown", auth_scheduled_for=None)
    assert service._resolve_payment_status(booking, events) == "refunded"

    booking.auth_scheduled_for = now
    assert service._resolve_payment_status(booking, []) == "scheduled"


def test_messages_summary_fetches_last_message_when_missing_on_conversation():
    service = _svc()
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(student_id="s", instructor_id="i")
    conversation = SimpleNamespace(id="c1", last_message_at=None)

    service.conversation_repo = SimpleNamespace(find_by_pair=lambda *_args, **_kwargs: conversation)
    service.message_repo = SimpleNamespace(
        count_for_conversation=lambda _cid: 5,
        get_last_message_at_for_conversation=lambda _cid: now,
    )

    summary = service._build_messages_summary(booking)

    assert summary.message_count == 5
    assert summary.last_message_at is not None


def test_timeline_skips_none_timestamps_and_deduplicates_same_event_time():
    service = _svc()
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        created_at=None,
        confirmed_at=now,
        updated_at=now,
        rescheduled_from_booking_id=None,
        rescheduled_to_booking_id=None,
        cancelled_at=None,
        completed_at=None,
        status=BookingStatus.CONFIRMED,
        auth_scheduled_for=None,
        payment_status=None,
    )

    payment_events = [
        PaymentEvent(booking_id="b1", event_type="auth_succeeded", event_data={}, created_at=now),
        PaymentEvent(booking_id="b1", event_type="auth_succeeded", event_data={}, created_at=now),
    ]

    timeline = service._build_timeline(
        booking,
        payment_events,
        [],
        review=None,
        tip=None,
        messages_summary=None,
    )

    auth_events = [entry for entry in timeline if entry.event == "PAYMENT_AUTHORIZED"]
    assert len(auth_events) == 1


def test_compute_recommended_actions_uses_duration_when_end_is_missing():
    service = _svc()
    booking = SimpleNamespace(
        status=BookingStatus.CONFIRMED,
        booking_end_utc=None,
        booking_start_utc=datetime.now(timezone.utc) - timedelta(hours=3),
        duration_minutes=30,
    )

    actions = service._compute_recommended_actions(
        booking,
        payment=SimpleNamespace(status="captured"),
    )

    action_names = {item.action for item in actions}
    assert "force_complete" in action_names
    assert "refund_preview" in action_names
