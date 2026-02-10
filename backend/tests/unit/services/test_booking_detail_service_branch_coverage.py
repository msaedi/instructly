"""Additional branch coverage tests for BookingDetailService internals."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from app.models.booking import BookingStatus
from app.models.payment import PaymentEvent
from app.services import booking_detail_service as booking_detail_module
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


def test_helper_functions_cover_additional_failure_categories_and_normalizers():
    assert booking_detail_module._redact_stripe_id("   ") is None
    assert booking_detail_module._hash_email(None) == ""
    assert booking_detail_module._normalize_booking_status("confirmed") == "CONFIRMED"

    assert (
        booking_detail_module._infer_failure_category("x", {"error": "card expired"})
        == "expired_card"
    )
    assert (
        booking_detail_module._infer_failure_category("x", {"error": "cvc check failed"})
        == "incorrect_cvc"
    )
    assert (
        booking_detail_module._infer_failure_category("x", {"error": "payment declined"})
        == "card_declined"
    )
    assert (
        booking_detail_module._infer_failure_category("auth_failed", {}) == "card_declined"
    )
    assert (
        booking_detail_module._infer_failure_category("refund_failed", {}) == "refund_failed"
    )
    assert booking_detail_module._infer_failure_category("totally_failed", {}) == "unknown_error"


def test_build_service_info_prefers_catalog_values():
    service = _svc()
    booking = SimpleNamespace(
        service_name="Fallback",
        instructor_service=SimpleNamespace(
            catalog_entry=SimpleNamespace(
                slug="math-algebra",
                name="Algebra Tutoring",
                category=SimpleNamespace(name="Math"),
            )
        ),
    )
    info = service._build_service_info(booking)
    assert info.slug == "math-algebra"
    assert info.name == "Algebra Tutoring"
    assert info.category == "Math"


def test_build_payment_amount_handles_invalid_total_and_explicit_payout():
    service = _svc()
    booking = SimpleNamespace(total_price=object())
    payment_intent = SimpleNamespace(amount=None, application_fee=125, instructor_payout_cents=3333)
    amount = service._build_payment_amount(booking, payment_intent, credits_applied_cents=0, tip=None)
    assert amount.gross == 0.0
    assert amount.net_to_instructor == 33.33


def test_resolve_payment_status_additional_paths():
    service = _svc()
    booking = SimpleNamespace(payment_status="unknown", auth_scheduled_for=None)
    events = [
        PaymentEvent(
            booking_id="b1",
            event_type="payment_captured",
            event_data={},
            created_at=datetime.now(timezone.utc),
        )
    ]
    assert service._resolve_payment_status(booking, events) == "captured"

    events = [
        PaymentEvent(
            booking_id="b1",
            event_type="auth_scheduled",
            event_data={},
            created_at=datetime.now(timezone.utc),
        )
    ]
    assert service._resolve_payment_status(booking, events) == "scheduled"
    booking.payment_status = "authorized"
    assert service._resolve_payment_status(booking, []) == "authorized"
    booking.payment_status = "mystery"
    assert service._resolve_payment_status(booking, []) == "mystery"
    booking.payment_status = ""
    assert service._resolve_payment_status(booking, []) == "failed"


def test_build_messages_summary_uses_existing_last_message_timestamp():
    service = _svc()
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(student_id="s", instructor_id="i")
    conversation = SimpleNamespace(id="c1", last_message_at=now)
    service.conversation_repo = SimpleNamespace(find_by_pair=lambda *_args, **_kwargs: conversation)
    service.message_repo = SimpleNamespace(
        count_for_conversation=lambda _cid: 2,
        get_last_message_at_for_conversation=lambda _cid: (_ for _ in ()).throw(
            AssertionError("should not fetch when already present")
        ),
    )
    summary = service._build_messages_summary(booking)
    assert summary.last_message_at is not None
    assert summary.message_count == 2


def test_timeline_includes_confirmed_cancelled_and_skips_unmapped_events():
    service = _svc()
    now = datetime.now(timezone.utc)
    booking = SimpleNamespace(
        created_at=now - timedelta(hours=4),
        confirmed_at=now - timedelta(hours=3),
        updated_at=now - timedelta(hours=1),
        rescheduled_from_booking_id=None,
        rescheduled_to_booking_id=None,
        cancelled_at=now - timedelta(hours=2),
        completed_at=None,
        status=BookingStatus.CANCELLED,
        auth_scheduled_for=None,
        payment_status=None,
    )
    payment_events = [
        PaymentEvent(
            booking_id="b1",
            event_type="unmapped_event",
            event_data={},
            created_at=now - timedelta(hours=2),
        )
    ]
    webhook_events = [SimpleNamespace(event_type="unknown", received_at=now, event_id="evt_1")]
    timeline = service._build_timeline(
        booking,
        payment_events,
        webhook_events,
        review=None,
        tip=None,
        messages_summary=None,
    )
    names = [item.event for item in timeline]
    assert "BOOKING_CONFIRMED" in names
    assert "BOOKING_CANCELLED" in names
    assert all(name != "unmapped_event" for name in names)


def test_compute_recommended_actions_non_confirmed_only_contact_action():
    service = _svc()
    booking = SimpleNamespace(
        status=BookingStatus.CANCELLED,
        booking_end_utc=None,
        booking_start_utc=None,
        duration_minutes=None,
    )
    actions = service._compute_recommended_actions(
        booking,
        payment=SimpleNamespace(status="captured"),
    )
    assert [action.action for action in actions] == ["contact_instructor"]


def test_get_booking_detail_trace_links_without_webhooks():
    service = _svc()
    now = datetime.now(timezone.utc)

    booking = SimpleNamespace(
        id="booking-1",
        student_id="student-1",
        instructor_id="inst-1",
        instructor_service_id="svc-1",
        booking_date=date.today(),
        start_time=time(9, 0),
        end_time=time(10, 0),
        booking_start_utc=now + timedelta(hours=1),
        booking_end_utc=now + timedelta(hours=2),
        service_name="Math",
        hourly_rate=75,
        total_price=75,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        location_type="online",
        created_at=now - timedelta(days=1),
        updated_at=now,
        confirmed_at=None,
        completed_at=None,
        cancelled_at=None,
        cancelled_by_id=None,
        cancellation_reason=None,
        payment_status=None,
        payment_intent_id=None,
        auth_scheduled_for=None,
        rescheduled_from_booking_id=None,
        rescheduled_to_booking_id=None,
        student_note=None,
        instructor_note=None,
        instructor_service=SimpleNamespace(
            catalog_entry=SimpleNamespace(slug="math", name="Math", category=SimpleNamespace(name="Math"))
        ),
        student=SimpleNamespace(
            id="student-1",
            first_name="Ava",
            last_name="Taylor",
            email="ava@example.com",
        ),
        instructor=SimpleNamespace(
            id="inst-1",
            first_name="Sam",
            last_name="Lee",
            email="sam@example.com",
        ),
    )

    service.booking_repo = SimpleNamespace(get_booking_with_details=lambda _id: booking)
    service.booking_note_repo = SimpleNamespace(list_for_booking=lambda _id: [])
    service.payment_repo = SimpleNamespace(
        get_payment_by_booking_id=lambda _id: None,
        get_payment_events_for_booking=lambda _id: [],
    )
    service.review_repo = SimpleNamespace(get_by_booking_id=lambda _id: None)
    service.review_tip_repo = SimpleNamespace(get_by_booking_id=lambda _id: None)
    service.conversation_repo = SimpleNamespace(find_by_pair=lambda *_args, **_kwargs: None)
    service.message_repo = SimpleNamespace(
        count_for_conversation=lambda _cid: 0,
        get_last_message_at_for_conversation=lambda _cid: None,
    )
    service.webhook_repo = SimpleNamespace(list_events_for_related_entity=lambda **_kwargs: [])

    detail = service.get_booking_detail(
        "booking-1",
        include_messages_summary=False,
        include_webhooks=False,
        include_trace_links=True,
    )
    assert detail is not None
    assert detail.webhooks is None
    assert detail.traces is not None and detail.traces.included is True
