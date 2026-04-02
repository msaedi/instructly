"""Celery facade for payment tasks."""
from __future__ import annotations

from datetime import datetime
import sys
from typing import Any, Dict, Optional, Union, cast

from sqlalchemy.orm import Session
import stripe as stripe

from app.core.booking_lock import booking_lock_sync
from app.core.exceptions import ServiceException
from app.database import get_db
from app.models.booking import Booking
from app.monitoring.sentry_crons import monitor_if_configured
from app.repositories.booking_repository import BookingRepository
from app.repositories.factory import RepositoryFactory
from app.services.booking_service import BookingService
from app.services.config_service import ConfigService
from app.services.notification_service import NotificationService
from app.services.pricing_service import PricingService, TierEvaluationResults
from app.services.stripe_service import StripeService
from app.services.student_credit_service import StudentCreditService
from app.services.timezone_service import TimezoneService
from app.tasks.payment import (
    authorization,
    authorization_retry,
    capture,
    capture_orchestration,
    capture_reauth,
    capture_recovery,
    late_cancel_noshow,
    maintenance,
)
from app.tasks.payment.common import (
    STRIPE_CURRENCY,
    AuthorizationJobResults,
    CaptureJobResults,
    CaptureRetryResults,
    NoShowResolutionResults,
    PaymentTasksFacadeApi,
    RetryJobResults,
    _get_booking_end_utc,
    _get_booking_start_utc,
    _should_retry_auth,
    _should_retry_capture,
    has_event_type,
    logger,
    mark_child_booking_settled_impl,
    resolve_locked_booking_from_task_impl,
    typed_task,
)


def _facade_api() -> PaymentTasksFacadeApi:
    return cast(PaymentTasksFacadeApi, sys.modules[__name__])


def _resolve_locked_booking_from_task(locked_booking_id: str, resolution: str) -> Dict[str, Any]:
    return resolve_locked_booking_from_task_impl(_facade_api(), locked_booking_id, resolution)


def _mark_child_booking_settled(booking_id: str) -> None:
    mark_child_booking_settled_impl(_facade_api(), booking_id)


def _process_authorization_for_booking(
    booking_id: str,
    hours_until_lesson: float,
) -> Dict[str, Any]:
    """Process payment authorization for a single booking."""
    from app.database import SessionLocal

    api = _facade_api()
    # ========== PHASE 1: Read booking and validate (quick transaction) ==========
    db1: Session = SessionLocal()
    phase1_error: Optional[str] = None
    payment_method_id: Optional[str] = None
    existing_payment_intent_id: Optional[str] = None
    try:
        phase1 = authorization.load_auth_booking_context(api, db1, booking_id)
        if phase1.get("result") is not None:
            phase1_result = cast(Dict[str, Any], phase1["result"])
            if phase1_result.get("error") != "Booking not found":
                db1.commit()
            return phase1_result
        phase1_error = phase1.get("phase1_error")
        payment_method_id = phase1.get("payment_method_id")
        existing_payment_intent_id = phase1.get("existing_payment_intent_id")
        db1.commit()
    finally:
        db1.close()
    if phase1_error:
        stripe_result: Dict[str, Any] = {
            "success": False,
            "error": phase1_error,
            "error_type": "validation_error",
        }
    else:
        # ========== PHASE 2: Stripe authorization (NO transaction) ==========
        stripe_result = {"success": False}
        try:
            db_stripe: Session = SessionLocal()
            try:
                stripe_service = StripeService(
                    db_stripe,
                    config_service=ConfigService(db_stripe),
                    pricing_service=PricingService(db_stripe),
                )
                ctx = stripe_service.build_charge_context(
                    booking_id=booking_id, requested_credit_cents=None
                )
                if ctx.student_pay_cents <= 0:
                    stripe_result = authorization.build_auth_credits_only_result(ctx)
                elif existing_payment_intent_id:
                    payment_record = stripe_service.confirm_payment_intent(
                        existing_payment_intent_id, payment_method_id
                    )
                    if getattr(payment_record, "status", None) not in {
                        "requires_capture",
                        "succeeded",
                    }:
                        raise ServiceException(
                            f"Unexpected PaymentIntent status: {getattr(payment_record, 'status', None)}"
                        )
                    stripe_result = authorization.build_auth_success_result(
                        ctx, existing_payment_intent_id
                    )
                else:
                    if not payment_method_id:
                        raise ServiceException("Payment method required for authorization")
                    payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                        booking_id=booking_id,
                        payment_method_id=payment_method_id,
                        requested_credit_cents=None,
                    )
                    stripe_result = authorization.build_auth_success_result(
                        ctx, getattr(payment_intent, "id", None)
                    )
                db_stripe.commit()
            finally:
                db_stripe.close()
        except Exception as exc:
            stripe_result = authorization.classify_auth_exception(exc)
    # ========== PHASE 3: Write results (quick transaction) ==========
    db3: Session = SessionLocal()
    try:
        stripe_result = authorization.persist_authorization_result(
            api, db3, booking_id, hours_until_lesson, stripe_result
        )
    finally:
        db3.close()
    authorization.maybe_enqueue_immediate_auth_timeout(
        api, booking_id, hours_until_lesson, stripe_result
    )
    return stripe_result


