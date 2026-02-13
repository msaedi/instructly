"""Celery tasks for instructor referral payouts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable, Dict, ParamSpec, Protocol, TypeVar, cast

from celery.result import AsyncResult

from app.database import get_db_session
from app.models.referrals import InstructorReferralPayout
from app.monitoring.sentry_crons import monitor_if_configured
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.config_service import ConfigService
from app.services.pricing_service import PricingService
from app.services.stripe_service import StripeService
from app.tasks.celery_app import celery_app
from app.tasks.enqueue import enqueue_task

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class TaskWrapper(Protocol[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        ...

    delay: "Callable[..., AsyncResult[Any]]"
    apply_async: "Callable[..., AsyncResult[Any]]"


def typed_task(
    *task_args: Any, **task_kwargs: Any
) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]:
    """Return a typed Celery task decorator for mypy."""

    return cast(
        Callable[[Callable[P, R]], TaskWrapper[P, R]],
        celery_app.task(*task_args, **task_kwargs),
    )


@typed_task(
    bind=True,
    max_retries=3,
    name="app.tasks.referral_tasks.process_instructor_referral_payout",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
)
def process_instructor_referral_payout(self: Any, payout_id: str) -> Dict[str, Any]:
    """
    Process a pending instructor referral payout via Stripe Transfer.

    Idempotent: safe to retry on failure and skips already completed payouts.
    """
    logger.info("Processing instructor referral payout %s", payout_id)

    failure_exc: Exception | None = None
    with get_db_session() as db:
        payout = (  # repo-pattern-migrate: TODO: move to ReferralRepository
            db.query(
                InstructorReferralPayout
            )  # repo-pattern-migrate: TODO: move to ReferralRepository
            .filter(
                InstructorReferralPayout.id == payout_id
            )  # repo-pattern-migrate: referral payout query
            .with_for_update()
            .first()  # repo-pattern-migrate: referral payout query
        )
        if not payout:
            logger.error("Payout not found: %s", payout_id)
            return {"status": "error", "reason": "payout_not_found"}

        if payout.stripe_transfer_status == "completed":
            logger.info(
                "Payout already completed: %s transfer_id=%s",
                payout_id,
                payout.stripe_transfer_id,
            )
            return {
                "status": "already_completed",
                "transfer_id": payout.stripe_transfer_id,
            }

        instructor_repo = InstructorProfileRepository(db)
        referrer_profile = instructor_repo.get_by_user_id(payout.referrer_user_id)
        if not referrer_profile:
            logger.error("Referrer profile not found: %s", payout.referrer_user_id)
            _mark_payout_failed(payout, "referrer_profile_not_found")
            return {"status": "error", "reason": "referrer_profile_not_found"}

        stripe_account = referrer_profile.stripe_connected_account
        if not stripe_account:
            logger.error("Referrer has no Stripe account: %s", payout.referrer_user_id)
            _mark_payout_failed(payout, "referrer_no_stripe_account")
            return {"status": "error", "reason": "no_stripe_account"}

        if not getattr(stripe_account, "onboarding_completed", True):
            logger.warning("Referrer Stripe onboarding incomplete: %s", payout.referrer_user_id)
            _mark_payout_failed(payout, "referrer_stripe_not_onboarded")
            return {"status": "error", "reason": "stripe_not_onboarded"}

        destination_account_id = stripe_account.stripe_account_id

        stripe_service = StripeService(
            db,
            config_service=ConfigService(db),
            pricing_service=PricingService(db),
        )
        try:
            transfer = stripe_service.create_referral_bonus_transfer(
                payout_id=payout_id,
                destination_account_id=destination_account_id,
                amount_cents=payout.amount_cents,
                referrer_user_id=payout.referrer_user_id,
                referred_instructor_id=payout.referred_instructor_id,
                was_founding_bonus=payout.was_founding_bonus,
            )
            transfer_id = None
            if isinstance(transfer, dict):
                transfer_id = transfer.get("transfer_id") or transfer.get("id")
            if transfer_id is None:
                transfer_id = getattr(transfer, "id", None)

            if not transfer_id:
                logger.error("Stripe transfer returned no ID for payout %s", payout_id)
                _mark_payout_failed(payout, "stripe_transfer_no_id")
                return {"status": "error", "reason": "no_transfer_id"}

            payout.stripe_transfer_id = transfer_id
            payout.stripe_transfer_status = "completed"
            payout.transferred_at = datetime.now(timezone.utc)

            logger.info(
                "Successfully processed payout %s transfer_id=%s amount_cents=%s",
                payout_id,
                transfer_id,
                payout.amount_cents,
            )
            return {
                "status": "completed",
                "transfer_id": transfer_id,
                "amount_cents": payout.amount_cents,
            }
        except Exception as exc:
            logger.error("Stripe transfer failed for payout %s: %s", payout_id, exc, exc_info=True)
            _mark_payout_failed(payout, str(exc)[:500])
            failure_exc = exc

    if failure_exc:
        raise failure_exc

    return {"status": "error", "reason": "unknown_failure"}


def _mark_payout_failed(payout: InstructorReferralPayout, reason: str) -> None:
    payout.stripe_transfer_status = "failed"
    payout.failed_at = datetime.now(timezone.utc)
    payout.failure_reason = reason


@typed_task(
    name="app.tasks.referral_tasks.retry_failed_instructor_referral_payouts",
    max_retries=0,
)
@monitor_if_configured("retry-failed-instructor-referral-payouts")
def retry_failed_instructor_referral_payouts() -> Dict[str, Any]:
    """Retry failed payouts from the last 7 days."""
    logger.info("Retrying failed instructor referral payouts")

    with get_db_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        failed_payouts = (
            db.query(  # repo-pattern-migrate: TODO: move to ReferralRepository
                InstructorReferralPayout
            )
            .filter(  # repo-pattern-migrate: referral payout query
                InstructorReferralPayout.stripe_transfer_status == "failed",
                InstructorReferralPayout.failed_at >= cutoff,
            )
            .all()
        )

        retried = 0
        for payout in failed_payouts:
            payout.stripe_transfer_status = "pending"
            payout.failed_at = None
            payout.failure_reason = None
            enqueue_task(
                "app.tasks.referral_tasks.process_instructor_referral_payout",
                args=(payout.id,),
            )
            retried += 1

        logger.info("Queued %s failed payouts for retry", retried)
        return {"retried": retried, "checked_since": cutoff.isoformat()}


@typed_task(
    name="app.tasks.referral_tasks.check_pending_instructor_referral_payouts",
    max_retries=0,
)
@monitor_if_configured("check-pending-instructor-referral-payouts")
def check_pending_instructor_referral_payouts() -> Dict[str, Any]:
    """Queue pending payouts older than 5 minutes for processing."""
    logger.info("Checking for pending instructor referral payouts")

    with get_db_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        pending_payouts = (
            db.query(  # repo-pattern-migrate: TODO: move to ReferralRepository
                InstructorReferralPayout
            )
            .filter(  # repo-pattern-migrate: referral payout query
                InstructorReferralPayout.stripe_transfer_status == "pending",
                InstructorReferralPayout.created_at <= cutoff,
            )
            .all()
        )

        queued = 0
        for payout in pending_payouts:
            enqueue_task(
                "app.tasks.referral_tasks.process_instructor_referral_payout",
                args=(payout.id,),
            )
            queued += 1

        logger.info("Queued %s pending payouts for processing", queued)
        return {"queued": queued}
