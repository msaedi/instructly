from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.booking_note import BookingNote
from app.models.conversation import Conversation
from app.models.instructor import InstructorProfile
from app.models.message import MESSAGE_TYPE_USER, Message
from app.models.payment import PaymentEvent, PaymentIntent
from app.models.service_catalog import InstructorService
from app.models.webhook_event import WebhookEvent
from app.services import booking_detail_service as booking_detail_module
from app.services.booking_detail_service import BookingDetailService

try:  # pragma: no cover - support running from repo root or backend/
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


def _get_active_service_id(db, instructor_id: str) -> str:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if not profile:
        raise RuntimeError("Instructor profile not found for booking detail service test")
    service = (
        db.query(InstructorService)
        .filter(
            InstructorService.instructor_profile_id == profile.id,
            InstructorService.is_active == True,
        )
        .first()
    )
    if not service:
        raise RuntimeError("Active service not found for booking detail service test")
    return service.id


def _create_booking(
    db,
    *,
    student_id: str,
    instructor_id: str,
    instructor_service_id: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    status: BookingStatus,
    offset_index: int,
) -> Booking:
    booking = create_booking_pg_safe(
        db,
        student_id=student_id,
        instructor_id=instructor_id,
        instructor_service_id=instructor_service_id,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        service_name="Test Lesson",
        hourly_rate=75,
        total_price=75,
        duration_minutes=60,
        status=status,
        offset_index=offset_index,
    )
    db.flush()
    return booking


def _attach_payment(
    db,
    booking: Booking,
    *,
    payment_status: str = "authorized",
    event_type: str = "auth_succeeded",
    event_time: datetime | None = None,
) -> tuple[str, str]:
    payment_intent_id = f"pi_{generate_ulid()}"
    charge_id = f"ch_{generate_ulid()}"
    booking.payment_intent_id = payment_intent_id
    booking.payment_status = payment_status
    db.flush()

    db.add(
        PaymentIntent(
            booking_id=booking.id,
            stripe_payment_intent_id=payment_intent_id,
            amount=7500,
            application_fee=750,
            status="succeeded",
        )
    )
    db.add(
        PaymentEvent(
            booking_id=booking.id,
            event_type=event_type,
            event_data={"amount_cents": 7500, "charge_id": charge_id},
            created_at=event_time or datetime.now(timezone.utc),
        )
    )
    db.commit()
    return payment_intent_id, charge_id