@typed_task(
    bind=True,
    max_retries=3,
    name="app.tasks.payment_tasks.process_scheduled_authorizations",
)
@monitor_if_configured("process-scheduled-authorizations")
def process_scheduled_authorizations(self: Any) -> AuthorizationJobResults:
    return authorization.process_scheduled_authorizations_impl(_facade_api())


def _mark_booking_payment_failed(
    booking_id: str,
    hours_until_lesson: float,
    now: datetime,
) -> bool:
    return authorization_retry.mark_booking_payment_failed_impl(
        _facade_api(),
        booking_id,
        hours_until_lesson,
        now,
    )


def _cancel_booking_payment_failed(
    booking_id: str,
    hours_until_lesson: float,
    now: datetime,
) -> bool:
    """Backward-compatible alias for tests and older call sites."""
    return _mark_booking_payment_failed(booking_id, hours_until_lesson, now)


def _process_retry_authorization(
    booking_id: str,
    hours_until_lesson: float,
) -> Dict[str, Any]:
    """Process authorization retry for a single booking."""
    from app.database import SessionLocal

    api = _facade_api()
    # ========== PHASE 1: Read retry context (quick transaction) ==========
    db1: Session = SessionLocal()
    payment_method_id: Optional[str] = None
    try:
        phase1 = authorization_retry.load_retry_context(api, db1, booking_id)
        if phase1.get("result") is not None:
            phase1_result = cast(Dict[str, Any], phase1["result"])
            if phase1_result.get("error") != "Booking not found":
                db1.commit()
            return phase1_result
        payment_method_id = phase1.get("payment_method_id")
        db1.commit()
    finally:
        db1.close()
    # ========== PHASE 2: Stripe retry (NO transaction) ==========
    stripe_result: Dict[str, Any] = {"success": False}
    try:
        db_stripe: Session = SessionLocal()
        try:
            stripe_service = StripeService(
                db_stripe,
                config_service=ConfigService(db_stripe),
                pricing_service=PricingService(db_stripe),
            )
            ctx = stripe_service.build_charge_context(
                booking_id=booking_id, requested_credit_cents=None
            )
            if ctx.student_pay_cents <= 0:
                stripe_result = authorization_retry.build_retry_credits_only_result(ctx)
            else:
                payment_intent = stripe_service.create_or_retry_booking_payment_intent(
                    booking_id=booking_id,
                    payment_method_id=payment_method_id,
                    requested_credit_cents=None,
                )
                stripe_result = authorization_retry.build_retry_success_result(
                    ctx, getattr(payment_intent, "id", None)
                )
            db_stripe.commit()
        finally:
            db_stripe.close()
    except Exception as exc:
        stripe_result = {"success": False, "error": str(exc)}
    # ========== PHASE 3: Write results (quick transaction) ==========
    db3: Session = SessionLocal()
    try:
        return authorization_retry.persist_retry_result(
            api, db3, booking_id, hours_until_lesson, stripe_result
        )
    finally:
        db3.close()


