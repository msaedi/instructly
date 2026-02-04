"""Admin student actions for MCP workflows."""

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
from app.models.booking import Booking
from app.models.user import User
from app.repositories.conversation_state_repository import ConversationStateRepository
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_student_actions import (
    CreditAdjustAction,
    CreditAdjustExecuteResponse,
    CreditAdjustPreviewResponse,
    CreditHistoryEntry,
    CreditHistoryResponse,
    CreditHistorySummary,
    RefundFraudFlags,
    RefundHistoryEntry,
    RefundHistoryResponse,
    RefundHistorySummary,
    StudentState,
    StudentSuspendExecuteResponse,
    StudentSuspendPreviewResponse,
    StudentUnsuspendResponse,
)
from app.services.audit_service import AuditService
from app.services.base import BaseService
from app.services.booking_admin_service import BookingAdminService
from app.services.booking_service import BookingService
from app.services.credit_service import CreditService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

_DECIMAL_00 = Decimal("0.00")
_DECIMAL_RATE = Decimal("0.01")
_SUSPEND_CREDIT_REVOKE_REASON = "admin_suspension"


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cents_to_decimal(value: int | None) -> Decimal:
    if value is None:
        return _DECIMAL_00
    return (Decimal(value) / Decimal("100")).quantize(_DECIMAL_RATE)


def _decimal_to_cents(value: Decimal | int | float | str) -> int:
    cents = (Decimal(str(value)) * Decimal("100")).quantize(Decimal("1"))
    return int(cents)


def _booking_amount(booking: Booking) -> Decimal:
    if booking.total_price is not None:
        return Decimal(str(booking.total_price)).quantize(Decimal("0.01"))
    if booking.hourly_rate is None or not booking.duration_minutes:
        return _DECIMAL_00
    hourly = Decimal(str(booking.hourly_rate))
    duration = Decimal(int(booking.duration_minutes))
    total = (hourly * duration / Decimal("60")).quantize(Decimal("0.01"))
    return total