class TestBookingDetailService:
    def test_booking_detail_returns_complete_response(
        self, db, test_student, test_instructor_with_availability
    ):
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            status=BookingStatus.CONFIRMED,
            offset_index=0,
        )

        _attach_payment(db, booking)

        conversation = Conversation(
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
        )
        db.add(conversation)
        db.flush()
        message = Message(
            conversation_id=conversation.id,
            sender_id=test_student.id,
            content="Hello",
            message_type=MESSAGE_TYPE_USER,
        )
        db.add(message)
        conversation.last_message_at = message.created_at
        db.add(
            WebhookEvent(
                source="stripe",
                event_type="payment_intent.succeeded",
                event_id=f"evt_{generate_ulid()}",
                payload={},
                status="processed",
                related_entity_type="booking",
                related_entity_id=booking.id,
                received_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        service = BookingDetailService(db)
        detail = service.get_booking_detail(
            booking_id=booking.id,
            include_messages_summary=True,
            include_webhooks=True,
        )

        assert detail is not None
        assert detail.meta.booking_id == booking.id
        assert detail.booking.id == booking.id
        assert detail.payment is not None
        assert detail.messages is not None
        assert detail.messages.included is True
        assert detail.webhooks is not None
        assert detail.webhooks.included is True
        assert detail.recommended_actions

    def test_booking_detail_timeline_ordered_chronologically(
        self, db, test_student, test_instructor_with_availability
    ):
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            status=BookingStatus.CONFIRMED,
            offset_index=1,
        )
        now = datetime.now(timezone.utc)
        booking.created_at = now - timedelta(days=2)
        booking.confirmed_at = now - timedelta(days=2, hours=1)
        booking.completed_at = now - timedelta(days=1)
        db.flush()

        _attach_payment(
            db,
            booking,
            event_time=now - timedelta(days=1, hours=2),
            event_type="payment_captured",
            payment_status="settled",
        )

        service = BookingDetailService(db)
        detail = service.get_booking_detail(booking.id)
        assert detail is not None
        timestamps = [event.ts for event in detail.timeline]
        assert timestamps == sorted(timestamps)

    def test_booking_detail_payment_ids_redacted(self, db, test_booking):
        payment_intent_id, charge_id = _attach_payment(db, test_booking)
        service = BookingDetailService(db)
        detail = service.get_booking_detail(test_booking.id)

        assert detail is not None
        assert detail.payment is not None
        payment_ids = detail.payment.ids
        assert payment_ids.payment_intent is not None
        assert payment_ids.charge is not None
        assert payment_ids.payment_intent.endswith(payment_intent_id[-4:])
        assert "..." in payment_ids.payment_intent
        assert payment_ids.charge.endswith(charge_id[-4:])
        assert "..." in payment_ids.charge

    def test_booking_detail_names_privacy_safe(self, db, test_booking, test_student):
        service = BookingDetailService(db)
        detail = service.get_booking_detail(test_booking.id)
        assert detail is not None

        expected = f"{test_student.first_name} {test_student.last_name[0].upper()}."
        assert detail.booking.student.name == expected

    def test_booking_detail_recommended_actions_refund_eligible(
        self, db, test_booking
    ):
        test_booking.status = BookingStatus.CONFIRMED
        _attach_payment(db, test_booking, payment_status="authorized")

        service = BookingDetailService(db)
        detail = service.get_booking_detail(test_booking.id)
        assert detail is not None

        actions = {action.action for action in detail.recommended_actions}
        assert "refund_preview" in actions

    def test_booking_detail_recommended_actions_force_complete(
        self, db, test_student, test_instructor_with_availability
    ):
        service_id = _get_active_service_id(db, test_instructor_with_availability.id)
        past_date = datetime.now(timezone.utc).date() - timedelta(days=2)
        booking = _create_booking(
            db,
            student_id=test_student.id,
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service_id,
            booking_date=past_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            status=BookingStatus.CONFIRMED,
            offset_index=2,
        )
        db.commit()

        service = BookingDetailService(db)
        detail = service.get_booking_detail(booking.id)
        assert detail is not None

        actions = {action.action for action in detail.recommended_actions}
        assert "force_complete" in actions

    def test_booking_detail_includes_webhooks_when_requested(
        self, db, test_booking
    ):
        db.add(
            WebhookEvent(
                source="stripe",
                event_type="payment_intent.succeeded",
                event_id=f"evt_{generate_ulid()}",
                payload={},
                status="processed",
                related_entity_type="booking",
                related_entity_id=test_booking.id,
                received_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        service = BookingDetailService(db)
        detail = service.get_booking_detail(test_booking.id, include_webhooks=True)

        assert detail is not None
        assert detail.webhooks is not None
        assert detail.webhooks.included is True
        assert detail.webhooks.events

    def test_booking_detail_excludes_messages_by_default(self, db, test_booking):
        service = BookingDetailService(db)
        detail = service.get_booking_detail(test_booking.id)

        assert detail is not None
        assert detail.messages is None

    def test_booking_detail_includes_admin_notes(self, db, test_booking, test_student):
        now = datetime.now(timezone.utc)
        db.add(
            BookingNote(
                booking_id=test_booking.id,
                created_by_id=test_student.id,
                note="First note",
                visibility="internal",
                category="general",
                created_at=now - timedelta(hours=1),
            )
        )
        db.add(
            BookingNote(
                booking_id=test_booking.id,
                created_by_id=None,
                note="Second note",
                visibility="internal",
                category="general",
                created_at=now,
            )
        )
        db.commit()

        service = BookingDetailService(db)
        detail = service.get_booking_detail(test_booking.id)
        assert detail is not None
        assert detail.admin_notes
        assert detail.admin_notes[0].note == "Second note"
        assert detail.admin_notes[0].created_by is None
        assert detail.admin_notes[1].note == "First note"
        assert detail.admin_notes[1].created_by is not None
        assert detail.admin_notes[1].created_by.email == test_student.email

    def test_booking_detail_not_found_returns_404(
        self, client: TestClient, mcp_service_headers
    ):
        res = client.get(
            "/api/v1/admin/mcp/bookings/01INVALIDBOOKING000000000000/detail",
            headers=mcp_service_headers,
        )
        assert res.status_code == 404

    def test_booking_detail_route_returns_success(
        self, client: TestClient, mcp_service_headers, test_booking
    ):
        res = client.get(
            f"/api/v1/admin/mcp/bookings/{test_booking.id}/detail",
            headers=mcp_service_headers,
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["booking"]["id"] == test_booking.id


def test_booking_detail_helper_mappings_and_redaction():
    assert booking_detail_module._redact_stripe_id("pi_1234567890") == "pi_...7890"
    assert booking_detail_module._redact_stripe_id("1234") == "1234"
    assert booking_detail_module._redact_stripe_id(None) is None

    assert booking_detail_module._privacy_name(None, None) == "Unknown"
    assert booking_detail_module._privacy_name("Sarah", "Chen") == "Sarah C."
    assert len(booking_detail_module._hash_email("Test@Email.com")) == 8

    assert booking_detail_module._map_payment_event("auth_failed") == "PAYMENT_AUTH_FAILED"
    assert booking_detail_module._map_payment_event("auth_succeeded") == "PAYMENT_AUTHORIZED"
    assert booking_detail_module._map_payment_event("capture_failed") == "PAYMENT_CAPTURE_FAILED"
    assert booking_detail_module._map_payment_event("payment_captured") == "PAYMENT_CAPTURED"
    assert booking_detail_module._map_payment_event("refund_succeeded") == "PAYMENT_REFUNDED"
    assert booking_detail_module._map_payment_event("paid_out") == "PAYMENT_SETTLED"
    assert booking_detail_module._map_payment_event("unknown_event") is None

    assert (
        booking_detail_module._map_webhook_event("payment_intent.payment_failed")
        == "PAYMENT_AUTH_FAILED"
    )
    assert (
        booking_detail_module._map_webhook_event("payment_intent.amount_capturable_updated")
        == "PAYMENT_AUTHORIZED"
    )
    assert booking_detail_module._map_webhook_event("charge.captured") == "PAYMENT_CAPTURED"
    assert booking_detail_module._map_webhook_event("charge.refunded") == "PAYMENT_REFUNDED"
    assert booking_detail_module._map_webhook_event("unknown") is None


def test_booking_detail_credit_tip_and_schedule_helpers():
    now = datetime(2026, 2, 3, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        PaymentEvent(
            booking_id="bk1",
            event_type="credits_applied",
            event_data={"applied_cents": 250},
            created_at=now,
        )
    ]
    assert booking_detail_module._resolve_credit_applied_cents(events) == 250

    fallback_events = [
        PaymentEvent(
            booking_id="bk1",
            event_type="auth_succeeded_credits_only",
            event_data={"credits_applied_cents": 400},
            created_at=now,
        )
    ]
    assert booking_detail_module._resolve_credit_applied_cents(fallback_events) == 400

    tip_failed = SimpleNamespace(status="failed", amount_cents=500)
    tip_pending = SimpleNamespace(status="pending", amount_cents=600)
    assert booking_detail_module._resolve_tip_cents(tip_failed) == 0
    assert booking_detail_module._resolve_tip_cents(tip_pending) == 600

    booking_with_auth = SimpleNamespace(
        auth_scheduled_for=now,
        booking_start_utc=now + timedelta(hours=1),
        booking_end_utc=None,
        duration_minutes=60,
    )
    assert booking_detail_module._resolve_scheduled_authorize_at(booking_with_auth) == now

    booking_with_start = SimpleNamespace(
        auth_scheduled_for=None,
        booking_start_utc=now,
        booking_end_utc=None,
        duration_minutes=60,
    )
    assert booking_detail_module._resolve_scheduled_authorize_at(booking_with_start) == now - timedelta(
        hours=24
    )
    assert booking_detail_module._resolve_scheduled_capture_at(booking_with_start) == now + timedelta(
        minutes=60, hours=24
    )

    booking_with_end = SimpleNamespace(
        auth_scheduled_for=None,
        booking_start_utc=now,
        booking_end_utc=now + timedelta(minutes=30),
        duration_minutes=30,
    )
    assert booking_detail_module._resolve_scheduled_capture_at(booking_with_end) == now + timedelta(
        minutes=30, hours=24
    )


def test_booking_detail_failure_inference_and_payment_ids(db):
    service = BookingDetailService(db)
    booking = SimpleNamespace(payment_intent_id=None)
    payment_intent = PaymentIntent(
        booking_id="bk1",
        stripe_payment_intent_id="pi_1234567890",
        amount=1000,
        application_fee=100,
        status="succeeded",
    )
    events = [
        PaymentEvent(
            booking_id="bk1",
            event_type="auth_failed",
            event_data={"error_type": "card_declined", "charge_id": "ch_123456"},
            created_at=datetime.now(timezone.utc),
        )
    ]
    payment_ids = service._build_payment_ids(booking, events, payment_intent)
    assert payment_ids.payment_intent.endswith("7890")
    assert payment_ids.charge.endswith("3456")

    failures = service._build_payment_failures(events)
    assert failures
    assert failures[0].category == "card_declined"


def test_booking_detail_helper_edge_cases():
    naive = datetime(2026, 2, 3, 12, 0, 0)
    assert booking_detail_module._ensure_utc(naive).tzinfo == timezone.utc
    assert booking_detail_module._redact_stripe_id("12345") == "...2345"
    assert booking_detail_module._redact_stripe_id(123) is None
    assert booking_detail_module._privacy_name("Sarah", None) == "Sarah"
    assert booking_detail_module._normalize_booking_status(BookingStatus.CONFIRMED) == "CONFIRMED"
    assert booking_detail_module._normalize_booking_status(None) == ""

    tip_success = SimpleNamespace(status="completed", amount_cents=900)
    assert booking_detail_module._resolve_tip_cents(tip_success) == 900

    booking_missing = SimpleNamespace(
        auth_scheduled_for=None,
        booking_start_utc=None,
        booking_end_utc=None,
        duration_minutes=None,
    )
    assert booking_detail_module._resolve_scheduled_authorize_at(booking_missing) is None
    assert booking_detail_module._resolve_scheduled_capture_at(booking_missing) is None

    assert booking_detail_module._map_payment_event("auth_scheduled") == "PAYMENT_SCHEDULED"
    assert booking_detail_module._map_payment_event("payment_locked") == "PAYMENT_LOCKED"
    assert booking_detail_module._map_payment_event("refund_failed") is None
    assert booking_detail_module._map_webhook_event("payment_intent.succeeded") == "PAYMENT_CAPTURED"

    assert (
        booking_detail_module._infer_failure_category("auth_failed", {"error": "Insufficient funds"})
        == "insufficient_funds"
    )
    assert booking_detail_module._infer_failure_category("capture_failed", {}) == "capture_failed"


def test_booking_detail_payment_status_and_amount_helpers(db):
    service = BookingDetailService(db)
    now = datetime.now(timezone.utc)

    booking = SimpleNamespace(
        payment_status="locked",
        auth_scheduled_for=None,
        booking_start_utc=None,
        booking_end_utc=None,
        duration_minutes=None,
    )
    assert service._resolve_payment_status(booking, []) == "locked"

    booking.payment_status = "settled"
    assert service._resolve_payment_status(booking, []) == "settled"

    booking.payment_status = "unknown"
    booking.auth_scheduled_for = now
    assert service._resolve_payment_status(booking, []) == "scheduled"

    booking.auth_scheduled_for = None
    events = [
        PaymentEvent(
            booking_id="bk1",
            event_type="auth_failed",
            event_data={},
            created_at=now,
        )
    ]
    assert service._resolve_payment_status(booking, events) == "failed"

    payment_intent = PaymentIntent(
        booking_id="bk1",
        stripe_payment_intent_id="pi_123456",
        amount=10000,
        application_fee=1000,
        status="succeeded",
    )
    amount = service._build_payment_amount(
        SimpleNamespace(total_price=None),
        payment_intent,
        0,
        None,
    )
    assert amount.net_to_instructor == 90.0

    amount_error = service._build_payment_amount(
        SimpleNamespace(total_price="bad"),
        None,
        0,
        None,
    )
    assert amount_error.gross == 0.0

    ids = service._build_payment_ids(
        SimpleNamespace(payment_intent_id="pi_9999"),
        [PaymentEvent(booking_id="bk1", event_type="capture", event_data={}, created_at=now)],
        None,
    )
    assert ids.payment_intent.endswith("9999")
    assert ids.charge is None

    assert service._build_payment_info(
        SimpleNamespace(payment_status=None, auth_scheduled_for=None, booking_start_utc=None,
                        booking_end_utc=None, duration_minutes=None),
        None,
        [],
        0,
        None,
    ) is None


def test_booking_detail_messages_webhooks_and_timeline_helpers(db):
    service = BookingDetailService(db)
    now = datetime.now(timezone.utc)

    booking = SimpleNamespace(student_id="student", instructor_id="instructor")
    service.conversation_repo = SimpleNamespace(find_by_pair=lambda *_args, **_kw: None)
    summary = service._build_messages_summary(booking)
    assert summary.conversation_id is None

    conversation = SimpleNamespace(id="conv1", last_message_at=None)
    service.conversation_repo = SimpleNamespace(
        find_by_pair=lambda *_args, **_kw: conversation
    )
    service.message_repo = SimpleNamespace(
        count_for_conversation=lambda _cid: 2,
        get_last_message_at_for_conversation=lambda _cid: now,
    )
    summary = service._build_messages_summary(booking)
    assert summary.message_count == 2
    assert summary.last_message_at is not None

    service.webhook_repo = SimpleNamespace(
        list_events_for_related_entity=lambda **_kw: [SimpleNamespace(event_type="charge.captured")]
    )
    events = service._fetch_webhook_events("bk1")
    assert events

    service.webhook_repo = SimpleNamespace(list_events_for_related_entity=lambda **_kw: (_ for _ in ()).throw(RuntimeError()))
    assert service._fetch_webhook_events("bk1") == []

    webhook_summary = service._build_webhooks_summary(
        [
            SimpleNamespace(
                event_id="evt1",
                id="evt1",
                event_type="charge.captured",
                status="processed",
                received_at=now,
                processed_at=None,
                created_at=None,
            ),
            SimpleNamespace(
                event_id="evt2",
                id="evt2",
                event_type="charge.captured",
                status="processed",
                received_at=None,
                processed_at=None,
                created_at=None,
            ),
        ]
    )
    assert len(webhook_summary.events) == 1

    timeline_booking = SimpleNamespace(
        created_at=now - timedelta(days=2),
        confirmed_at=now - timedelta(days=2, hours=1),
        updated_at=now - timedelta(days=1),
        rescheduled_from_booking_id="bk-old",
        rescheduled_to_booking_id=None,
        cancelled_at=None,
        completed_at=None,
        status=BookingStatus.CANCELLED,
        auth_scheduled_for=now - timedelta(days=1, hours=3),
        payment_status=PaymentStatus.LOCKED.value,
        booking_start_utc=now - timedelta(days=2),
        booking_end_utc=now - timedelta(days=2, hours=1),
        duration_minutes=60,
    )
    timeline = service._build_timeline(
        timeline_booking,
        [PaymentEvent(booking_id="bk1", event_type="auth_succeeded", event_data={}, created_at=now - timedelta(days=1, hours=2))],
        [SimpleNamespace(event_type="payment_intent.succeeded", received_at=now - timedelta(days=1, hours=1), event_id="evt1")],
        review=SimpleNamespace(created_at=now - timedelta(days=1, hours=4)),
        tip=SimpleNamespace(created_at=now - timedelta(days=1, hours=3), processed_at=None),
        messages_summary=SimpleNamespace(last_message_at=now - timedelta(days=1, hours=5), message_count=3),
    )
    events = {event.event for event in timeline}
    assert "BOOKING_CREATED" in events
    assert "BOOKING_RESCHEDULED" in events
    assert "BOOKING_CANCELLED" in events
    assert "PAYMENT_LOCKED" in events
    assert "MESSAGE_SENT" in events

    timeline_booking.payment_status = PaymentStatus.SETTLED.value
    timeline2 = service._build_timeline(
        timeline_booking,
        [],
        [],
        review=None,
        tip=None,
        messages_summary=None,
    )
    assert any(event.event == "PAYMENT_SETTLED" for event in timeline2)