@typed_task(bind=True, max_retries=5, name="app.tasks.payment_tasks.retry_failed_authorizations")
@monitor_if_configured("retry-failed-authorizations")
def retry_failed_authorizations(self: Any) -> RetryJobResults:
    return authorization_retry.retry_failed_authorizations_impl(_facade_api())


@typed_task(name="app.tasks.payment_tasks.check_immediate_auth_timeout")
def check_immediate_auth_timeout(booking_id: str) -> Dict[str, Any]:
    return authorization.check_immediate_auth_timeout_impl(_facade_api(), booking_id)


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.retry_failed_captures")
@monitor_if_configured("retry-failed-captures")
def retry_failed_captures(self: Any) -> CaptureRetryResults:
    return capture_recovery.retry_failed_captures_impl(_facade_api())


def _escalate_capture_failure(booking_id: str, now: datetime) -> None:
    capture_recovery.escalate_capture_failure_impl(_facade_api(), booking_id, now)


def handle_authorization_failure(
    booking: Booking,
    payment_repo: Any,
    error: str,
    error_type: str,
    hours_until_lesson: float,
) -> None:
    authorization.handle_authorization_failure_impl(
        _facade_api(),
        booking,
        payment_repo,
        error,
        error_type,
        hours_until_lesson,
    )


def attempt_authorization_retry(
    booking: Booking,
    payment_repo: Any,
    db: Session,
    hours_until_lesson: float,
    stripe_service: StripeService,
) -> bool:
    return authorization_retry.attempt_authorization_retry_impl(
        _facade_api(),
        booking,
        payment_repo,
        db,
        hours_until_lesson,
        stripe_service,
    )


def _process_capture_for_booking(
    booking_id: str,
    capture_reason: str,
) -> Dict[str, Any]:
    """Process payment capture for a single booking."""
    from app.database import SessionLocal

    api = _facade_api()
    # ========== PHASE 1: Read booking data (quick transaction) ==========
    db1: Session = SessionLocal()
    payment_intent_id: Optional[str] = None
    try:
        phase1 = capture.load_capture_context(api, db1, booking_id, capture_reason)
        if phase1.get("result") is not None:
            phase1_result = cast(Dict[str, Any], phase1["result"])
            if phase1_result.get("error") != "Booking not found":
                db1.commit()
            return phase1_result
        if phase1.get("locked_booking_id"):
            db1.commit()
            lock_result = api._resolve_locked_booking_from_task(
                phase1["locked_booking_id"], "new_lesson_completed"
            )
            if lock_result.get("success") or lock_result.get("skipped"):
                api._mark_child_booking_settled(booking_id)
            return {
                "success": True,
                "skipped": True,
                "reason": "locked_funds",
                "lock_result": lock_result,
            }
        payment_intent_id = phase1.get("payment_intent_id")
        db1.commit()
    finally:
        db1.close()
    if payment_intent_id is None:
        return {"success": False, "error": "No payment_intent_id"}
    # ========== PHASE 2: Stripe call (NO transaction) ==========
    stripe_result: Dict[str, Any] = {"success": False}
    try:
        db_stripe: Session = SessionLocal()
        try:
            stripe_service = StripeService(
                db_stripe,
                config_service=ConfigService(db_stripe),
                pricing_service=PricingService(db_stripe),
            )
            db_stripe.commit()
        finally:
            db_stripe.close()
        capture_payload = stripe_service.capture_booking_payment_intent(
            booking_id=booking_id,
            payment_intent_id=payment_intent_id,
            idempotency_key=f"capture_{capture_reason}_{booking_id}_{payment_intent_id}",
        )
        stripe_result = capture.build_capture_success_result(payment_intent_id, capture_payload)
    except Exception as exc:
        stripe_result = capture.classify_capture_exception(api, exc)
    # ========== PHASE 3: Write results (quick transaction) ==========
    db3: Session = SessionLocal()
    try:
        return capture.persist_capture_result(
            api, db3, booking_id, capture_reason, payment_intent_id, stripe_result
        )
    finally:
        db3.close()