class StudentAdminService(BaseService):
    """Admin student actions with preview/execute guardrails."""

    CONFIRM_TOKEN_TTL = timedelta(minutes=5)

    def __init__(
        self,
        db: Session,
        *,
        booking_admin_service: BookingAdminService | None = None,
        booking_service: BookingService | None = None,
        confirm_service: MCPConfirmTokenService | None = None,
        idempotency_service: MCPIdempotencyService | None = None,
        notification_service: NotificationService | None = None,
        audit_service: AuditService | None = None,
        credit_service: CreditService | None = None,
    ) -> None:
        super().__init__(db)
        self.user_repo = RepositoryFactory.create_user_repository(db)
        self.booking_repo = RepositoryFactory.create_booking_repository(db)
        self.credit_repo = RepositoryFactory.create_credit_repository(db)
        self.payment_repo = RepositoryFactory.create_payment_repository(db)
        self.conversation_repo = RepositoryFactory.create_conversation_repository(db)
        self.conversation_state_repo = ConversationStateRepository(db)
        self.confirm_service = confirm_service or MCPConfirmTokenService(db)
        self.idempotency_service = idempotency_service or MCPIdempotencyService(db)
        self.notification_service = notification_service or NotificationService(db)
        self.audit_service = audit_service or AuditService(db)
        self.credit_service = credit_service or CreditService(db)
        self.booking_service = booking_service or BookingService(
            db, notification_service=self.notification_service
        )
        self.booking_admin_service = booking_admin_service or BookingAdminService(
            db,
            booking_service=self.booking_service,
            notification_service=self.notification_service,
            audit_service=self.audit_service,
            credit_service=self.credit_service,
        )

    def _load_student(self, student_id: str) -> User:
        user = self.user_repo.get_by_id(student_id)
        if not user and "@" in student_id:
            user = self.user_repo.get_by_email(student_id)
        if not user:
            raise NotFoundException("Student not found")
        if not user.is_student:
            raise ValidationException("User is not a student")
        return user

    def _conversation_ids_for_user(self, user_id: str) -> list[str]:
        ids: list[str] = []
        cursor: str | None = None
        while True:
            conversations = self.conversation_repo.find_for_user(
                user_id=user_id, limit=200, cursor=cursor
            )
            if not conversations:
                break
            ids.extend([conv.id for conv in conversations if getattr(conv, "id", None)])
            if len(conversations) < 200:
                break
            last = conversations[-1]
            last_ts = getattr(last, "last_message_at", None) or getattr(last, "created_at", None)
            if not last_ts:
                break
            cursor = _ensure_utc(last_ts).isoformat()
        return ids

    def _archive_conversations(self, user_id: str) -> int:
        conversation_ids = self._conversation_ids_for_user(user_id)
        for conversation_id in conversation_ids:
            self.conversation_state_repo.set_state(
                user_id,
                "archived",
                conversation_id=conversation_id,
            )
        return len(conversation_ids)

    def _forfeit_all_credits(self, user_id: str, reason: str) -> int:
        credits = self.credit_repo.list_credits_for_user(user_id=user_id, include_expired=True)
        now = datetime.now(timezone.utc)
        total_forfeited = 0
        for credit in credits:
            status = getattr(credit, "status", None)
            if status in {"revoked", "forfeited", "expired"}:
                continue
            amount = int(getattr(credit, "amount_cents", 0) or 0)
            if amount <= 0:
                continue
            credit.status = "revoked"
            credit.revoked = True
            credit.revoked_at = now
            credit.revoked_reason = reason
            credit.reserved_amount_cents = 0
            credit.reserved_for_booking_id = None
            credit.reserved_at = None
            total_forfeited += amount
        return total_forfeited

    def _restore_forfeited_credits(self, user_id: str) -> int:
        credits = self.credit_repo.get_revoked_credits_for_user(
            user_id=user_id, revoked_reason=_SUSPEND_CREDIT_REVOKE_REASON
        )
        now = datetime.now(timezone.utc)
        restored = 0
        for credit in credits:
            credit.revoked = False
            credit.revoked_at = None
            credit.revoked_reason = None
            if credit.expires_at and _ensure_utc(credit.expires_at) <= now:
                credit.status = "expired"
                continue
            credit.status = "available"
            restored += int(getattr(credit, "amount_cents", 0) or 0)
        return restored

    def _remove_available_credits(self, user_id: str, amount_cents: int, reason: str) -> int:
        if amount_cents <= 0:
            return 0
        available_total = self.credit_repo.get_total_available_credits(user_id=user_id)
        if available_total < amount_cents:
            raise ValidationException("Insufficient available credits", code="INSUFFICIENT_CREDITS")

        credits = self.credit_repo.get_available_credits(
            user_id=user_id, order_by="expires_at", for_update=True
        )
        remaining = amount_cents
        revoked_count = 0
        now = datetime.now(timezone.utc)

        for credit in credits:
            if remaining <= 0:
                break
            credit_amount = int(getattr(credit, "amount_cents", 0) or 0)
            if credit_amount <= 0:
                continue
            revoke_amount = min(credit_amount, remaining)
            if credit_amount > revoke_amount:
                remainder_amount = credit_amount - revoke_amount
                self.payment_repo.create_platform_credit(
                    user_id=credit.user_id,
                    amount_cents=remainder_amount,
                    reason=f"Remainder of {credit.id}",
                    source_type=getattr(credit, "source_type", "admin_adjustment"),
                    source_booking_id=credit.source_booking_id,
                    expires_at=credit.expires_at,
                    original_expires_at=getattr(credit, "original_expires_at", None)
                    or credit.expires_at,
                    status="available",
                )
                credit.amount_cents = revoke_amount
            credit.status = "revoked"
            credit.revoked = True
            credit.revoked_at = now
            credit.revoked_reason = reason
            credit.reserved_amount_cents = 0
            credit.reserved_for_booking_id = None
            credit.reserved_at = None
            revoked_count += 1
            remaining -= revoke_amount
        return revoked_count

    @BaseService.measure_operation("mcp_student_actions.preview_suspend")
    def preview_suspend(
        self,
        *,
        student_id: str,
        reason_code: str,
        note: str,
        notify_student: bool,
        cancel_pending_bookings: bool,
        forfeit_credits: bool,
        actor_id: str,
    ) -> StudentSuspendPreviewResponse:
        user = self._load_student(student_id)

        credit_balance = _cents_to_decimal(
            self.credit_repo.get_total_available_credits(user_id=user.id)
        )
        current_state = StudentState(
            account_status=user.account_status,
            credit_balance=credit_balance,
            is_restricted=bool(getattr(user, "account_restricted", False)),
        )

        eligible = True
        ineligible_reason = None
        if user.account_status == "suspended":
            eligible = False
            ineligible_reason = "Already suspended"
        elif user.account_status == "deactivated":
            eligible = False
            ineligible_reason = "Account deactivated"

        pending_bookings = self.booking_repo.get_student_bookings(
            student_id=user.id,
            upcoming_only=True,
        )
        pending_value = sum((_booking_amount(b) for b in pending_bookings), _DECIMAL_00)
        active_conversations = int(self.conversation_repo.count_for_user(user.id) or 0)

        warnings: list[str] = []
        if pending_bookings:
            warnings.append(
                f"Student has {len(pending_bookings)} pending bookings totaling ${pending_value}"
            )
        if pending_bookings and not cancel_pending_bookings:
            warnings.append("Pending bookings will remain active")
        if credit_balance > _DECIMAL_00:
            warnings.append(f"Student has ${credit_balance} in available credits")
        if forfeit_credits and credit_balance > _DECIMAL_00:
            warnings.append("Available credits will be forfeited")
        if active_conversations:
            warnings.append(f"Student has {active_conversations} active conversations")

        will_suspend = eligible
        will_cancel_bookings = bool(
            eligible and cancel_pending_bookings and len(pending_bookings) > 0
        )

        confirm_token = None
        idempotency_key = None
        if eligible:
            idempotency_key = str(uuid4())
            payload = {
                "student_id": student_id,
                "reason_code": reason_code,
                "note": note,
                "notify_student": notify_student,
                "cancel_pending_bookings": cancel_pending_bookings,
                "forfeit_credits": forfeit_credits,
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
            action="STUDENT_SUSPEND_PREVIEW",
            resource_type="student",
            resource_id=user.id,
            metadata={
                "reason_code": reason_code,
                "eligible": eligible,
                "cancel_pending_bookings": cancel_pending_bookings,
                "forfeit_credits": forfeit_credits,
            },
        )

        return StudentSuspendPreviewResponse(
            eligible=eligible,
            ineligible_reason=ineligible_reason,
            current_state=current_state,
            pending_bookings_count=len(pending_bookings),
            pending_bookings_value=pending_value,
            credit_balance=credit_balance,
            active_conversations=active_conversations,
            will_suspend=will_suspend,
            will_cancel_bookings=will_cancel_bookings,
            will_refund_students=bool(will_cancel_bookings and not forfeit_credits),
            will_forfeit_credits=bool(eligible and forfeit_credits),
            will_notify_student=bool(eligible and notify_student),
            will_notify_affected_instructors=will_cancel_bookings,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    def _execute_suspend_sync(
        self,
        *,
        student_id: str,
        reason_code: str,
        note: str,
        notify_student: bool,
        cancel_pending_bookings: bool,
        forfeit_credits: bool,
        actor_id: str,
        idempotency_key: str,
    ) -> StudentSuspendExecuteResponse:
        user = self._load_student(student_id)
        if user.account_status == "suspended":
            raise ValidationException("Student already suspended", code="ALREADY_SUSPENDED")

        previous_status = user.account_status

        bookings_cancelled = 0
        refunds_issued = 0
        total_refunded_cents = 0
        credits_forfeited_cents = 0
        error: str | None = None

        pending_bookings: list[Booking] = []
        if cancel_pending_bookings:
            pending_bookings = self.booking_repo.get_student_bookings(
                student_id=user.id,
                upcoming_only=True,
            )

        for booking in pending_bookings:
            try:
                if forfeit_credits:
                    self.booking_admin_service._cancel_without_refund(
                        booking, reason_code=reason_code
                    )
                else:
                    self.booking_admin_service._cancel_with_full_refund(
                        booking,
                        reason_code=reason_code,
                        idempotency_key=f"student_suspend_{booking.id}_{idempotency_key}",
                    )

                refreshed = self.booking_repo.get_by_id(booking.id)
                if refreshed:
                    bookings_cancelled += 1
                    refunded = getattr(refreshed, "refunded_to_card_amount", None)
                    if refunded:
                        refunds_issued += 1
                        total_refunded_cents += int(refunded)

                if notify_student:
                    try:
                        booking_full = (
                            self.booking_repo.get_booking_with_details(booking.id)
                            if refreshed is None
                            else self.booking_repo.get_booking_with_details(refreshed.id)
                        )
                        if booking_full:
                            self.notification_service._send_student_cancellation_confirmation(
                                booking_full
                            )
                    except Exception:
                        logger.debug(
                            "Failed to notify student for booking %s", booking.id, exc_info=True
                        )

                try:
                    booking_full = self.booking_repo.get_booking_with_details(booking.id)
                    if booking_full:
                        self.notification_service._send_instructor_cancellation_confirmation(
                            booking_full
                        )
                except Exception:
                    logger.debug(
                        "Failed to notify instructor for booking %s", booking.id, exc_info=True
                    )

            except Exception as exc:
                logger.error("Failed to cancel booking %s", booking.id, exc_info=exc)
                error = "cancel_pending_bookings_failed"

        if forfeit_credits:
            try:
                credits_forfeited_cents = self._forfeit_all_credits(
                    user.id, _SUSPEND_CREDIT_REVOKE_REASON
                )
            except Exception as exc:
                logger.error("Failed to forfeit credits", exc_info=exc)
                error = "credit_forfeit_failed"

        archived_count = 0
        with self.transaction():
            user.account_status = "suspended"
            archived_count = self._archive_conversations(user.id)

        notifications_sent = []
        if cancel_pending_bookings and pending_bookings:
            notifications_sent.append("instructors_booking_cancelled")
        if notify_student:
            notifications_sent.append("student_notified")
        if archived_count:
            notifications_sent.append("conversations_archived")

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="STUDENT_SUSPEND_EXECUTE",
            resource_type="student",
            resource_id=user.id,
            metadata={
                "reason_code": reason_code,
                "note": note,
                "cancel_pending_bookings": cancel_pending_bookings,
                "forfeit_credits": forfeit_credits,
                "idempotency_key": idempotency_key,
            },
            status="failed" if error else "success",
            error_message=error,
        )

        return StudentSuspendExecuteResponse(
            success=error is None,
            error=error,
            student_id=user.id,
            previous_status=previous_status,
            new_status=user.account_status,
            bookings_cancelled=bookings_cancelled,
            refunds_issued=refunds_issued,
            total_refunded=_cents_to_decimal(total_refunded_cents),
            credits_forfeited=_cents_to_decimal(credits_forfeited_cents),
            notifications_sent=notifications_sent,
            audit_id=audit_id,
        )

    @BaseService.measure_operation("mcp_student_actions.execute_suspend")
    async def execute_suspend(
        self,
        *,
        student_id: str,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> StudentSuspendExecuteResponse:
        try:
            token_data = self.confirm_service.decode_token(confirm_token)
        except MCPTokenError:
            raise

        payload = token_data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationException("Invalid confirm token payload")

        self.confirm_service.validate_token(confirm_token, payload, actor_id=actor_id)

        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        token_student_id = str(payload.get("student_id"))
        if student_id and token_student_id != student_id:
            raise ValidationException("Student ID mismatch", code="STUDENT_MISMATCH")

        try:
            already_done, cached = await self.idempotency_service.check_and_store(
                idempotency_key, operation="mcp_student.suspend"
            )
        except Exception as exc:
            logger.error("Suspend idempotency check failed", exc_info=exc)
            raise

        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return StudentSuspendExecuteResponse.model_validate(cached)

        reason_code = str(payload.get("reason_code"))
        note = str(payload.get("note"))
        cancel_pending = bool(payload.get("cancel_pending_bookings", True))
        notify_student = bool(payload.get("notify_student", True))
        forfeit_credits = bool(payload.get("forfeit_credits", False))

        response = await asyncio.to_thread(
            self._execute_suspend_sync,
            student_id=token_student_id,
            reason_code=reason_code,
            note=note,
            notify_student=notify_student,
            cancel_pending_bookings=cancel_pending,
            forfeit_credits=forfeit_credits,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

        await self.idempotency_service.store_result(
            idempotency_key, response.model_dump(mode="json")
        )
        return response

    @BaseService.measure_operation("mcp_student_actions.unsuspend")
    def unsuspend(
        self,
        *,
        student_id: str,
        reason: str,
        restore_credits: bool,
        actor_id: str,
    ) -> StudentUnsuspendResponse:
        user = self._load_student(student_id)

        if user.account_status != "suspended":
            raise ValidationException("Student is not suspended", code="NOT_SUSPENDED")

        previous_status = user.account_status
        credits_restored_cents = 0

        with self.transaction():
            user.account_status = "active"
            if restore_credits:
                credits_restored_cents = self._restore_forfeited_credits(user.id)

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="STUDENT_UNSUSPEND",
            resource_type="student",
            resource_id=user.id,
            metadata={
                "reason": reason,
                "restore_credits": restore_credits,
            },
        )

        return StudentUnsuspendResponse(
            success=True,
            student_id=user.id,
            previous_status=previous_status,
            new_status=user.account_status,
            credits_restored=_cents_to_decimal(credits_restored_cents),
            audit_id=audit_id,
        )

    @BaseService.measure_operation("mcp_student_actions.preview_credit_adjust")
    def preview_credit_adjust(
        self,
        *,
        student_id: str,
        action: CreditAdjustAction,
        amount: Decimal,
        reason_code: str,
        note: str | None,
        expires_at: datetime | None,
        actor_id: str,
    ) -> CreditAdjustPreviewResponse:
        user = self._load_student(student_id)

        amount = Decimal(str(amount)).quantize(_DECIMAL_RATE)
        if amount <= 0:
            raise ValidationException("Amount must be positive", code="INVALID_AMOUNT")

        if expires_at and _ensure_utc(expires_at) <= datetime.now(timezone.utc):
            raise ValidationException("Expiration must be in the future", code="INVALID_EXPIRY")

        current_balance_cents = self.credit_repo.get_total_available_credits(user_id=user.id)
        current_balance = _cents_to_decimal(current_balance_cents)

        if action == CreditAdjustAction.ADD:
            new_balance = current_balance + amount
            delta = amount
            will_create = True
            will_remove = False
        elif action == CreditAdjustAction.REMOVE:
            new_balance = current_balance - amount
            delta = amount * Decimal("-1")
            will_create = False
            will_remove = True
        else:
            new_balance = amount
            delta = new_balance - current_balance
            will_create = delta > 0
            will_remove = delta < 0

        eligible = True
        ineligible_reason = None
        warnings: list[str] = []
        if new_balance < _DECIMAL_00:
            eligible = False
            ineligible_reason = "negative_balance"
            warnings.append("Adjustment would result in negative balance")

        reserved_cents = self.credit_repo.get_total_reserved_credits(user_id=user.id)
        if reserved_cents:
            warnings.append("Student has reserved credits for upcoming bookings")

        confirm_token = None
        idempotency_key = None
        if eligible:
            idempotency_key = str(uuid4())
            payload = {
                "student_id": student_id,
                "action": action.value,
                "amount_cents": _decimal_to_cents(amount),
                "reason_code": reason_code,
                "note": note,
                "expires_at": expires_at.isoformat() if expires_at else None,
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
            action="STUDENT_CREDIT_ADJUST_PREVIEW",
            resource_type="student",
            resource_id=user.id,
            metadata={
                "action": action.value,
                "reason_code": reason_code,
                "amount": str(amount),
                "eligible": eligible,
            },
        )

        return CreditAdjustPreviewResponse(
            eligible=eligible,
            ineligible_reason=ineligible_reason,
            current_balance=current_balance,
            new_balance=new_balance,
            delta=delta,
            will_create_credit=will_create,
            will_remove_credit=will_remove,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    def _execute_credit_adjust_sync(
        self,
        *,
        student_id: str,
        action: CreditAdjustAction,
        amount_cents: int,
        reason_code: str,
        note: str | None,
        expires_at: datetime | None,
        actor_id: str,
    ) -> CreditAdjustExecuteResponse:
        user = self._load_student(student_id)
        if amount_cents <= 0:
            raise ValidationException("Amount must be positive", code="INVALID_AMOUNT")

        previous_balance_cents = self.credit_repo.get_total_available_credits(user_id=user.id)
        previous_balance = _cents_to_decimal(previous_balance_cents)

        credits_created = 0
        credits_revoked = 0

        with self.transaction():
            if action == CreditAdjustAction.ADD:
                self.payment_repo.create_platform_credit(
                    user_id=user.id,
                    amount_cents=amount_cents,
                    reason=reason_code,
                    source_type="admin_adjustment",
                    expires_at=expires_at,
                    original_expires_at=expires_at,
                    status="available",
                )
                credits_created = 1
            elif action == CreditAdjustAction.REMOVE:
                credits_revoked = self._remove_available_credits(user.id, amount_cents, reason_code)
            else:
                desired_balance = amount_cents
                delta = desired_balance - previous_balance_cents
                if delta > 0:
                    self.payment_repo.create_platform_credit(
                        user_id=user.id,
                        amount_cents=delta,
                        reason=reason_code,
                        source_type="admin_adjustment",
                        expires_at=expires_at,
                        original_expires_at=expires_at,
                        status="available",
                    )
                    credits_created = 1
                elif delta < 0:
                    credits_revoked = self._remove_available_credits(
                        user.id, abs(delta), reason_code
                    )

        new_balance_cents = self.credit_repo.get_total_available_credits(user_id=user.id)
        new_balance = _cents_to_decimal(new_balance_cents)
        delta_balance = new_balance - previous_balance

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="STUDENT_CREDIT_ADJUST_EXECUTE",
            resource_type="student",
            resource_id=user.id,
            metadata={
                "action": action.value,
                "reason_code": reason_code,
                "note": note,
                "amount_cents": amount_cents,
            },
        )

        return CreditAdjustExecuteResponse(
            success=True,
            student_id=user.id,
            previous_balance=previous_balance,
            new_balance=new_balance,
            delta=delta_balance,
            credits_created=credits_created,
            credits_revoked=credits_revoked,
            audit_id=audit_id,
        )

    @BaseService.measure_operation("mcp_student_actions.execute_credit_adjust")
    async def execute_credit_adjust(
        self,
        *,
        student_id: str,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> CreditAdjustExecuteResponse:
        try:
            token_data = self.confirm_service.decode_token(confirm_token)
        except MCPTokenError:
            raise

        payload = token_data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationException("Invalid confirm token payload")

        self.confirm_service.validate_token(confirm_token, payload, actor_id=actor_id)

        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        token_student_id = str(payload.get("student_id"))
        if student_id and token_student_id != student_id:
            raise ValidationException("Student ID mismatch", code="STUDENT_MISMATCH")

        try:
            already_done, cached = await self.idempotency_service.check_and_store(
                idempotency_key, operation="mcp_student.credit_adjust"
            )
        except Exception as exc:
            logger.error("Credit adjust idempotency check failed", exc_info=exc)
            raise

        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return CreditAdjustExecuteResponse.model_validate(cached)

        action = CreditAdjustAction(str(payload.get("action")))
        amount_cents = int(payload.get("amount_cents") or 0)
        reason_code = str(payload.get("reason_code"))
        note = payload.get("note")
        expires_at_raw = payload.get("expires_at")
        expires_at = None
        if expires_at_raw:
            expires_at = datetime.fromisoformat(str(expires_at_raw))

        response = await asyncio.to_thread(
            self._execute_credit_adjust_sync,
            student_id=token_student_id,
            action=action,
            amount_cents=amount_cents,
            reason_code=reason_code,
            note=note,
            expires_at=expires_at,
            actor_id=actor_id,
        )

        await self.idempotency_service.store_result(
            idempotency_key, response.model_dump(mode="json")
        )
        return response

    @BaseService.measure_operation("mcp_student_actions.credit_history")
    def credit_history(self, *, student_id: str, include_expired: bool) -> CreditHistoryResponse:
        user = self._load_student(student_id)

        credits = self.credit_repo.list_credits_for_user(
            user_id=user.id, include_expired=include_expired
        )

        entries: list[CreditHistoryEntry] = []
        total_earned = 0
        total_spent = 0
        total_expired = 0
        total_forfeited = 0

        for credit in credits:
            amount = int(getattr(credit, "amount_cents", 0) or 0)
            if amount < 0:
                amount = 0
            total_earned += amount
            status = getattr(credit, "status", None) or "unknown"

            if status == "revoked":
                total_forfeited += amount
            elif status == "expired":
                total_expired += amount

            if status != "revoked" and (credit.used_booking_id or credit.used_at):
                total_spent += amount

            entries.append(
                CreditHistoryEntry(
                    credit_id=credit.id,
                    amount=_cents_to_decimal(amount),
                    status=status,
                    reason=str(getattr(credit, "reason", "")),
                    source_type=str(getattr(credit, "source_type", "")),
                    created_at=_ensure_utc(credit.created_at),
                    expires_at=_ensure_utc(credit.expires_at)
                    if getattr(credit, "expires_at", None)
                    else None,
                    used_at=_ensure_utc(credit.used_at)
                    if getattr(credit, "used_at", None)
                    else None,
                    forfeited_at=_ensure_utc(credit.forfeited_at)
                    if getattr(credit, "forfeited_at", None)
                    else None,
                    revoked_at=_ensure_utc(credit.revoked_at)
                    if getattr(credit, "revoked_at", None)
                    else None,
                    reserved_amount=_cents_to_decimal(
                        getattr(credit, "reserved_amount_cents", None)
                    )
                    if getattr(credit, "reserved_amount_cents", None)
                    else None,
                    reserved_for_booking_id=getattr(credit, "reserved_for_booking_id", None),
                )
            )

        summary = CreditHistorySummary(
            total_earned=_cents_to_decimal(total_earned),
            total_spent=_cents_to_decimal(total_spent),
            total_expired=_cents_to_decimal(total_expired),
            total_forfeited=_cents_to_decimal(total_forfeited),
            available_balance=_cents_to_decimal(
                self.credit_repo.get_total_available_credits(user_id=user.id)
            ),
            reserved_balance=_cents_to_decimal(
                self.credit_repo.get_total_reserved_credits(user_id=user.id)
            ),
        )

        return CreditHistoryResponse(
            include_expired=include_expired,
            credits=entries,
            summary=summary,
        )

    @BaseService.measure_operation("mcp_student_actions.refund_history")
    def refund_history(self, *, student_id: str) -> RefundHistoryResponse:
        user = self._load_student(student_id)

        bookings = self.booking_repo.list_student_refund_bookings(user.id)
        entries: list[RefundHistoryEntry] = []

        for booking in bookings:
            refunded_at = getattr(booking, "cancelled_at", None) or getattr(
                booking, "updated_at", None
            )
            refund_ts = _ensure_utc(refunded_at) if refunded_at else None

            refunded_to_card = int(getattr(booking, "refunded_to_card_amount", 0) or 0)
            if refunded_to_card > 0:
                entries.append(
                    RefundHistoryEntry(
                        booking_id=booking.id,
                        amount=_cents_to_decimal(refunded_to_card),
                        method="card",
                        status=str(getattr(booking, "payment_status", "refunded")),
                        refunded_at=refund_ts,
                    )
                )

            credit_amount = int(getattr(booking, "student_credit_amount", 0) or 0)
            if credit_amount > 0:
                entries.append(
                    RefundHistoryEntry(
                        booking_id=booking.id,
                        amount=_cents_to_decimal(credit_amount),
                        method="credit",
                        status=str(getattr(booking, "payment_status", "credited")),
                        refunded_at=refund_ts,
                    )
                )

        total_card = sum(
            _decimal_to_cents(entry.amount) for entry in entries if entry.method == "card"
        )
        total_credit = sum(
            _decimal_to_cents(entry.amount) for entry in entries if entry.method == "credit"
        )
        total_refunds = total_card + total_credit

        refund_count = len(entries)
        total_bookings = self.booking_repo.count_student_bookings(user.id)
        refund_rate = float(refund_count) / float(total_bookings) if total_bookings else 0.0

        now = datetime.now(timezone.utc)
        refunds_last_7 = 0
        refunds_last_30 = 0
        refunds_amount_last_30 = 0
        for entry in entries:
            if not entry.refunded_at:
                continue
            days_delta = (now - _ensure_utc(entry.refunded_at)).days
            amount_cents = _decimal_to_cents(entry.amount)
            if days_delta <= 7:
                refunds_last_7 += 1
            if days_delta <= 30:
                refunds_last_30 += 1
                refunds_amount_last_30 += amount_cents

        fraud_flags = RefundFraudFlags(
            refund_rate=refund_rate,
            high_refund_rate=refund_rate > 0.2,
            rapid_refunds=refunds_last_7 >= 3,
            high_refund_amount=refunds_amount_last_30 > 50000,
            refunds_last_7_days=refunds_last_7,
            refunds_last_30_days=refunds_last_30,
        )

        summary = RefundHistorySummary(
            total_card_refunds=_cents_to_decimal(total_card),
            total_credit_refunds=_cents_to_decimal(total_credit),
            total_refunds=_cents_to_decimal(total_refunds),
            refund_count=refund_count,
        )

        return RefundHistoryResponse(
            refunds=entries,
            summary=summary,
            fraud_flags=fraud_flags,
        )


__all__ = ["StudentAdminService"]
