"""Service layer for MCP booking detail support workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import logging
from typing import Any, Iterable, Sequence

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.payment import PaymentEvent, PaymentIntent
from app.models.review import Review, ReviewTip
from app.models.webhook_event import WebhookEvent
from app.repositories.factory import RepositoryFactory
from app.repositories.review_repository import ReviewRepository, ReviewTipRepository
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.schemas.admin_booking_detail import (
    BookingDetailMeta,
    BookingDetailResponse,
    BookingInfo,
    MessagesSummary,
    ParticipantInfo,
    PaymentAmount,
    PaymentFailure,
    PaymentIds,
    PaymentInfo,
    RecommendedAction,
    ServiceInfo,
    TimelineEvent,
    TracesSummary,
    WebhookEventBrief,
    WebhooksSummary,
)
from app.services.base import BaseService

logger = logging.getLogger(__name__)

_ALLOWED_PAYMENT_STATUSES = {
    "scheduled",
    "authorized",
    "captured",
    "settled",
    "failed",
    "refunded",
    "locked",
}

_TIP_SUCCESS_STATUSES = {"completed", "succeeded", "processing"}


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _redact_stripe_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    last4 = cleaned[-4:] if len(cleaned) > 4 else cleaned
    prefix = cleaned.split("_", 1)[0] if "_" in cleaned else ""
    if prefix:
        return f"{prefix}_...{last4}"
    return f"...{last4}" if len(cleaned) > 4 else last4


def _privacy_name(first_name: str | None, last_name: str | None) -> str:
    if not first_name:
        return "Unknown"
    name = first_name.strip()
    if last_name and last_name.strip():
        name += f" {last_name.strip()[0].upper()}."
    return name


def _hash_email(email: str | None) -> str:
    if not email:
        return ""
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return digest[:8]


def _resolve_credit_applied_cents(events: Sequence[PaymentEvent]) -> int:
    credit_cents = 0
    for event in events:
        data = event.event_data or {}
        if event.event_type == "credits_applied":
            credit_cents = int(data.get("applied_cents", 0) or 0)
        elif credit_cents == 0 and event.event_type == "auth_succeeded_credits_only":
            credit_cents = int(
                data.get("credits_applied_cents", data.get("original_amount_cents", 0)) or 0
            )
    return max(0, credit_cents)


def _resolve_tip_cents(tip: ReviewTip | None) -> int:
    if not tip:
        return 0
    status = (tip.status or "").lower()
    if status and status not in _TIP_SUCCESS_STATUSES and status != "pending":
        return 0
    return int(tip.amount_cents or 0)


def _resolve_scheduled_authorize_at(booking: Booking) -> datetime | None:
    if booking.auth_scheduled_for:
        return _ensure_utc(booking.auth_scheduled_for)
    if booking.booking_start_utc is None:
        return None
    return _ensure_utc(booking.booking_start_utc) - timedelta(hours=24)


def _resolve_scheduled_capture_at(booking: Booking) -> datetime | None:
    if booking.booking_end_utc is not None:
        return _ensure_utc(booking.booking_end_utc) + timedelta(hours=24)
    if booking.booking_start_utc is None or booking.duration_minutes is None:
        return None
    start = _ensure_utc(booking.booking_start_utc)
    return start + timedelta(minutes=int(booking.duration_minutes)) + timedelta(hours=24)


def _normalize_booking_status(status: str | BookingStatus | None) -> str:
    if isinstance(status, BookingStatus):
        return status.value
    if isinstance(status, str):
        return status.upper()
    return ""


def _map_payment_event(event_type: str) -> str | None:
    lowered = event_type.lower()
    if "auth" in lowered and "failed" in lowered:
        return "PAYMENT_AUTH_FAILED"
    if "auth" in lowered and ("succeeded" in lowered or "success" in lowered):
        return "PAYMENT_AUTHORIZED"
    if "auth" in lowered and ("scheduled" in lowered or "attempt" in lowered):
        return "PAYMENT_SCHEDULED"
    if "capture" in lowered and "failed" in lowered:
        return "PAYMENT_CAPTURE_FAILED"
    if "captured" in lowered or "capture_success" in lowered:
        return "PAYMENT_CAPTURED"
    if "refund" in lowered and "failed" in lowered:
        return None
    if "refund" in lowered:
        return "PAYMENT_REFUNDED"
    if "locked" in lowered:
        return "PAYMENT_LOCKED"
    if "paid_out" in lowered or "payout" in lowered:
        return "PAYMENT_SETTLED"
    return None


def _map_webhook_event(event_type: str) -> str | None:
    lowered = event_type.lower()
    if "payment_intent.amount_capturable_updated" in lowered:
        return "PAYMENT_AUTHORIZED"
    if "payment_intent.payment_failed" in lowered:
        return "PAYMENT_AUTH_FAILED"
    if "charge.captured" in lowered or "charge.succeeded" in lowered:
        return "PAYMENT_CAPTURED"
    if "charge.refunded" in lowered:
        return "PAYMENT_REFUNDED"
    if "payment_intent.succeeded" in lowered:
        return "PAYMENT_CAPTURED"
    return None


def _infer_failure_category(event_type: str, data: dict[str, Any]) -> str | None:
    for key in ("error_type", "error_code", "failure_reason"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

    text = data.get("error")
    if isinstance(text, str) and text.strip():
        lowered = text.strip().lower()
        if "insufficient" in lowered:
            return "insufficient_funds"
        if "expired" in lowered:
            return "expired_card"
        if "cvc" in lowered or "cvv" in lowered:
            return "incorrect_cvc"
        if "declined" in lowered:
            return "card_declined"
        return "unknown_error"

    lowered = event_type.lower()
    if "auth" in lowered and "failed" in lowered:
        return "card_declined"
    if "capture" in lowered and "failed" in lowered:
        return "capture_failed"
    if "refund" in lowered and "failed" in lowered:
        return "refund_failed"
    if "failed" in lowered:
        return "unknown_error"
    return None


class BookingDetailService(BaseService):
    """Support-focused booking detail summary for MCP workflows."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.booking_repo = RepositoryFactory.create_booking_repository(db)
        self.payment_repo = RepositoryFactory.create_payment_repository(db)
        self.conversation_repo = RepositoryFactory.create_conversation_repository(db)
        self.message_repo = RepositoryFactory.create_message_repository(db)
        self.webhook_repo = WebhookEventRepository(db)
        self.review_repo = ReviewRepository(db)
        self.review_tip_repo = ReviewTipRepository(db)

    @BaseService.measure_operation("booking_detail.get")
    def get_booking_detail(
        self,
        booking_id: str,
        include_messages_summary: bool = False,
        include_webhooks: bool = True,
        include_trace_links: bool = False,
    ) -> BookingDetailResponse | None:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            return None

        payment_events = self._resolve_payment_events(booking.id)
        payment_intent = self._resolve_payment_intent(booking)
        review = self._resolve_review(booking.id)
        tip = self._resolve_tip(booking.id)
        credits_applied_cents = _resolve_credit_applied_cents(payment_events)

        payment_info = self._build_payment_info(
            booking,
            payment_intent,
            payment_events,
            credits_applied_cents,
            tip,
        )

        messages_summary = (
            self._build_messages_summary(booking) if include_messages_summary else None
        )

        webhook_events: list[WebhookEvent] = []
        webhooks_summary = None
        if include_webhooks:
            webhook_events = self._fetch_webhook_events(booking.id)
            webhooks_summary = self._build_webhooks_summary(webhook_events)

        timeline = self._build_timeline(
            booking,
            payment_events,
            webhook_events,
            review,
            tip,
            messages_summary,
        )

        traces_summary = None
        if include_trace_links:
            traces_summary = TracesSummary(included=True, trace_ids=[], support_code=None)

        recommended_actions = self._compute_recommended_actions(booking, payment_info)

        service_info = self._build_service_info(booking)
        booking_info = BookingInfo(
            id=booking.id,
            status=_normalize_booking_status(booking.status),
            scheduled_at=_ensure_utc(booking.booking_start_utc),
            duration_minutes=int(booking.duration_minutes or 0),
            location_type=str(booking.location_type or ""),
            service=service_info,
            student=self._build_participant(booking.student),
            instructor=self._build_participant(booking.instructor),
            created_at=_ensure_utc(booking.created_at),
            updated_at=_ensure_utc(booking.updated_at or booking.created_at),
        )

        return BookingDetailResponse(
            meta=BookingDetailMeta(
                generated_at=datetime.now(timezone.utc),
                booking_id=booking.id,
            ),
            booking=booking_info,
            timeline=timeline,
            payment=payment_info,
            messages=messages_summary,
            webhooks=webhooks_summary,
            traces=traces_summary,
            recommended_actions=recommended_actions,
        )

    def _build_service_info(self, booking: Booking) -> ServiceInfo:
        instructor_service = getattr(booking, "instructor_service", None)
        catalog_entry = getattr(instructor_service, "catalog_entry", None)
        slug = "unknown"
        name = getattr(booking, "service_name", None) or "Unknown"
        category = "Unknown"
        if catalog_entry is not None:
            slug_value = getattr(catalog_entry, "slug", None)
            if isinstance(slug_value, str) and slug_value:
                slug = slug_value
            name_value = getattr(catalog_entry, "name", None)
            if isinstance(name_value, str) and name_value:
                name = name_value
            category_obj = getattr(catalog_entry, "category", None)
            category_value = getattr(category_obj, "name", None)
            if isinstance(category_value, str) and category_value:
                category = category_value
        return ServiceInfo(slug=slug, name=name, category=category)

    def _build_participant(self, participant: Any) -> ParticipantInfo:
        return ParticipantInfo(
            id=str(getattr(participant, "id", "")),
            name=_privacy_name(
                getattr(participant, "first_name", None),
                getattr(participant, "last_name", None),
            ),
            email_hash=_hash_email(getattr(participant, "email", None)),
        )

    def _resolve_payment_intent(self, booking: Booking) -> PaymentIntent | None:
        if booking.payment_intent_id:
            try:
                return self.payment_repo.get_payment_by_intent_id(booking.payment_intent_id)
            except Exception:
                return None
        try:
            return self.payment_repo.get_payment_by_booking_id(booking.id)
        except Exception:
            return None

    def _resolve_payment_events(self, booking_id: str) -> Sequence[PaymentEvent]:
        try:
            return self.payment_repo.get_payment_events_for_booking(booking_id)
        except Exception:
            return []

    def _resolve_review(self, booking_id: str) -> Review | None:
        try:
            return self.review_repo.get_by_booking_id(booking_id)
        except Exception:
            return None

    def _resolve_tip(self, booking_id: str) -> ReviewTip | None:
        try:
            return self.review_tip_repo.get_by_booking_id(booking_id)
        except Exception:
            return None

    def _build_payment_amount(
        self,
        booking: Booking,
        payment_intent: PaymentIntent | None,
        credits_applied_cents: int,
        tip: ReviewTip | None,
    ) -> PaymentAmount:
        gross_cents = 0
        if payment_intent and payment_intent.amount is not None:
            gross_cents = int(payment_intent.amount) + credits_applied_cents
        elif booking.total_price is not None:
            try:
                gross_cents = int((Decimal(str(booking.total_price)) * 100).quantize(Decimal("1")))
            except Exception:
                gross_cents = 0
        platform_fee_cents = int(payment_intent.application_fee) if payment_intent else 0
        if payment_intent and payment_intent.instructor_payout_cents is not None:
            instructor_payout_cents = int(payment_intent.instructor_payout_cents)
        elif payment_intent and payment_intent.amount is not None:
            instructor_payout_cents = max(0, int(payment_intent.amount) - platform_fee_cents)
        else:
            instructor_payout_cents = 0

        tip_cents = _resolve_tip_cents(tip)

        return PaymentAmount(
            gross=round(gross_cents / 100.0, 2),
            platform_fee=round(platform_fee_cents / 100.0, 2),
            credits_applied=round(credits_applied_cents / 100.0, 2),
            tip=round(tip_cents / 100.0, 2),
            net_to_instructor=round(instructor_payout_cents / 100.0, 2),
        )

    def _build_payment_ids(
        self,
        booking: Booking,
        payment_events: Sequence[PaymentEvent],
        payment_intent: PaymentIntent | None,
    ) -> PaymentIds:
        intent_value = booking.payment_intent_id
        if not intent_value and payment_intent is not None:
            intent_value = payment_intent.stripe_payment_intent_id
        payment_intent_redacted = _redact_stripe_id(intent_value)
        charge = None
        for event in payment_events:
            data = event.event_data or {}
            for key in ("charge_id", "stripe_charge_id", "charge"):
                if key in data and charge is None:
                    charge = _redact_stripe_id(data.get(key))
        return PaymentIds(payment_intent=payment_intent_redacted, charge=charge)

    def _build_payment_failures(
        self, payment_events: Sequence[PaymentEvent]
    ) -> list[PaymentFailure]:
        failures: list[PaymentFailure] = []
        for event in payment_events:
            if "fail" not in event.event_type.lower():
                continue
            data = event.event_data or {}
            category = _infer_failure_category(event.event_type, data)
            if not category:
                continue
            failures.append(
                PaymentFailure(
                    ts=_ensure_utc(event.created_at),
                    category=category,
                )
            )
        return failures

    def _resolve_payment_status(
        self, booking: Booking, payment_events: Sequence[PaymentEvent]
    ) -> str:
        raw_status = (booking.payment_status or "").lower()
        if raw_status in {PaymentStatus.LOCKED.value, PaymentStatus.SETTLED.value}:
            return raw_status

        last_state: str | None = None
        for event in payment_events:
            mapped = _map_payment_event(event.event_type)
            if mapped:
                last_state = mapped

        if last_state == "PAYMENT_AUTH_FAILED" or last_state == "PAYMENT_CAPTURE_FAILED":
            return "failed"
        if last_state == "PAYMENT_REFUNDED":
            return "refunded"
        if last_state == "PAYMENT_CAPTURED":
            return "captured"
        if last_state == "PAYMENT_AUTHORIZED":
            return "authorized"
        if last_state == "PAYMENT_SCHEDULED":
            return "scheduled"
        if raw_status in _ALLOWED_PAYMENT_STATUSES:
            return raw_status
        if booking.auth_scheduled_for:
            return "scheduled"
        return raw_status or "failed"

    def _build_payment_info(
        self,
        booking: Booking,
        payment_intent: PaymentIntent | None,
        payment_events: Sequence[PaymentEvent],
        credits_applied_cents: int,
        tip: ReviewTip | None,
    ) -> PaymentInfo | None:
        if not (payment_intent or booking.payment_status or payment_events):
            return None

        amount = self._build_payment_amount(
            booking,
            payment_intent,
            credits_applied_cents,
            tip,
        )
        ids = self._build_payment_ids(booking, payment_events, payment_intent)
        failures = self._build_payment_failures(payment_events)
        status = self._resolve_payment_status(booking, payment_events)

        return PaymentInfo(
            status=status,
            amount=amount,
            ids=ids,
            scheduled_authorize_at=_resolve_scheduled_authorize_at(booking),
            scheduled_capture_at=_resolve_scheduled_capture_at(booking),
            failures=failures,
        )

    def _build_messages_summary(self, booking: Booking) -> MessagesSummary:
        conversation = self.conversation_repo.find_by_pair(
            booking.student_id, booking.instructor_id
        )
        if not conversation:
            return MessagesSummary(
                included=True,
                conversation_id=None,
                message_count=None,
                last_message_at=None,
            )

        message_count = self.message_repo.count_for_conversation(conversation.id)
        last_message_at = conversation.last_message_at
        if last_message_at is None:
            last_message_at = self.message_repo.get_last_message_at_for_conversation(
                conversation.id
            )
        return MessagesSummary(
            included=True,
            conversation_id=str(conversation.id),
            message_count=int(message_count or 0),
            last_message_at=_ensure_utc(last_message_at) if last_message_at else None,
        )

    def _fetch_webhook_events(self, booking_id: str) -> list[WebhookEvent]:
        try:
            return self.webhook_repo.list_events_for_related_entity(related_entity_id=booking_id)
        except Exception:
            logger.warning("Failed to load webhook events", exc_info=True)
            return []

    def _build_webhooks_summary(self, events: Iterable[WebhookEvent]) -> WebhooksSummary:
        items = []
        for event in events:
            ts = event.received_at or event.processed_at or event.created_at
            if ts is None:
                continue
            items.append(
                WebhookEventBrief(
                    event_id=str(event.event_id or event.id),
                    type=event.event_type,
                    status=event.status,
                    ts=_ensure_utc(ts),
                )
            )
        return WebhooksSummary(included=True, events=items)

    def _build_timeline(
        self,
        booking: Booking,
        payment_events: Sequence[PaymentEvent],
        webhook_events: Sequence[WebhookEvent],
        review: Review | None,
        tip: ReviewTip | None,
        messages_summary: MessagesSummary | None,
    ) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        seen: set[tuple[str, datetime]] = set()

        def add_event(
            ts: datetime | None, event: str, details: dict[str, Any] | None = None
        ) -> None:
            if ts is None:
                return
            ts_value = _ensure_utc(ts)
            key = (event, ts_value)
            if key in seen:
                return
            seen.add(key)
            events.append(TimelineEvent(ts=ts_value, event=event, details=details or {}))

        add_event(booking.created_at, "BOOKING_CREATED")
        if booking.confirmed_at:
            add_event(booking.confirmed_at, "BOOKING_CONFIRMED")
        if booking.rescheduled_from_booking_id or booking.rescheduled_to_booking_id:
            add_event(booking.updated_at or booking.created_at, "BOOKING_RESCHEDULED")
        if booking.cancelled_at:
            add_event(booking.cancelled_at, "BOOKING_CANCELLED")
        if booking.completed_at:
            add_event(booking.completed_at, "BOOKING_COMPLETED")
        if (
            _normalize_booking_status(booking.status) == BookingStatus.CANCELLED.value
            and booking.cancelled_at is None
        ):
            add_event(booking.updated_at or booking.created_at, "BOOKING_CANCELLED")

        if booking.auth_scheduled_for:
            add_event(booking.auth_scheduled_for, "PAYMENT_SCHEDULED")

        for event in payment_events:
            mapped = _map_payment_event(event.event_type)
            if not mapped:
                continue
            add_event(
                event.created_at,
                mapped,
                {"source": "payment_event", "event_type": event.event_type},
            )

        if booking.payment_status:
            status = booking.payment_status.lower()
            if status == PaymentStatus.SETTLED.value:
                add_event(booking.updated_at or booking.completed_at, "PAYMENT_SETTLED")
            if status == PaymentStatus.LOCKED.value:
                add_event(
                    getattr(booking, "locked_at", None) or booking.updated_at, "PAYMENT_LOCKED"
                )

        for webhook_event in webhook_events:
            mapped = _map_webhook_event(webhook_event.event_type)
            if not mapped:
                continue
            add_event(
                webhook_event.received_at,
                mapped,
                {
                    "source": "webhook",
                    "event_type": webhook_event.event_type,
                    "event_id": webhook_event.event_id,
                },
            )

        if review is not None:
            add_event(review.created_at, "REVIEW_SUBMITTED")
        if tip is not None:
            add_event(tip.processed_at or tip.created_at, "TIP_ADDED")
        if messages_summary and messages_summary.last_message_at:
            add_event(
                messages_summary.last_message_at,
                "MESSAGE_SENT",
                {"message_count": messages_summary.message_count or 0},
            )

        events.sort(key=lambda item: item.ts)
        return events

    def _compute_recommended_actions(
        self, booking: Booking, payment: PaymentInfo | None
    ) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        booking_status = _normalize_booking_status(booking.status)
        payment_status = payment.status if payment else None

        if booking_status == BookingStatus.CONFIRMED.value and payment_status in {
            "authorized",
            "captured",
        }:
            actions.append(
                RecommendedAction(
                    action="refund_preview",
                    reason="Booking can be refunded",
                    allowed=True,
                )
            )

        if booking_status == BookingStatus.CONFIRMED.value:
            actions.append(
                RecommendedAction(
                    action="resend_confirmation",
                    reason="Can resend booking confirmation email",
                    allowed=True,
                )
            )

        scheduled_end = booking.booking_end_utc
        if scheduled_end is None and booking.booking_start_utc and booking.duration_minutes:
            scheduled_end = _ensure_utc(booking.booking_start_utc) + timedelta(
                minutes=int(booking.duration_minutes)
            )
        if (
            booking_status == BookingStatus.CONFIRMED.value
            and scheduled_end is not None
            and _ensure_utc(scheduled_end) < datetime.now(timezone.utc)
        ):
            actions.append(
                RecommendedAction(
                    action="force_complete",
                    reason="Lesson time has passed, can mark complete",
                    allowed=True,
                )
            )

        actions.append(
            RecommendedAction(
                action="contact_instructor",
                reason="Reach out to instructor about this booking",
                allowed=True,
            )
        )

        return actions