def _auto_complete_booking(booking_id: str, now: datetime) -> Dict[str, Any]:
    return capture_orchestration.auto_complete_booking_impl(_facade_api(), booking_id, now)


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.capture_completed_lessons")
@monitor_if_configured("capture-completed-lessons")
def capture_completed_lessons(self: Any) -> CaptureJobResults:
    return capture_orchestration.capture_completed_lessons_impl(_facade_api())


def attempt_payment_capture(
    booking: Booking,
    payment_repo: Any,
    capture_reason: str,
    stripe_service: StripeService,
) -> Dict[str, Any]:
    return capture.attempt_payment_capture_impl(
        _facade_api(),
        booking,
        payment_repo,
        capture_reason,
        stripe_service,
    )


def create_new_authorization_and_capture(
    booking: Booking,
    payment_repo: Any,
    db: Session,
    *,
    lock_acquired: bool = False,
) -> Dict[str, Any]:
    return capture_reauth.create_new_authorization_and_capture_impl(
        _facade_api(),
        booking,
        payment_repo,
        db,
        lock_acquired=lock_acquired,
    )


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.capture_late_cancellation")
def capture_late_cancellation(self: Any, booking_id: Union[int, str]) -> Dict[str, Any]:
    return late_cancel_noshow.capture_late_cancellation_impl(_facade_api(), self, booking_id)


@typed_task(name="app.tasks.payment_tasks.resolve_undisputed_no_shows")
@monitor_if_configured("resolve-undisputed-no-shows")
def resolve_undisputed_no_shows() -> NoShowResolutionResults:
    return late_cancel_noshow.resolve_undisputed_no_shows_impl(_facade_api())


@typed_task(name="app.tasks.payment_tasks.check_authorization_health")
@monitor_if_configured("payment-health-check")
def check_authorization_health() -> Dict[str, Any]:
    return maintenance.check_authorization_health_impl(_facade_api())


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.evaluate_instructor_tiers")
def evaluate_instructor_tiers(self: Any) -> TierEvaluationResults:
    return cast(
        TierEvaluationResults, maintenance.evaluate_instructor_tiers_impl(_facade_api(), self)
    )


@typed_task(bind=True, max_retries=3, name="app.tasks.payment_tasks.audit_and_fix_payout_schedules")
@monitor_if_configured("payout-schedule-audit")
def audit_and_fix_payout_schedules(self: Any) -> Dict[str, Any]:
    return maintenance.audit_and_fix_payout_schedules_impl(_facade_api(), self)


__all__ = [
    "AuthorizationJobResults",
    "Booking",
    "BookingRepository",
    "BookingService",
    "CaptureJobResults",
    "CaptureRetryResults",
    "ConfigService",
    "datetime",
    "NotificationService",
    "NoShowResolutionResults",
    "PricingService",
    "RepositoryFactory",
    "RetryJobResults",
    "STRIPE_CURRENCY",
    "StripeService",
    "StudentCreditService",
    "TimezoneService",
    "_auto_complete_booking",
    "_cancel_booking_payment_failed",
    "_mark_booking_payment_failed",
    "_escalate_capture_failure",
    "_facade_api",
    "_get_booking_end_utc",
    "_get_booking_start_utc",
    "_mark_child_booking_settled",
    "_process_authorization_for_booking",
    "_process_capture_for_booking",
    "_process_retry_authorization",
    "_resolve_locked_booking_from_task",
    "_should_retry_auth",
    "_should_retry_capture",
    "attempt_authorization_retry",
    "attempt_payment_capture",
    "audit_and_fix_payout_schedules",
    "booking_lock_sync",
    "capture_completed_lessons",
    "capture_late_cancellation",
    "check_authorization_health",
    "check_immediate_auth_timeout",
    "create_new_authorization_and_capture",
    "evaluate_instructor_tiers",
    "get_db",
    "handle_authorization_failure",
    "has_event_type",
    "logger",
    "process_scheduled_authorizations",
    "resolve_undisputed_no_shows",
    "retry_failed_authorizations",
    "retry_failed_captures",
    "stripe",
    "typed_task",
]
