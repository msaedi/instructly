"""Refund preview/execute workflow for MCP admin operations."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictException,
    MCPTokenError,
    NotFoundException,
    ValidationException,
)
from app.models.booking import Booking, BookingStatus
from app.models.payment import PaymentIntent
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_refund import (
    OriginalPayment,
    RefundAmount,
    RefundAmountType,
    RefundExecuteMeta,
    RefundExecuteResponse,
    RefundImpact,
    RefundMeta,
    RefundPreviewResponse,
    RefundReasonCode,
    RefundResult,
    UpdatedBooking,
    UpdatedPayment,
)
from app.services.audit_service import AuditService
from app.services.base import BaseService
from app.services.config_service import ConfigService
from app.services.credit_service import CreditService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.pricing_service import PricingService
from app.services.refund_policy_engine import RefundPolicyEngine, RefundPolicyResult
from app.services.stripe_service import StripeService

logger = logging.getLogger(__name__)

_STRIPE_REASON_MAP = {
    RefundReasonCode.CANCEL_POLICY: "requested_by_customer",
    RefundReasonCode.GOODWILL: "requested_by_customer",
    RefundReasonCode.DUPLICATE: "duplicate",
    RefundReasonCode.DISPUTE_PREVENTION: "requested_by_customer",
    RefundReasonCode.INSTRUCTOR_NO_SHOW: "requested_by_customer",
    RefundReasonCode.SERVICE_ISSUE: "requested_by_customer",
}


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cents_to_dollars(cents: int) -> float:
    return round(cents / 100.0, 2)


def _dollars_to_cents(value: float) -> int:
    return int(round(value * 100))


def _redact_stripe_id(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    last4 = cleaned[-4:] if len(cleaned) > 4 else cleaned
    prefix = cleaned.split("_", 1)[0] if "_" in cleaned else ""
    if prefix:
        return f"{prefix}_...{last4}"
    return f"...{last4}" if len(cleaned) > 4 else last4


class RefundService(BaseService):
    """Refund preview and execution with guardrails for MCP."""

    CONFIRM_TOKEN_TTL = timedelta(minutes=5)

    def __init__(
        self,
        db: Session,
        *,
        policy_engine: RefundPolicyEngine | None = None,
        confirm_service: MCPConfirmTokenService | None = None,
        idempotency_service: MCPIdempotencyService | None = None,
        stripe_service: StripeService | None = None,
        credit_service: CreditService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        super().__init__(db)
        self.booking_repo = RepositoryFactory.create_booking_repository(db)
        self.payment_repo = RepositoryFactory.create_payment_repository(db)
        self.policy_engine = policy_engine or RefundPolicyEngine()
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
        self.audit_service = audit_service or AuditService(db)

    @BaseService.measure_operation("mcp_refunds.preview")
    def preview_refund(
        self,
        *,
        booking_id: str,
        reason_code: RefundReasonCode,
        amount: RefundAmount,
        note: str | None,
        actor_id: str,
    ) -> RefundPreviewResponse:
        booking = self.booking_repo.get_booking_with_details(booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found", code="BOOKING_NOT_FOUND")

        payment = self.payment_repo.get_payment_by_booking_id(booking_id)
        if not payment:
            raise NotFoundException(
                f"No payment found for booking {booking_id}", code="PAYMENT_NOT_FOUND"
            )

        requested_cents = self._resolve_requested_amount_cents(amount, payment)
        policy_result = self.policy_engine.evaluate(
            booking=booking,
            payment=payment,
            reason_code=reason_code,
            requested_amount_cents=requested_cents,
        )

        warnings: list[str] = []
        payment_status = (booking.payment_status or payment.status or "").lower()
        if payment_status == "settled":
            warnings.append("Instructor payout already transferred - this will trigger a clawback")
        if policy_result.method == "credit" and reason_code == RefundReasonCode.CANCEL_POLICY:
            warnings.append("Policy dictates credit-only refund at this time window")

        confirm_token = None
        idempotency_key = None
        token_expires_at = None

        if policy_result.eligible:
            idempotency_key = str(uuid4())
            confirm_token, token_expires_at = self.confirm_service.generate_token(
                {
                    "booking_id": booking_id,
                    "reason_code": reason_code.value,
                    "amount_cents": requested_cents,
                    "amount_type": amount.type.value,
                    "policy_result": policy_result.to_payload(),
                    "actor_id": actor_id,
                    "note": note,
                    "idempotency_key": idempotency_key,
                },
                actor_id=actor_id,
                ttl_minutes=int(self.CONFIRM_TOKEN_TTL.total_seconds() / 60),
            )

        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="REFUND_PREVIEW",
            resource_type="booking",
            resource_id=booking_id,
            metadata={
                "reason_code": reason_code.value,
                "amount_cents": requested_cents,
                "eligible": policy_result.eligible,
            },
        )

        impact = self._build_refund_impact(booking, payment, policy_result)

        return RefundPreviewResponse(
            meta=RefundMeta(
                generated_at=datetime.now(timezone.utc),
                booking_id=booking_id,
                reason_code=reason_code.value,
            ),
            eligible=policy_result.eligible,
            ineligible_reason=policy_result.reason if not policy_result.eligible else None,
            policy_basis=policy_result.policy_basis,
            impact=impact,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
            token_expires_at=token_expires_at,
        )

    @BaseService.measure_operation("mcp_refunds.execute")
    async def execute_refund(
        self,
        *,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> RefundExecuteResponse:
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

        token_idempotency = payload.get("idempotency_key")
        if token_idempotency != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        try:
            already_done, cached = await self.idempotency_service.check_and_store(
                idempotency_key, operation="mcp_refunds.execute"
            )
        except Exception as exc:
            logger.error("Refund idempotency check failed", exc_info=exc)
            raise

        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return RefundExecuteResponse.model_validate(cached)

        booking_id = str(payload.get("booking_id"))
        reason_code = RefundReasonCode(str(payload.get("reason_code")))
        policy_payload = payload.get("policy_result")
        if not isinstance(policy_payload, dict):
            raise ValidationException("Invalid policy payload")
        policy_result = RefundPolicyResult.from_payload(policy_payload)
        if not policy_result.eligible:
            raise ValidationException("Refund is no longer eligible", code="REFUND_INELIGIBLE")

        booking = await asyncio.to_thread(self.booking_repo.get_booking_with_details, booking_id)
        if not booking:
            raise NotFoundException(f"Booking {booking_id} not found", code="BOOKING_NOT_FOUND")
        payment = await asyncio.to_thread(self.payment_repo.get_payment_by_booking_id, booking_id)
        if not payment:
            raise NotFoundException(
                f"No payment found for booking {booking_id}", code="PAYMENT_NOT_FOUND"
            )

        requested_cents = int(payload.get("amount_cents", 0) or 0)
        executed_at = datetime.now(timezone.utc)

        result = "success"
        error: str | None = None
        refund_status = "succeeded"
        stripe_refund_id: str | None = None

        if policy_result.method == "card":
            try:
                stripe_result = await asyncio.to_thread(
                    self.stripe_service.refund_payment,
                    payment.stripe_payment_intent_id,
                    amount_cents=policy_result.student_card_refund_cents,
                    reason=_STRIPE_REASON_MAP.get(reason_code, "requested_by_customer"),
                    idempotency_key=idempotency_key,
                )
                refund_status = (
                    "succeeded" if stripe_result.get("status") == "succeeded" else "pending"
                )
                stripe_refund_id = _redact_stripe_id(str(stripe_result.get("refund_id")))
            except Exception as exc:
                logger.error("Stripe refund failed", exc_info=exc)
                result = "failed"
                error = "payment_provider_error"
                refund_status = "failed"
        else:
            try:
                await asyncio.to_thread(
                    self.credit_service.issue_credit,
                    user_id=booking.student_id,
                    amount_cents=policy_result.student_credit_cents,
                    source_type="refund",
                    reason=f"Refund for booking {booking_id}",
                    source_booking_id=booking_id,
                )
                refund_status = "succeeded"
            except Exception as exc:
                logger.error("Credit issuance failed", exc_info=exc)
                result = "failed"
                error = "credit_issue_failed"
                refund_status = "failed"

        if result == "success":
            await asyncio.to_thread(
                self._apply_booking_updates,
                booking=booking,
                policy_result=policy_result,
                reason_code=reason_code,
            )
            await asyncio.to_thread(
                self._apply_payment_updates,
                payment=payment,
            )

        audit_id = str(uuid4())
        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="REFUND_EXECUTE",
            resource_type="booking",
            resource_id=booking_id,
            metadata={
                "result": result,
                "reason_code": reason_code.value,
                "amount_cents": requested_cents,
                "method": policy_result.method,
                "idempotency_key": idempotency_key,
            },
            status="success" if result == "success" else "failed",
            error_message=error,
        )

        response = RefundExecuteResponse(
            meta=RefundExecuteMeta(
                executed_at=executed_at,
                booking_id=booking_id,
                idempotency_key=idempotency_key,
            ),
            result=result,
            error=error,
            refund=RefundResult(
                status=refund_status,
                amount=_cents_to_dollars(requested_cents),
                method=policy_result.method or "",
                stripe_refund_id=stripe_refund_id,
            )
            if result == "success"
            else None,
            updated_booking=UpdatedBooking(
                id=booking_id,
                status=BookingStatus.CANCELLED.value,
                updated_at=executed_at,
            )
            if result == "success"
            else None,
            updated_payment=UpdatedPayment(
                status="refunded",
                refunded_at=executed_at,
            )
            if result == "success"
            else None,
            audit_id=audit_id,
        )

        await self.idempotency_service.store_result(
            idempotency_key, response.model_dump(mode="json")
        )

        return response

    def _resolve_requested_amount_cents(self, amount: RefundAmount, payment: PaymentIntent) -> int:
        gross_cents = int(payment.amount or 0)
        if amount.type == RefundAmountType.FULL:
            requested_cents = gross_cents
        else:
            if amount.value is None:
                raise ValidationException(
                    "Partial refund requires amount", code="REFUND_AMOUNT_MISSING"
                )
            requested_cents = _dollars_to_cents(float(amount.value))
        if requested_cents <= 0:
            raise ValidationException(
                "Refund amount must be positive", code="REFUND_AMOUNT_INVALID"
            )
        if requested_cents > gross_cents:
            raise ValidationException(
                "Partial refund cannot exceed original payment",
                code="REFUND_AMOUNT_EXCEEDS_TOTAL",
            )
        return requested_cents

    def _build_refund_impact(
        self,
        booking: Booking,
        payment: PaymentIntent,
        policy_result: RefundPolicyResult,
    ) -> RefundImpact:
        gross_cents = int(payment.amount or 0)
        platform_fee_cents = int(payment.application_fee or 0)
        instructor_payout_cents = int(
            payment.instructor_payout_cents
            if payment.instructor_payout_cents is not None
            else max(0, gross_cents - platform_fee_cents)
        )
        payment_status = booking.payment_status or payment.status or "unknown"
        captured_at = getattr(booking, "auth_attempted_at", None)

        return RefundImpact(
            refund_method=policy_result.method or "",
            student_card_refund=_cents_to_dollars(policy_result.student_card_refund_cents),
            student_credit_issued=_cents_to_dollars(policy_result.student_credit_cents),
            instructor_payout_delta=_cents_to_dollars(policy_result.instructor_payout_delta_cents),
            platform_fee_refunded=_cents_to_dollars(policy_result.platform_fee_refunded_cents),
            original_payment=OriginalPayment(
                gross=_cents_to_dollars(gross_cents),
                platform_fee=_cents_to_dollars(platform_fee_cents),
                instructor_payout=_cents_to_dollars(instructor_payout_cents),
                status=str(payment_status),
                captured_at=_ensure_utc(captured_at) if captured_at else None,
            ),
        )

    def _apply_booking_updates(
        self,
        *,
        booking: Booking,
        policy_result: RefundPolicyResult,
        reason_code: RefundReasonCode,
    ) -> None:
        now = datetime.now(timezone.utc)
        instructor_payout_amount = max(
            0,
            (booking.instructor_payout_amount or 0) + policy_result.instructor_payout_delta_cents,
        )
        self.booking_repo.apply_refund_updates(
            booking,
            status=BookingStatus.CANCELLED,
            cancelled_at=now,
            cancellation_reason=reason_code.value,
            settlement_outcome=booking.settlement_outcome or "admin_refund",
            refunded_to_card_amount=policy_result.student_card_refund_cents,
            student_credit_amount=policy_result.student_credit_cents,
            instructor_payout_amount=instructor_payout_amount,
            updated_at=now,
        )

    def _apply_payment_updates(self, *, payment: PaymentIntent) -> None:
        try:
            # PaymentIntent status must remain a valid Stripe status (e.g., succeeded).
            self.payment_repo.update_payment_status(payment.stripe_payment_intent_id, "succeeded")
        except Exception:
            logger.debug("Failed updating payment status", exc_info=True)
