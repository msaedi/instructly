"""Service layer for admin booking and payments endpoints."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import logging
import math
import os
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.exceptions import ServiceException
from app.models.audit_log import AuditLog
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.payment import PaymentEvent, PaymentIntent
from app.models.user import User
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_bookings import (
    AdminAuditActor,
    AdminAuditEntry,
    AdminAuditLogResponse,
    AdminAuditLogSummary,
    AdminBookingDetailResponse,
    AdminBookingListItem,
    AdminBookingListResponse,
    AdminBookingPaymentInfo,
    AdminBookingPerson,
    AdminBookingServiceInfo,
    AdminBookingStatsNeedsAction,
    AdminBookingStatsResponse,
    AdminBookingStatsToday,
    AdminBookingStatsWeek,
    AdminBookingTimelineEvent,
)
from app.services.audit_redaction import redact
from app.services.base import BaseService
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService

logger = logging.getLogger(__name__)

AUDIT_ENABLED = os.getenv("AUDIT_ENABLED", "true").lower() in {"1", "true", "yes"}

PAYMENT_EVENT_TO_TIMELINE = {
    "auth_succeeded": "payment_authorized",
    "auth_retry_succeeded": "payment_authorized",
    "auth_succeeded_credits_only": "payment_authorized",
    "payment_captured": "payment_captured",
}

PAYMENT_CAPTURE_EVENT_TYPES = {"payment_captured"}


class AdminBookingService(BaseService):
    """Admin booking query and workflow helpers."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.booking_repo = RepositoryFactory.create_booking_repository(db)
        self.payment_repo = RepositoryFactory.create_payment_repository(db)
        self.audit_repo = RepositoryFactory.create_audit_repository(db)
        self.user_repo = RepositoryFactory.create_user_repository(db)

    @BaseService.measure_operation("admin_bookings.list")
    def list_bookings(
        self,
        *,
        search: Optional[str],
        statuses: Optional[Sequence[str]],
        payment_statuses: Optional[Sequence[str]],
        date_from: Optional[date],
        date_to: Optional[date],
        needs_action: Optional[bool],
        page: int,
        per_page: int,
    ) -> AdminBookingListResponse:
        now = datetime.now(timezone.utc) if needs_action else None
        bookings, total = self.booking_repo.list_admin_bookings(
            search=search,
            statuses=statuses,
            payment_statuses=payment_statuses,
            date_from=date_from,
            date_to=date_to,
            needs_action=needs_action,
            now=now,
            page=page,
            per_page=per_page,
        )

        items = [self._build_booking_list_item(booking) for booking in bookings]
        total_pages = max(1, math.ceil(total / per_page)) if per_page else 1

        return AdminBookingListResponse(
            bookings=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    @BaseService.measure_operation("admin_bookings.detail")
    def get_booking_detail(self, booking_id: str) -> Optional[AdminBookingDetailResponse]:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            return None

        student = booking.student
        instructor = booking.instructor

        payment_intent = self._resolve_payment_intent(booking)
        payment_events = self._resolve_payment_events(booking.id)

        credits_applied_cents = self._resolve_credit_applied_cents(payment_events)
        payment_info = self._build_payment_info(booking, payment_intent, credits_applied_cents)
        timeline = self._build_timeline(booking, payment_events)

        service_info = AdminBookingServiceInfo(
            id=getattr(booking, "instructor_service_id", None),
            name=booking.service_name,
            duration_minutes=booking.duration_minutes,
            hourly_rate=self._to_float(booking.hourly_rate),
        )

        return AdminBookingDetailResponse(
            id=booking.id,
            student=self._build_person(student, include_phone=True),
            instructor=self._build_person(instructor, include_phone=True),
            service=service_info,
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            booking_start_utc=getattr(booking, "booking_start_utc", None),
            booking_end_utc=getattr(booking, "booking_end_utc", None),
            lesson_timezone=getattr(booking, "lesson_timezone", None),
            instructor_timezone=getattr(booking, "instructor_tz_at_booking", None),
            student_timezone=getattr(booking, "student_tz_at_booking", None),
            location_type=booking.location_type,
            meeting_location=booking.meeting_location,
            student_note=booking.student_note,
            instructor_note=booking.instructor_note,
            status=self._status_value(booking.status),
            payment=payment_info,
            timeline=timeline,
            created_at=booking.created_at,
            updated_at=booking.updated_at,
        )

    @BaseService.measure_operation("admin_bookings.stats")
    def get_booking_stats(self) -> AdminBookingStatsResponse:
        now = datetime.now(timezone.utc)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        today_count = self._count_bookings_for_range(today, today)
        today_revenue = self._sum_booking_total(today, today)

        week_gmv = self._sum_booking_total(week_start, week_end)
        week_platform_revenue = self._sum_platform_fee_cents(week_start, week_end) / 100.0

        pending_completion = self._count_pending_completion(now)

        return AdminBookingStatsResponse(
            today=AdminBookingStatsToday(
                booking_count=today_count,
                revenue=today_revenue,
            ),
            this_week=AdminBookingStatsWeek(
                gmv=week_gmv,
                platform_revenue=week_platform_revenue,
            ),
            needs_action=AdminBookingStatsNeedsAction(
                pending_completion=pending_completion,
                disputed=0,
            ),
        )

    @BaseService.measure_operation("admin_bookings.audit_log")
    def list_audit_log(
        self,
        *,
        actions: Optional[Sequence[str]],
        admin_id: Optional[str],
        date_from: Optional[date],
        date_to: Optional[date],
        page: int,
        per_page: int,
    ) -> AdminAuditLogResponse:
        requested_actions = {action for action in (actions or []) if action}
        if not requested_actions:
            requested_actions = {
                "admin_refund",
                "admin_cancel",
                "status_change",
                "payment_capture",
            }

        include_captures = "payment_capture" in requested_actions
        audit_actions = sorted(
            action for action in requested_actions if action != "payment_capture"
        )

        fetch_limit = max(1, page * per_page)

        if audit_actions:
            audit_entries, audit_total = self._fetch_audit_entries(
                actions=audit_actions,
                admin_id=admin_id,
                date_from=date_from,
                date_to=date_to,
                limit=fetch_limit,
            )
        else:
            audit_entries, audit_total = [], 0
        capture_entries, capture_total = self._fetch_capture_entries(
            include=include_captures,
            admin_id=admin_id,
            date_from=date_from,
            date_to=date_to,
            limit=fetch_limit,
        )

        combined = audit_entries + capture_entries
        combined.sort(key=lambda entry: entry.timestamp, reverse=True)

        offset = max(0, (page - 1) * per_page)
        page_entries = combined[offset : offset + per_page]

        total = audit_total + capture_total
        total_pages = max(1, math.ceil(total / per_page)) if per_page else 1

        summary = self._build_audit_summary(
            admin_id=admin_id,
            date_from=date_from,
            date_to=date_to,
        )

        return AdminAuditLogResponse(
            entries=page_entries,
            summary=summary,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    @BaseService.measure_operation("admin_bookings.cancel")
    def cancel_booking(
        self,
        *,
        booking_id: str,
        reason: str,
        note: Optional[str],
        refund: bool,
        actor: User,
    ) -> tuple[Optional[Booking], Optional[str]]:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            return None, None

        if self._status_value(booking.status) != BookingStatus.CONFIRMED.value:
            raise ServiceException("Booking cannot be cancelled in its current status")

        refund_id: Optional[str] = None
        amount_cents: Optional[int] = None

        if refund:
            if not booking.payment_intent_id:
                raise ServiceException("Booking has no payment to refund", code="invalid_request")
            if (
                booking.refunded_to_card_amount
                and booking.refunded_to_card_amount > 0
                or (booking.settlement_outcome or "")
                in {
                    "admin_refund",
                    "instructor_cancel_full_refund",
                    "instructor_no_show_full_refund",
                    "student_wins_dispute_full_refund",
                }
            ):
                raise ServiceException("Booking already refunded", code="invalid_request")
            amount_cents = self._resolve_full_refund_cents(booking)
            if amount_cents <= 0:
                raise ServiceException(
                    "Unable to determine refundable amount", code="invalid_request"
                )

            stripe_result = self._issue_refund(
                booking=booking,
                amount_cents=amount_cents,
                reason=reason,
            )
            refund_id = stripe_result.get("refund_id")

        with self.transaction():
            booking = self.booking_repo.get_booking_with_details(booking_id)
            if not booking:
                return None, refund_id

            audit_before = redact(booking.to_dict()) or {}
            audit_before["payment_status"] = booking.payment_status

            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = datetime.now(timezone.utc)
            booking.cancelled_by_id = actor.id
            booking.cancellation_reason = reason

            try:
                from app.services.credit_service import CreditService

                credit_service = CreditService(self.db)
                credit_service.release_credits_for_booking(
                    booking_id=booking.id, use_transaction=False
                )
                booking.credits_reserved_cents = 0
            except Exception as exc:
                logger.warning(
                    "Failed to release reserved credits for booking %s: %s",
                    booking.id,
                    exc,
                )

            if refund:
                booking.payment_status = PaymentStatus.SETTLED.value
                booking.settlement_outcome = "admin_refund"
                if amount_cents is not None:
                    booking.refunded_to_card_amount = amount_cents

            audit_after = redact(booking.to_dict()) or {}
            audit_after["payment_status"] = booking.payment_status
            audit_after["admin_cancel"] = {
                "reason": reason,
                "note": note,
                "refund": refund,
                "refund_id": refund_id,
                "amount_cents": amount_cents,
            }

            if refund and amount_cents is not None:
                audit_after["refund"] = {
                    "reason": reason,
                    "note": note,
                    "amount_cents": amount_cents,
                    "refund_id": refund_id,
                    "stripe_reason": self._stripe_reason_for_cancel(reason),
                }

            if AUDIT_ENABLED:
                cancel_entry = AuditLog.from_change(
                    entity_type="booking",
                    entity_id=booking.id,
                    action="admin_cancel",
                    actor={"id": actor.id, "role": "admin"},
                    before=audit_before,
                    after=audit_after,
                )
                self.audit_repo.write(cancel_entry)

                if refund and amount_cents is not None:
                    refund_entry = AuditLog.from_change(
                        entity_type="booking",
                        entity_id=booking.id,
                        action="admin_refund",
                        actor={"id": actor.id, "role": "admin"},
                        before=audit_before,
                        after=audit_after,
                    )
                    self.audit_repo.write(refund_entry)

            return booking, refund_id

    @BaseService.measure_operation("admin_bookings.status_update")
    def update_booking_status(
        self,
        *,
        booking_id: str,
        status: BookingStatus,
        note: Optional[str],
        actor: User,
    ) -> Optional[Booking]:
        with self.transaction():
            booking = self.booking_repo.get_booking_with_details(booking_id)
            if not booking:
                return None

            if self._status_value(booking.status) != BookingStatus.CONFIRMED.value:
                raise ServiceException(
                    "Booking cannot be updated in its current status",
                    code="invalid_request",
                )

            audit_before = redact(booking.to_dict()) or {}
            audit_before["payment_status"] = booking.payment_status
            previous_status = self._status_value(booking.status)

            if status == BookingStatus.COMPLETED:
                booking.complete()
            elif status == BookingStatus.NO_SHOW:
                booking.mark_no_show()
            else:
                raise ServiceException("Unsupported status update", code="invalid_request")

            audit_after = redact(booking.to_dict()) or {}
            audit_after["payment_status"] = booking.payment_status
            audit_after["status_change"] = {
                "from": previous_status,
                "to": status.value,
                "note": note,
            }

            if AUDIT_ENABLED:
                entry = AuditLog.from_change(
                    entity_type="booking",
                    entity_id=booking.id,
                    action="status_change",
                    actor={"id": actor.id, "role": "admin"},
                    before=audit_before,
                    after=audit_after,
                )
                self.audit_repo.write(entry)

            return booking

    def _build_booking_list_item(self, booking: Booking) -> AdminBookingListItem:
        return AdminBookingListItem(
            id=booking.id,
            student=self._build_person(booking.student, include_phone=False),
            instructor=self._build_person(booking.instructor, include_phone=False),
            service_name=booking.service_name,
            booking_date=booking.booking_date,
            start_time=booking.start_time,
            end_time=booking.end_time,
            booking_start_utc=getattr(booking, "booking_start_utc", None),
            booking_end_utc=getattr(booking, "booking_end_utc", None),
            lesson_timezone=getattr(booking, "lesson_timezone", None),
            instructor_timezone=getattr(booking, "instructor_tz_at_booking", None),
            student_timezone=getattr(booking, "student_tz_at_booking", None),
            total_price=self._to_float(booking.total_price),
            status=self._status_value(booking.status),
            payment_status=booking.payment_status,
            payment_intent_id=booking.payment_intent_id,
            created_at=booking.created_at,
        )

    def _build_payment_info(
        self,
        booking: Booking,
        payment_intent: Optional[PaymentIntent],
        credits_applied_cents: int,
    ) -> AdminBookingPaymentInfo:
        total_price = self._to_float(booking.total_price)
        lesson_price_cents = self._resolve_lesson_price_cents(booking, payment_intent)
        platform_fee_cents = self._resolve_platform_fee_cents(payment_intent)
        instructor_payout_cents = self._resolve_instructor_payout_cents(
            payment_intent, platform_fee_cents
        )
        platform_revenue_cents = platform_fee_cents

        stripe_url = None
        if booking.payment_intent_id:
            stripe_url = f"https://dashboard.stripe.com/payments/{booking.payment_intent_id}"

        return AdminBookingPaymentInfo(
            total_price=total_price,
            lesson_price=lesson_price_cents / 100.0,
            platform_fee=platform_fee_cents / 100.0,
            credits_applied=credits_applied_cents / 100.0,
            payment_status=booking.payment_status,
            payment_intent_id=booking.payment_intent_id,
            instructor_payout=instructor_payout_cents / 100.0,
            platform_revenue=platform_revenue_cents / 100.0,
            stripe_url=stripe_url,
        )

    def _build_timeline(
        self,
        booking: Booking,
        payment_events: Sequence[PaymentEvent],
    ) -> list[AdminBookingTimelineEvent]:
        events: list[AdminBookingTimelineEvent] = []

        if booking.created_at:
            events.append(
                AdminBookingTimelineEvent(
                    timestamp=booking.created_at,
                    event="booking_created",
                )
            )

        if booking.completed_at:
            events.append(
                AdminBookingTimelineEvent(
                    timestamp=booking.completed_at,
                    event="lesson_completed",
                )
            )

        if booking.cancelled_at:
            events.append(
                AdminBookingTimelineEvent(
                    timestamp=booking.cancelled_at,
                    event="booking_cancelled",
                )
            )

        if self._status_value(booking.status) == BookingStatus.NO_SHOW.value:
            fallback_time = booking.updated_at or booking.created_at or datetime.now(timezone.utc)
            events.append(
                AdminBookingTimelineEvent(
                    timestamp=fallback_time,
                    event="lesson_no_show",
                )
            )

        for event in payment_events:
            timeline_event = PAYMENT_EVENT_TO_TIMELINE.get(event.event_type)
            if not timeline_event:
                continue
            amount = self._resolve_payment_event_amount(event)
            events.append(
                AdminBookingTimelineEvent(
                    timestamp=event.created_at,
                    event=timeline_event,
                    amount=amount,
                )
            )

        events.sort(key=lambda item: item.timestamp)
        return events

    def _resolve_payment_event_amount(self, event: PaymentEvent) -> Optional[float]:
        data = event.event_data or {}
        if event.event_type == "payment_captured":
            cents = self._extract_cents(
                data, ("amount_captured_cents", "amount_received", "amount")
            )
            return cents / 100.0 if cents is not None else None
        cents = self._extract_cents(data, ("amount_cents", "student_pay_cents", "amount"))
        return cents / 100.0 if cents is not None else None

    def _resolve_payment_intent(self, booking: Booking) -> Optional[PaymentIntent]:
        if not booking.payment_intent_id:
            return None
        try:
            return self.payment_repo.get_payment_by_intent_id(booking.payment_intent_id)
        except Exception:
            return None

    def _resolve_payment_events(self, booking_id: str) -> Sequence[PaymentEvent]:
        try:
            return self.payment_repo.get_payment_events_for_booking(booking_id)
        except Exception:
            return []

    def _resolve_credit_applied_cents(self, events: Sequence[PaymentEvent]) -> int:
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

    def _resolve_lesson_price_cents(
        self,
        booking: Booking,
        payment_intent: Optional[PaymentIntent],
    ) -> int:
        if payment_intent and payment_intent.base_price_cents:
            return int(payment_intent.base_price_cents)

        if booking.hourly_rate and booking.duration_minutes:
            try:
                hourly_rate = Decimal(str(booking.hourly_rate))
                minutes = Decimal(str(booking.duration_minutes))
                lesson_price = hourly_rate * minutes / Decimal(60)
                return int((lesson_price * 100).quantize(Decimal("1")))
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
        total_price = self._to_float(booking.total_price)
        return int(total_price * 100)

    def _resolve_platform_fee_cents(self, payment_intent: Optional[PaymentIntent]) -> int:
        if payment_intent and payment_intent.application_fee is not None:
            return int(payment_intent.application_fee)
        return 0

    def _resolve_instructor_payout_cents(
        self,
        payment_intent: Optional[PaymentIntent],
        platform_fee_cents: int,
    ) -> int:
        if payment_intent and payment_intent.instructor_payout_cents is not None:
            return int(payment_intent.instructor_payout_cents)
        if payment_intent and payment_intent.amount is not None:
            return max(0, int(payment_intent.amount) - platform_fee_cents)
        return 0

    def _resolve_full_refund_cents(self, booking: Booking) -> int:
        payment_intent_id = booking.payment_intent_id
        if payment_intent_id:
            payment_record = self.payment_repo.get_payment_by_intent_id(payment_intent_id)
            if payment_record and payment_record.amount:
                return int(payment_record.amount)

        if booking.total_price is None:
            return 0

        total_price = Decimal(str(booking.total_price))
        return int(total_price * 100)

    def _stripe_reason_for_cancel(self, reason: str) -> str:
        if reason.strip().lower() == "dispute":
            return "duplicate"
        return "requested_by_customer"

    def _issue_refund(
        self,
        *,
        booking: Booking,
        amount_cents: int,
        reason: str,
    ) -> dict[str, Any]:
        stripe_service = StripeService(
            self.db,
            config_service=ConfigService(self.db),
            pricing_service=PricingService(self.db),
        )
        try:
            return stripe_service.refund_payment(
                payment_intent_id=booking.payment_intent_id,
                amount_cents=amount_cents,
                reason=self._stripe_reason_for_cancel(reason),
                reverse_transfer=True,
                idempotency_key=f"admin_cancel_{booking.id}_{amount_cents}",
            )
        except ServiceException:
            raise
        except Exception as exc:
            raise ServiceException("Stripe refund failed", code="stripe_error") from exc

    def _fetch_audit_entries(
        self,
        *,
        actions: Sequence[str],
        admin_id: Optional[str],
        date_from: Optional[date],
        date_to: Optional[date],
        limit: int,
    ) -> tuple[list[AdminAuditEntry], int]:
        start_dt, end_dt = self._date_range_bounds(date_from, date_to)

        rows, total = self.audit_repo.list_for_booking_actions(
            actions=actions,
            actor_id=admin_id if admin_id and admin_id != "system" else None,
            start=start_dt,
            end=end_dt,
            limit=limit,
            offset=0,
        )

        actor_ids = {row.actor_id for row in rows if row.actor_id}
        users = self.user_repo.get_by_ids(list(actor_ids)) if actor_ids else []
        user_map = {user.id: user.email for user in users}

        entries = [
            self._build_audit_entry(
                entry=row,
                admin_email=user_map.get(row.actor_id or "", "system"),
            )
            for row in rows
        ]
        return entries, total

    def _fetch_capture_entries(
        self,
        *,
        include: bool,
        admin_id: Optional[str],
        date_from: Optional[date],
        date_to: Optional[date],
        limit: int,
    ) -> tuple[list[AdminAuditEntry], int]:
        if not include:
            return [], 0

        if admin_id and admin_id != "system":
            return [], 0

        start_dt, end_dt = self._date_range_bounds(date_from, date_to)

        rows = self.payment_repo.list_payment_events_by_types(
            list(PAYMENT_CAPTURE_EVENT_TYPES),
            start=start_dt,
            end=end_dt,
            limit=limit,
            offset=0,
            desc=True,
        )
        total = self.payment_repo.count_payment_events_by_types(
            list(PAYMENT_CAPTURE_EVENT_TYPES),
            start=start_dt,
            end=end_dt,
        )

        entries = [
            AdminAuditEntry(
                id=row.id,
                timestamp=row.created_at,
                admin=AdminAuditActor(id="system", email="system"),
                action="payment_capture",
                resource_type="booking",
                resource_id=row.booking_id,
                details=self._build_capture_details(row),
            )
            for row in rows
        ]

        return entries, total

    def _build_audit_summary(
        self,
        *,
        admin_id: Optional[str],
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> AdminAuditLogSummary:
        start_dt, end_dt = self._date_range_bounds(date_from, date_to)

        refund_entries, _ = self.audit_repo.list_for_booking_actions(
            actions=["admin_refund"],
            actor_id=admin_id if admin_id and admin_id != "system" else None,
            start=start_dt,
            end=end_dt,
            limit=None,
            offset=0,
        )
        refund_count = len(refund_entries)
        refund_total_cents = 0
        for entry in refund_entries:
            details = self._extract_audit_details(entry) or {}
            amount_cents = details.get("amount_cents")
            if isinstance(amount_cents, (int, float)):
                refund_total_cents += int(amount_cents)

        capture_entries: Sequence[PaymentEvent]
        if admin_id and admin_id != "system":
            capture_entries = []
        else:
            capture_entries = self.payment_repo.list_payment_events_by_types(
                list(PAYMENT_CAPTURE_EVENT_TYPES),
                start=start_dt,
                end=end_dt,
                limit=None,
                offset=0,
                desc=False,
            )
        capture_count = len(capture_entries)
        capture_total_cents = 0
        for payment_event in capture_entries:
            data = payment_event.event_data or {}
            amount_cents = self._extract_cents(
                data, ("amount_captured_cents", "amount_received", "amount")
            )
            if amount_cents is not None:
                capture_total_cents += amount_cents

        return AdminAuditLogSummary(
            refunds_count=refund_count,
            refunds_total=refund_total_cents / 100.0,
            captures_count=capture_count,
            captures_total=capture_total_cents / 100.0,
        )

    def _build_audit_entry(self, entry: AuditLog, admin_email: str) -> AdminAuditEntry:
        actor_id = entry.actor_id or "system"
        return AdminAuditEntry(
            id=entry.id,
            timestamp=entry.occurred_at,
            admin=AdminAuditActor(
                id=actor_id,
                email=admin_email if actor_id != "system" else "system",
            ),
            action=entry.action,
            resource_type=entry.entity_type,
            resource_id=entry.entity_id,
            details=self._extract_audit_details(entry),
        )

    def _extract_audit_details(self, entry: AuditLog) -> Optional[dict[str, Any]]:
        after = entry.after or {}
        if entry.action == "admin_refund":
            return after.get("refund") or after.get("admin_refund") or None
        if entry.action == "admin_cancel":
            return after.get("admin_cancel") or None
        if entry.action == "status_change":
            return after.get("status_change") or None
        return None

    def _build_capture_details(self, event: PaymentEvent) -> dict[str, Any]:
        data = event.event_data or {}
        amount_cents = self._extract_cents(
            data, ("amount_captured_cents", "amount_received", "amount")
        )
        return {
            "amount_cents": amount_cents,
            "captured_at": data.get("captured_at"),
        }

    def _count_bookings_for_range(self, start: date, end: date) -> int:
        return self.booking_repo.count_bookings_in_date_range(start, end)

    def _sum_booking_total(self, start: date, end: date) -> float:
        total = self.booking_repo.sum_total_price_in_date_range(start, end)
        return self._to_float(total)

    def _sum_platform_fee_cents(self, start: date, end: date) -> int:
        return self.payment_repo.sum_application_fee_for_booking_date_range(start, end)

    def _count_pending_completion(self, now: datetime) -> int:
        return self.booking_repo.count_pending_completion(now)

    def _build_person(self, user: Optional[User], *, include_phone: bool) -> AdminBookingPerson:
        if not user:
            return AdminBookingPerson(id="", name="Unknown", email="")
        name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
        phone = user.phone if include_phone else None
        return AdminBookingPerson(id=user.id, name=name, email=user.email, phone=phone)

    def _status_value(self, status: Any) -> str:
        value = getattr(status, "value", None)
        return str(value) if value is not None else str(status)

    def _to_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        try:
            return float(Decimal(str(value)))
        except Exception:
            return 0.0

    def _extract_cents(self, data: dict[str, Any], keys: Iterable[str]) -> Optional[int]:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
                continue
        return None

    def _date_range_bounds(
        self,
        start: Optional[date],
        end: Optional[date],
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        start_dt = None
        end_dt = None
        if start:
            start_dt = datetime.combine(  # tz-pattern-ok: date range bounds only
                start, time.min, tzinfo=timezone.utc
            )
        if end:
            end_dt = datetime.combine(  # tz-pattern-ok: date range bounds only
                end, time.max, tzinfo=timezone.utc
            )
        return start_dt, end_dt
