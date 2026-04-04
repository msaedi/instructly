"""Payment health checks and maintenance flows."""

from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Optional, Sequence, cast

from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models.booking import Booking
from app.repositories.payment_monitoring_repository import PaymentMonitoringRepository
from app.tasks.payment.common import PaymentTasksFacadeApi, _ensure_stripe_api_key


def _collect_overdue_bookings(
    api: PaymentTasksFacadeApi,
    booking_repo: Any,
) -> List[Dict[str, Any]]:
    overdue_bookings: List[Dict[str, Any]] = []
    scheduled_bookings = cast(
        Sequence[Booking],
        booking_repo.get_bookings_for_payment_authorization(),
    )
    for booking in scheduled_bookings:
        booking_start_utc = api._get_booking_start_utc(booking)
        hours_until_lesson = api.TimezoneService.hours_until(booking_start_utc)
        if hours_until_lesson < 24:
            overdue_bookings.append(
                {
                    "booking_id": booking.id,
                    "hours_until_lesson": round(hours_until_lesson, 1),
                }
            )
    return overdue_bookings


def _get_minutes_since_last_auth(
    api: PaymentTasksFacadeApi,
    db: Session,
    now: Any,
) -> Optional[int]:
    try:
        last_auth_event = PaymentMonitoringRepository(db).get_last_successful_authorization()
    except Exception:
        api.logger.debug(
            "Unable to fetch last authorization event for health check",
            exc_info=True,
        )
        return None
    if last_auth_event is None:
        return None
    return int((now - last_auth_event.created_at).total_seconds() / 60)


def check_authorization_health_impl(api: PaymentTasksFacadeApi) -> Dict[str, Any]:
    """Health check for authorization system."""
    try:
        with get_db_session() as db:
            now = api.datetime.now(timezone.utc)
            booking_repo = api.RepositoryFactory.create_booking_repository(db)
            overdue_bookings = _collect_overdue_bookings(api, booking_repo)
            minutes_since_last_auth = _get_minutes_since_last_auth(api, db, now)
            health_status = {
                "healthy": True,
                "overdue_count": len(overdue_bookings),
                "overdue_bookings": overdue_bookings[:10],
                "minutes_since_last_auth": minutes_since_last_auth,
                "checked_at": now.isoformat(),
            }
            if len(overdue_bookings) > 5:
                health_status["healthy"] = False
                api.logger.error(
                    "ALERT: %s bookings are overdue for authorization", len(overdue_bookings)
                )
            if minutes_since_last_auth and minutes_since_last_auth > 120:
                health_status["healthy"] = False
                api.logger.warning(
                    "No successful authorizations in %s minutes", minutes_since_last_auth
                )
            return health_status
    except Exception as exc:
        api.logger.error("Health check failed: %s", exc)
        return {
            "healthy": False,
            "error": str(exc),
            "checked_at": api.datetime.now(timezone.utc).isoformat(),
        }


def evaluate_instructor_tiers_impl(api: PaymentTasksFacadeApi, task_self: Any) -> Dict[str, Any]:
    """Re-evaluate persisted instructor tiers as a daily safety net."""
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        result = cast(Dict[str, Any], api.PricingService(db).evaluate_active_instructor_tiers())
        api.logger.info("Instructor tier evaluation completed: %s", result)
        return result
    except Exception as exc:
        api.logger.error("Instructor tier evaluation failed: %s", exc)
        raise task_self.retry(exc=exc, countdown=1800)
    finally:
        db.close()


def _audit_payout_schedule_for_account(
    api: PaymentTasksFacadeApi,
    stripe_service: Any,
    account: Any,
) -> bool:
    _ensure_stripe_api_key()
    acct = api.stripe.Account.retrieve(account.stripe_account_id)
    current = getattr(acct, "settings", {}).get("payouts", {}).get("schedule", {})
    interval = current.get("interval")
    weekly_anchor = current.get("weekly_anchor")
    if interval == "weekly" and weekly_anchor == "tuesday":
        return False
    stripe_service.set_payout_schedule_for_account(
        instructor_profile_id=account.instructor_profile_id,
        interval="weekly",
        weekly_anchor="tuesday",
    )
    return True


def audit_and_fix_payout_schedules_impl(
    api: PaymentTasksFacadeApi,
    task_self: Any,
) -> Dict[str, Any]:
    """Nightly audit to ensure all connected accounts use weekly Tuesday payouts."""
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        payment_repo = api.RepositoryFactory.create_payment_repository(db)
        stripe_service = api.StripeService(
            db,
            config_service=api.ConfigService(db),
            pricing_service=api.PricingService(db),
        )
        checked = 0
        fixed = 0
        for account in payment_repo.get_all_connected_accounts():
            checked += 1
            try:
                fixed += int(_audit_payout_schedule_for_account(api, stripe_service, account))
            except Exception as exc:
                api.logger.warning(
                    "Payout schedule audit failed for %s: %s",
                    account.stripe_account_id,
                    exc,
                )
        result = {"checked": checked, "fixed": fixed}
        api.logger.info("Payout schedule audit completed: %s", result)
        return result
    except Exception as exc:
        api.logger.error("Payout schedule audit failed: %s", exc)
        raise task_self.retry(exc=exc, countdown=900)
    finally:
        db.close()
