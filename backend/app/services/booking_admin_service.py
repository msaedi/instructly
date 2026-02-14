"""Admin booking actions for MCP workflows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictException,
    MCPTokenError,
    NotFoundException,
    ValidationException,
)
from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.payment import PaymentIntent
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_booking_actions import (
    AddNoteResponse,
    BookingState,
    ForceCancelExecuteResponse,
    ForceCancelPreviewResponse,
    ForceCompleteExecuteResponse,
    ForceCompletePreviewResponse,
    NotificationRecipient,
    NotificationSent,
    NotificationType,
    RefundPreference,
    ResendNotificationResponse,
)
from app.services.audit_service import AuditService
from app.services.base import BaseService
from app.services.booking_service import BookingService
from app.services.config_service import ConfigService
from app.services.credit_service import CreditService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.notification_service import NotificationService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService
from app.services.system_message_service import SystemMessageService

logger = logging.getLogger(__name__)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cents_to_decimal(cents: int | None) -> Decimal:
    if cents is None:
        return Decimal("0.00")
    return (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))


class BookingAdminService(BaseService):
    """Admin booking actions with preview/execute guardrails."""

    CONFIRM_TOKEN_TTL = timedelta(minutes=5)

    def __init__(
        self,
        db: Session,
        *,
        booking_service: BookingService | None = None,
        confirm_service: MCPConfirmTokenService | None = None,
        idempotency_service: MCPIdempotencyService | None = None,
        stripe_service: StripeService | None = None,
        credit_service: CreditService | None = None,
        notification_service: NotificationService | None = None,
        audit_service: AuditService | None = None,
        system_message_service: SystemMessageService | None = None,
    ) -> None:
        super().__init__(db)
        self.booking_repo = RepositoryFactory.create_booking_repository(db)
        self.booking_note_repo = RepositoryFactory.create_booking_note_repository(db)
        self.payment_repo = RepositoryFactory.create_payment_repository(db)
        self.user_repo = RepositoryFactory.create_user_repository(db)
        self.confirm_service = confirm_service or MCPConfirmTokenService(db)
        self.idempotency_service = idempotency_service or MCPIdempotencyService(db)
        if stripe_service is None:
            config_service = ConfigService(db)
            pricing_service = PricingService(db)
            stripe_service = StripeService(
                db,
                config_service=config_service,
                pricing_service=pricing_service,
            )
        self.stripe_service = stripe_service
        self.credit_service = credit_service or CreditService(db)
        self.notification_service = notification_service or NotificationService(db)
        self.audit_service = audit_service or AuditService(db)
        self.system_message_service = system_message_service or SystemMessageService(db)
        self.booking_service = booking_service or BookingService(
            db,
            notification_service=self.notification_service,
        )

    @BaseService.measure_operation("mcp_booking_actions.preview_force_cancel")
    def preview_force_cancel(
        self,
        *,
        booking_id: str,
        reason_code: str,
        note: str,
        refund_preference: RefundPreference,
        actor_id: str,
    ) -> ForceCancelPreviewResponse:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found", code="BOOKING_NOT_FOUND")

        pd = booking.payment_detail
        current_state = BookingState(
            status=self._status_value(booking.status),
            payment_status=pd.payment_status if pd is not None else None,
        )

        eligible = True
        ineligible_reason = None

        if self._status_value(booking.status) == BookingStatus.CANCELLED.value:
            eligible = False
            ineligible_reason = "Booking already cancelled"
        elif self._status_value(booking.status) != BookingStatus.CONFIRMED.value:
            eligible = False
            ineligible_reason = "Booking not in confirmed status"

        payment = self._resolve_payment(booking)
        amounts = self._resolve_amounts(booking, payment)
        full_amount_cents = amounts["full_amount_cents"]
        lesson_price_cents = amounts["lesson_price_cents"]

        warnings: list[str] = []

        refund_method = None
        refund_amount_cents: int | None = None

        if eligible:
            if refund_preference == RefundPreference.NO_REFUND:
                refund_method = "none"
                refund_amount_cents = None
                warnings.append("No refund will be issued")
            elif full_amount_cents <= 0:
                eligible = False
                ineligible_reason = "Booking has no payment to refund"
            else:
                refund_method, refund_amount_cents = self._evaluate_cancel_refund(
                    booking,
                    reason_code=reason_code,
                    refund_preference=refund_preference,
                    full_amount_cents=full_amount_cents,
                    lesson_price_cents=lesson_price_cents,
                )

        if (
            eligible
            and refund_preference == RefundPreference.POLICY_BASED
            and booking.booking_start_utc is None
        ):
            eligible = False
            ineligible_reason = "Booking start time unavailable for policy evaluation"

        pd_status = (pd.payment_status if pd is not None else None) or ""
        payment_status = pd_status.lower()
        if payment_status == PaymentStatus.SETTLED.value:
            warnings.append("Instructor already paid out - may trigger clawback")

        impacts = self._compute_impacts(
            booking,
            payment,
            refund_method,
            refund_amount_cents,
        )

        confirm_token = None
        idempotency_key = None

        if eligible:
            idempotency_key = str(uuid4())
            payload = {
                "booking_id": booking_id,
                "reason_code": reason_code,
                "refund_preference": refund_preference.value,
                "refund_method": refund_method,
                "refund_amount_cents": refund_amount_cents,
                "note": note,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
            }
            confirm_token, _expires_at = self.confirm_service.generate_token(
                payload,
                actor_id=actor_id,
                ttl_minutes=int(self.CONFIRM_TOKEN_TTL.total_seconds() / 60),
            )

        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="BOOKING_FORCE_CANCEL_PREVIEW",
            resource_type="booking",
            resource_id=booking_id,
            metadata={
                "reason_code": reason_code,
                "refund_preference": refund_preference.value,
                "eligible": eligible,
            },
        )

        return ForceCancelPreviewResponse(
            eligible=eligible,
            ineligible_reason=ineligible_reason,
            current_state=current_state,
            will_cancel_booking=eligible,
            will_refund=bool(eligible and refund_method and refund_method != "none"),
            refund_method=refund_method,
            refund_amount=_cents_to_decimal(refund_amount_cents)
            if refund_amount_cents is not None
            else None,
            will_notify_student=True if eligible else False,
            will_notify_instructor=True if eligible else False,
            instructor_payout_impact=impacts["instructor_payout_impact"],
            platform_fee_impact=impacts["platform_fee_impact"],
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    @BaseService.measure_operation("mcp_booking_actions.execute_force_cancel")
    async def execute_force_cancel(
        self,
        *,
        booking_id: str,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> ForceCancelExecuteResponse:
        try:
            token_data = self.confirm_service.decode_token(confirm_token)
        except MCPTokenError:
            raise

        payload = token_data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationException("Invalid confirm token payload")

        try:
            self.confirm_service.validate_token(confirm_token, payload, actor_id=actor_id)
        except MCPTokenError:
            raise

        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        token_booking_id = str(payload.get("booking_id"))
        if booking_id and token_booking_id != booking_id:
            raise ValidationException("Booking ID mismatch", code="BOOKING_MISMATCH")

        try:
            already_done, cached = await self.idempotency_service.check_and_store(
                idempotency_key, operation="mcp_booking.force_cancel"
            )
        except Exception as exc:
            logger.error("Force cancel idempotency check failed", exc_info=exc)
            raise

        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return ForceCancelExecuteResponse.model_validate(cached)

        booking = await asyncio.to_thread(
            self.booking_repo.get_booking_with_details, token_booking_id
        )
        if not booking:
            raise NotFoundException(
                f"Booking {token_booking_id} not found", code="BOOKING_NOT_FOUND"
            )

        previous_status = self._status_value(booking.status)
        if previous_status == BookingStatus.CANCELLED.value:
            raise ValidationException("Booking already cancelled", code="BOOKING_ALREADY_CANCELLED")

        refund_preference = RefundPreference(str(payload.get("refund_preference")))
        reason_code = str(payload.get("reason_code"))
        refund_method = payload.get("refund_method")
        refund_amount_cents = payload.get("refund_amount_cents")
        note = payload.get("note")

        refund_id: str | None = None
        refund_issued = False
        error: str | None = None
        send_admin_notifications = True

        if refund_preference == RefundPreference.POLICY_BASED and reason_code not in {
            "INSTRUCTOR_NO_SHOW",
            "DUPLICATE_BOOKING",
        }:
            # Use standard cancellation policy via BookingService (student-style).
            proxy_user = booking.student
            if proxy_user is None:
                raise ValidationException("Booking missing student data")
            try:
                self.booking_service.cancel_booking(
                    booking_id=token_booking_id,
                    user=proxy_user,
                    reason=reason_code,
                )
                send_admin_notifications = False
            except Exception as exc:
                logger.error("Policy-based cancellation failed", exc_info=exc)
                raise
            booking = (
                await asyncio.to_thread(
                    self.booking_repo.get_booking_with_details, token_booking_id
                )
            ) or booking
            refund_issued = bool(refund_method and refund_method != "none")
        elif refund_preference == RefundPreference.NO_REFUND:
            try:
                refund_issued = False
                self._cancel_without_refund(booking, reason_code=reason_code)
            except Exception as exc:
                logger.error("No-refund cancellation failed", exc_info=exc)
                error = "cancel_no_refund_failed"
        else:
            try:
                refund_id, refund_issued = self._cancel_with_full_refund(
                    booking,
                    reason_code=reason_code,
                    idempotency_key=idempotency_key,
                )
            except Exception as exc:
                logger.error("Full refund cancellation failed", exc_info=exc)
                error = "cancel_refund_failed"

        booking = (
            await asyncio.to_thread(self.booking_repo.get_booking_with_details, token_booking_id)
        ) or booking

        notifications_sent = ["student_email", "instructor_email"]
        if send_admin_notifications:
            self._send_admin_cancellation_notifications(booking)
            self._log_cancellation_message(booking)

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="BOOKING_FORCE_CANCEL_EXECUTE",
            resource_type="booking",
            resource_id=token_booking_id,
            metadata={
                "reason_code": reason_code,
                "refund_preference": refund_preference.value,
                "refund_method": refund_method,
                "refund_amount_cents": refund_amount_cents,
                "note": note,
                "idempotency_key": idempotency_key,
            },
            status="failed" if error else "success",
            error_message=error,
        )

        response = ForceCancelExecuteResponse(
            success=error is None,
            error=error,
            booking_id=token_booking_id,
            previous_status=previous_status,
            new_status=self._status_value(booking.status),
            refund_issued=refund_issued,
            refund_id=refund_id,
            refund_amount=_cents_to_decimal(refund_amount_cents)
            if refund_amount_cents is not None
            else None,
            refund_method=str(refund_method) if refund_method else None,
            notifications_sent=notifications_sent,
            audit_id=audit_id,
        )

        await self.idempotency_service.store_result(
            idempotency_key, response.model_dump(mode="json")
        )

        return response

    @BaseService.measure_operation("mcp_booking_actions.preview_force_complete")
    def preview_force_complete(
        self,
        *,
        booking_id: str,
        reason_code: str,
        note: str,
        actor_id: str,
    ) -> ForceCompletePreviewResponse:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found", code="BOOKING_NOT_FOUND")

        pd = booking.payment_detail
        pd_payment_status = pd.payment_status if pd is not None else None
        current_state = BookingState(
            status=self._status_value(booking.status),
            payment_status=pd_payment_status,
        )

        eligible = True
        ineligible_reason = None
        if self._status_value(booking.status) != BookingStatus.CONFIRMED.value:
            eligible = False
            ineligible_reason = "Booking not in confirmed status"
        elif (pd_payment_status or "") not in {
            PaymentStatus.AUTHORIZED.value,
            PaymentStatus.SETTLED.value,
            "captured",
        }:
            eligible = False
            ineligible_reason = "Booking payment not in a capture-ready state"

        payment = self._resolve_payment(booking)
        amounts = self._resolve_amounts(booking, payment)

        lesson_time_passed = False
        hours_since_scheduled: float | None = None
        warnings: list[str] = []

        if booking.booking_end_utc:
            scheduled_end = _ensure_utc(booking.booking_end_utc)
        elif booking.booking_start_utc and booking.duration_minutes:
            scheduled_end = _ensure_utc(booking.booking_start_utc) + timedelta(
                minutes=int(booking.duration_minutes)
            )
        else:
            scheduled_end = None

        now = datetime.now(timezone.utc)
        if scheduled_end is not None:
            lesson_time_passed = scheduled_end <= now
            delta_hours = (now - scheduled_end).total_seconds() / 3600
            hours_since_scheduled = max(delta_hours, 0.0)
            if not lesson_time_passed:
                warnings.append("Lesson scheduled for future - verify it actually occurred")
            elif delta_hours > 24 * 7:
                warnings.append("Lesson was over 7 days ago - delayed completion")
        else:
            warnings.append("Lesson time not available; verify completion timing")

        confirm_token = None
        idempotency_key = None

        if eligible:
            idempotency_key = str(uuid4())
            payload = {
                "booking_id": booking_id,
                "reason_code": reason_code,
                "note": note,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
            }
            confirm_token, _expires_at = self.confirm_service.generate_token(
                payload,
                actor_id=actor_id,
                ttl_minutes=int(self.CONFIRM_TOKEN_TTL.total_seconds() / 60),
            )

        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="BOOKING_FORCE_COMPLETE_PREVIEW",
            resource_type="booking",
            resource_id=booking_id,
            metadata={"reason_code": reason_code, "eligible": eligible},
        )

        return ForceCompletePreviewResponse(
            eligible=eligible,
            ineligible_reason=ineligible_reason,
            current_state=current_state,
            will_mark_complete=eligible,
            will_capture_payment=eligible
            and (pd_payment_status or "") == PaymentStatus.AUTHORIZED.value,
            capture_amount=_cents_to_decimal(amounts["full_amount_cents"]),
            instructor_payout=_cents_to_decimal(amounts["instructor_payout_cents"]),
            platform_fee=_cents_to_decimal(amounts["platform_fee_cents"]),
            lesson_time_passed=lesson_time_passed,
            hours_since_scheduled=hours_since_scheduled,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    @BaseService.measure_operation("mcp_booking_actions.execute_force_complete")
    async def execute_force_complete(
        self,
        *,
        booking_id: str,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> ForceCompleteExecuteResponse:
        try:
            token_data = self.confirm_service.decode_token(confirm_token)
        except MCPTokenError:
            raise

        payload = token_data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationException("Invalid confirm token payload")

        try:
            self.confirm_service.validate_token(confirm_token, payload, actor_id=actor_id)
        except MCPTokenError:
            raise

        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        token_booking_id = str(payload.get("booking_id"))
        if booking_id and token_booking_id != booking_id:
            raise ValidationException("Booking ID mismatch", code="BOOKING_MISMATCH")

        try:
            already_done, cached = await self.idempotency_service.check_and_store(
                idempotency_key, operation="mcp_booking.force_complete"
            )
        except Exception as exc:
            logger.error("Force complete idempotency check failed", exc_info=exc)
            raise

        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return ForceCompleteExecuteResponse.model_validate(cached)

        booking = await asyncio.to_thread(
            self.booking_repo.get_booking_with_details, token_booking_id
        )
        if not booking:
            raise NotFoundException(
                f"Booking {token_booking_id} not found", code="BOOKING_NOT_FOUND"
            )

        previous_status = self._status_value(booking.status)
        if previous_status != BookingStatus.CONFIRMED.value:
            raise ValidationException(
                "Booking not in confirmed status", code="BOOKING_NOT_CONFIRMED"
            )

        now = datetime.now(timezone.utc)
        completed_at = now
        if booking.booking_end_utc and _ensure_utc(booking.booking_end_utc) <= now:
            completed_at = _ensure_utc(booking.booking_end_utc)

        def _mark_completed() -> Booking:
            with self.transaction():
                booking = self.booking_repo.get_booking_with_details(token_booking_id)
                if not booking:
                    raise NotFoundException("Booking not found", code="BOOKING_NOT_FOUND")
                booking.status = BookingStatus.COMPLETED
                booking.completed_at = completed_at
                return booking

        booking = await asyncio.to_thread(_mark_completed)

        payment_captured = False
        capture_amount: Decimal | None = None
        pd = booking.payment_detail
        pd_payment_status = pd.payment_status if pd is not None else None
        if (pd_payment_status or "") == PaymentStatus.AUTHORIZED.value:
            try:
                from app.tasks.payment_tasks import _process_capture_for_booking

                capture_result = _process_capture_for_booking(booking.id, "admin_force_complete")
                payment_captured = bool(
                    capture_result.get("success") or capture_result.get("already_captured")
                )
                amount_received = capture_result.get("amount_received")
                if amount_received is not None:
                    try:
                        capture_amount = _cents_to_decimal(int(amount_received))
                    except (TypeError, ValueError):
                        capture_amount = None
            except Exception as exc:
                logger.error("Payment capture failed", exc_info=exc)

        booking = (
            await asyncio.to_thread(self.booking_repo.get_booking_with_details, token_booking_id)
        ) or booking
        payment = self._resolve_payment(booking)
        amounts = self._resolve_amounts(booking, payment)
        if capture_amount is None and amounts["full_amount_cents"]:
            capture_amount = _cents_to_decimal(amounts["full_amount_cents"])

        self._post_complete_actions(booking)

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="BOOKING_FORCE_COMPLETE_EXECUTE",
            resource_type="booking",
            resource_id=token_booking_id,
            metadata={
                "reason_code": payload.get("reason_code"),
                "note": payload.get("note"),
                "idempotency_key": idempotency_key,
            },
        )

        response = ForceCompleteExecuteResponse(
            success=True,
            booking_id=token_booking_id,
            previous_status=previous_status,
            new_status=BookingStatus.COMPLETED.value,
            payment_captured=payment_captured,
            capture_amount=capture_amount,
            instructor_payout_scheduled=payment_captured
            or (getattr(booking.payment_detail, "payment_status", None) or "")
            == PaymentStatus.SETTLED.value,
            payout_amount=_cents_to_decimal(amounts["instructor_payout_cents"]),
            audit_id=audit_id,
        )

        await self.idempotency_service.store_result(
            idempotency_key, response.model_dump(mode="json")
        )

        return response

    @BaseService.measure_operation("mcp_booking_actions.resend_notification")
    def resend_notification(
        self,
        *,
        booking_id: str,
        notification_type: NotificationType,
        recipient: NotificationRecipient,
        note: str,
        actor_id: str,
    ) -> ResendNotificationResponse:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found", code="BOOKING_NOT_FOUND")

        valid_states = self._valid_states_for_notification(notification_type)
        if valid_states and self._status_value(booking.status) not in valid_states:
            raise ValidationException(
                "Notification not valid for booking state", code="INVALID_NOTIFICATION_STATE"
            )

        sent: list[NotificationSent] = []
        errors: list[str] = []
        now = datetime.now(timezone.utc)

        def _record(recipient_label: str, template: str) -> None:
            sent.append(
                NotificationSent(
                    recipient=recipient_label,
                    channel="email",
                    template=template,
                    sent_at=now,
                )
            )

        targets = {recipient.value}
        if recipient == NotificationRecipient.BOTH:
            targets = {"student", "instructor"}

        try:
            if notification_type == NotificationType.BOOKING_CONFIRMATION:
                if "student" in targets:
                    self.notification_service._send_student_booking_confirmation(booking)
                    _record("student", "booking_confirmation_student")
                if "instructor" in targets:
                    self.notification_service._send_instructor_booking_notification(booking)
                    _record("instructor", "booking_confirmation_instructor")
            elif notification_type in {
                NotificationType.LESSON_REMINDER_24H,
                NotificationType.LESSON_REMINDER_1H,
            }:
                reminder_type = (
                    "24h" if notification_type == NotificationType.LESSON_REMINDER_24H else "1h"
                )
                if "student" in targets:
                    self.notification_service._send_student_reminder(
                        booking, reminder_type=reminder_type
                    )
                    _record("student", "booking_reminder_student")
                if "instructor" in targets:
                    self.notification_service._send_instructor_reminder(
                        booking, reminder_type=reminder_type
                    )
                    _record("instructor", "booking_reminder_instructor")
            elif notification_type == NotificationType.LESSON_COMPLETED:
                if "student" in targets:
                    self.notification_service._send_student_completion_notification(booking)
                    _record("student", "booking_completed_student")
                if "instructor" in targets:
                    self.notification_service._send_instructor_completion_notification(booking)
                    _record("instructor", "booking_completed_instructor")
            elif notification_type == NotificationType.CANCELLATION_NOTICE:
                if "student" in targets:
                    self.notification_service._send_student_cancellation_confirmation(booking)
                    _record("student", "booking_cancellation_confirmation_student")
                if "instructor" in targets:
                    self.notification_service._send_instructor_cancellation_confirmation(booking)
                    _record("instructor", "booking_cancellation_confirmation_instructor")
        except Exception as exc:
            logger.error("Resend notification failed", exc_info=exc)
            errors.append(str(exc))

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="BOOKING_RESEND_NOTIFICATION",
            resource_type="booking",
            resource_id=booking_id,
            metadata={
                "notification_type": notification_type.value,
                "recipient": recipient.value,
                "note": note,
                "sent": [s.model_dump() for s in sent],
            },
            status="failed" if errors else "success",
            error_message=errors[0] if errors else None,
        )

        return ResendNotificationResponse(
            success=not errors,
            error=errors[0] if errors else None,
            notifications_sent=sent,
            audit_id=audit_id,
        )

    @BaseService.measure_operation("mcp_booking_actions.add_note")
    def add_note(
        self,
        *,
        booking_id: str,
        note: str,
        visibility: str,
        category: str,
        actor_id: str,
        actor_type: str,
    ) -> AddNoteResponse:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found", code="BOOKING_NOT_FOUND")

        created_by_id = actor_id if actor_type == "user" else None

        with self.transaction():
            booking_note = self.booking_note_repo.create_note(
                booking_id=booking_id,
                created_by_id=created_by_id,
                note=note,
                visibility=visibility,
                category=category,
            )

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="BOOKING_NOTE_ADDED",
            resource_type="booking",
            resource_id=booking_id,
            metadata={
                "note_id": booking_note.id,
                "visibility": visibility,
                "category": category,
            },
        )

        return AddNoteResponse(
            success=True,
            note_id=booking_note.id,
            created_at=booking_note.created_at,
            audit_id=audit_id,
        )

    def _resolve_payment(self, booking: Booking) -> PaymentIntent | None:
        pd = booking.payment_detail
        pd_intent_id = pd.payment_intent_id if pd is not None else None
        if pd_intent_id:
            try:
                return self.payment_repo.get_payment_by_intent_id(pd_intent_id)
            except Exception:
                return None
        try:
            return self.payment_repo.get_payment_by_booking_id(booking.id)
        except Exception:
            return None

    def _resolve_amounts(self, booking: Booking, payment: PaymentIntent | None) -> dict[str, int]:
        full_amount_cents = 0
        if payment and payment.amount is not None:
            full_amount_cents = int(payment.amount)
        elif booking.total_price is not None:
            try:
                full_amount_cents = int(
                    (Decimal(str(booking.total_price)) * 100).quantize(Decimal("1"))
                )
            except Exception:
                full_amount_cents = 0

        lesson_price_cents = 0
        try:
            lesson_price_cents = int(
                (
                    Decimal(str(booking.hourly_rate))
                    * Decimal(int(booking.duration_minutes or 0))
                    * Decimal("100")
                    / Decimal("60")
                ).quantize(Decimal("1"))
            )
        except Exception:
            lesson_price_cents = 0

        platform_fee_cents = int(payment.application_fee) if payment else 0
        instructor_payout_cents = 0
        if payment and payment.instructor_payout_cents is not None:
            instructor_payout_cents = int(payment.instructor_payout_cents)
        elif payment and payment.amount is not None:
            instructor_payout_cents = max(0, int(payment.amount) - platform_fee_cents)

        return {
            "full_amount_cents": full_amount_cents,
            "lesson_price_cents": lesson_price_cents,
            "platform_fee_cents": platform_fee_cents,
            "instructor_payout_cents": instructor_payout_cents,
        }

    def _evaluate_cancel_refund(
        self,
        booking: Booking,
        *,
        reason_code: str,
        refund_preference: RefundPreference,
        full_amount_cents: int,
        lesson_price_cents: int,
    ) -> tuple[str, int]:
        if refund_preference == RefundPreference.FULL_CARD:
            return "card", full_amount_cents

        if refund_preference == RefundPreference.POLICY_BASED and reason_code in {
            "INSTRUCTOR_NO_SHOW",
            "DUPLICATE_BOOKING",
        }:
            return "card", full_amount_cents

        if not booking.booking_start_utc:
            return "card", full_amount_cents

        now = datetime.now(timezone.utc)
        scheduled_start = _ensure_utc(booking.booking_start_utc)
        hours_before = (scheduled_start - now).total_seconds() / 3600

        if hours_before >= 24:
            return "card", full_amount_cents
        if hours_before >= 12:
            return "credit", lesson_price_cents

        return "credit", int(round(lesson_price_cents * 0.5))

    def _compute_impacts(
        self,
        booking: Booking,
        payment: PaymentIntent | None,
        refund_method: str | None,
        refund_amount_cents: int | None,
    ) -> dict[str, Decimal]:
        if not refund_method or refund_method == "none" or refund_amount_cents is None:
            return {
                "instructor_payout_impact": Decimal("0.00"),
                "platform_fee_impact": Decimal("0.00"),
            }

        amounts = self._resolve_amounts(booking, payment)
        gross_cents = amounts["full_amount_cents"]
        platform_fee_cents = amounts["platform_fee_cents"]
        instructor_payout_cents = amounts["instructor_payout_cents"]

        if refund_method == "card" and gross_cents > 0:
            platform_fee_portion = int(
                round(platform_fee_cents * (refund_amount_cents / gross_cents))
            )
            instructor_delta = -1 * max(0, refund_amount_cents - platform_fee_portion)
            return {
                "instructor_payout_impact": _cents_to_decimal(instructor_delta),
                "platform_fee_impact": _cents_to_decimal(platform_fee_portion),
            }

        if refund_method == "credit":
            if booking.booking_start_utc:
                hours_before = (
                    _ensure_utc(booking.booking_start_utc) - datetime.now(timezone.utc)
                ).total_seconds() / 3600
            else:
                hours_before = 0
            if hours_before < 12:
                payout_retained = int(round(instructor_payout_cents * 0.5))
                instructor_delta = -1 * max(0, instructor_payout_cents - payout_retained)
            else:
                instructor_delta = -1 * instructor_payout_cents
            return {
                "instructor_payout_impact": _cents_to_decimal(instructor_delta),
                "platform_fee_impact": Decimal("0.00"),
            }

        return {
            "instructor_payout_impact": Decimal("0.00"),
            "platform_fee_impact": Decimal("0.00"),
        }

    def _cancel_with_full_refund(
        self,
        booking: Booking,
        *,
        reason_code: str,
        idempotency_key: str,
    ) -> tuple[str | None, bool]:
        payment = self._resolve_payment(booking)
        amounts = self._resolve_amounts(booking, payment)
        refund_amount_cents = amounts["full_amount_cents"]
        refund_id = None
        refund_issued = False

        pd = booking.payment_detail
        payment_intent_id = pd.payment_intent_id if pd is not None else None
        pd_payment_status = (pd.payment_status if pd is not None else None) or ""
        already_captured = pd_payment_status.lower() in {
            PaymentStatus.SETTLED.value,
            PaymentStatus.LOCKED.value,
        }

        if payment_intent_id:
            if already_captured:
                stripe_result = self.stripe_service.refund_payment(
                    payment_intent_id,
                    amount_cents=refund_amount_cents,
                    reason="requested_by_customer",
                    idempotency_key=idempotency_key,
                )
                refund_id = stripe_result.get("refund_id")
                refund_issued = True
            else:
                self.stripe_service.cancel_payment_intent(
                    payment_intent_id,
                    idempotency_key=f"cancel_admin_{booking.id}",
                )
                refund_issued = True
        else:
            refund_issued = False

        with self.transaction():
            booking_locked = self.booking_repo.get_booking_with_details(booking.id)
            if not booking_locked:
                raise NotFoundException("Booking not found", code="BOOKING_NOT_FOUND")
            booking_locked.status = BookingStatus.CANCELLED
            booking_locked.cancelled_at = datetime.now(timezone.utc)
            booking_locked.cancellation_reason = reason_code
            bp = self.booking_repo.ensure_payment(booking_locked.id)
            bp.settlement_outcome = "admin_refund"
            booking_locked.refunded_to_card_amount = refund_amount_cents if refund_issued else 0
            if refund_issued:
                bp.payment_status = PaymentStatus.SETTLED.value
            else:
                bp.payment_status = bp.payment_status or PaymentStatus.MANUAL_REVIEW.value

        try:
            self.credit_service.release_credits_for_booking(
                booking_id=booking.id,
                use_transaction=False,
            )
        except Exception:
            logger.debug("Failed to release credits for booking %s", booking.id, exc_info=True)

        return refund_id, refund_issued

    def _cancel_without_refund(self, booking: Booking, *, reason_code: str) -> None:
        pd = booking.payment_detail
        payment_intent_id = pd.payment_intent_id if pd is not None else None
        pd_payment_status = ((pd.payment_status if pd is not None else None) or "").lower()
        capture_success = False
        if payment_intent_id and pd_payment_status == PaymentStatus.AUTHORIZED.value:
            try:
                self.stripe_service.capture_booking_payment_intent(
                    booking_id=booking.id,
                    payment_intent_id=payment_intent_id,
                    idempotency_key=f"capture_no_refund_{booking.id}",
                )
                capture_success = True
            except Exception:
                logger.debug("Capture failed for no-refund booking %s", booking.id, exc_info=True)

        with self.transaction():
            booking_locked = self.booking_repo.get_booking_with_details(booking.id)
            if not booking_locked:
                raise NotFoundException("Booking not found", code="BOOKING_NOT_FOUND")
            booking_locked.status = BookingStatus.CANCELLED
            booking_locked.cancelled_at = datetime.now(timezone.utc)
            booking_locked.cancellation_reason = reason_code
            bp = self.booking_repo.ensure_payment(booking_locked.id)
            bp.settlement_outcome = "admin_no_refund"
            if payment_intent_id and (
                capture_success or pd_payment_status == PaymentStatus.SETTLED.value
            ):
                bp.payment_status = PaymentStatus.SETTLED.value

        try:
            self.credit_service.forfeit_credits_for_booking(
                booking_id=booking.id,
                use_transaction=False,
            )
        except Exception:
            logger.debug("Failed to forfeit credits for booking %s", booking.id, exc_info=True)

    def _valid_states_for_notification(self, notification_type: NotificationType) -> set[str]:
        if notification_type == NotificationType.BOOKING_CONFIRMATION:
            return {"PENDING", "CONFIRMED", "COMPLETED"}
        if notification_type in {
            NotificationType.LESSON_REMINDER_24H,
            NotificationType.LESSON_REMINDER_1H,
        }:
            return {"CONFIRMED"}
        if notification_type == NotificationType.LESSON_COMPLETED:
            return {"COMPLETED"}
        if notification_type == NotificationType.CANCELLATION_NOTICE:
            return {"CANCELLED"}
        return set()

    def _send_admin_cancellation_notifications(self, booking: Booking) -> None:
        try:
            self.notification_service._send_student_cancellation_confirmation(booking)
            self.notification_service._send_instructor_cancellation_confirmation(booking)
        except Exception:
            logger.debug("Admin cancellation notifications failed", exc_info=True)

    def _log_cancellation_message(self, booking: Booking) -> None:
        try:
            self.system_message_service.create_booking_cancelled_message(
                student_id=booking.student_id,
                instructor_id=booking.instructor_id,
                booking_id=booking.id,
                booking_date=booking.booking_date,
                start_time=booking.start_time,
                cancelled_by=None,
            )
        except Exception:
            logger.debug("Failed to create admin cancellation system message", exc_info=True)

    def _post_complete_actions(self, booking: Booking) -> None:
        try:
            from app.services.student_credit_service import StudentCreditService

            StudentCreditService(self.db).maybe_issue_milestone_credit(
                student_id=booking.student_id,
                booking_id=booking.id,
            )
        except Exception:
            logger.debug(
                "Failed issuing milestone credit for booking %s", booking.id, exc_info=True
            )

        try:
            service_name = None
            if booking.instructor_service and booking.instructor_service.name:
                service_name = booking.instructor_service.name
            self.system_message_service.create_booking_completed_message(
                student_id=booking.student_id,
                instructor_id=booking.instructor_id,
                booking_id=booking.id,
                booking_date=booking.booking_date,
                service_name=service_name,
            )
        except Exception:
            logger.debug(
                "Failed creating completion system message for %s", booking.id, exc_info=True
            )

        try:
            from app.services.referral_service import ReferralService

            ReferralService(self.db).on_instructor_lesson_completed(
                instructor_user_id=booking.instructor_id,
                booking_id=booking.id,
                completed_at=booking.completed_at or datetime.now(timezone.utc),
            )
        except Exception:
            logger.debug("Failed to process referral for booking %s", booking.id, exc_info=True)

    @staticmethod
    def _status_value(status: BookingStatus | str | None) -> str:
        if isinstance(status, BookingStatus):
            return status.value
        if isinstance(status, str):
            return status.upper()
        return ""
