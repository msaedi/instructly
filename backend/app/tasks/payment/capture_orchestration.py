"""Capture orchestration and escalation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence, cast

from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus, PaymentStatus
from app.models.payment import PaymentEvent
from app.tasks.payment.common import CaptureJobResults, PaymentTasksFacadeApi


def complete_booking_status(
    api: PaymentTasksFacadeApi,
    db: Session,
    booking_id: str,
    now: datetime,
) -> Dict[str, Any]:
    booking = api.BookingRepository(db).get_by_id(booking_id)
    if not booking:
        return {"success": False, "error": "Booking not found"}
    if booking.status in {BookingStatus.CANCELLED, BookingStatus.PAYMENT_FAILED}:
        return {"success": True, "auto_completed": False, "skipped": True, "reason": "terminal"}
    payment = booking.payment_detail
    if getattr(payment, "payment_status", None) == PaymentStatus.MANUAL_REVIEW.value:
        return {"success": True, "auto_completed": False, "skipped": True, "reason": "disputed"}
    if (
        booking.status != BookingStatus.CONFIRMED
        and getattr(booking, "has_locked_funds", False) is not True
    ):
        return {"success": True, "auto_completed": False, "skipped": True, "reason": "not_eligible"}
    if (
        getattr(payment, "payment_status", None) != PaymentStatus.AUTHORIZED.value
        and getattr(booking, "has_locked_funds", False) is not True
    ):
        return {"success": True, "auto_completed": False, "skipped": True, "reason": "not_eligible"}
    lesson_end = api._get_booking_end_utc(booking)
    booking.mark_completed(completed_at=lesson_end)
    api.StudentCreditService(db).maybe_issue_milestone_credit(
        student_id=booking.student_id, booking_id=booking.id
    )
    api.RepositoryFactory.create_payment_repository(db).create_payment_event(
        booking_id=booking.id,
        event_type="auto_completed",
        event_data={
            "reason": "No instructor confirmation within 24hr",
            "lesson_end": lesson_end.isoformat(),
            "auto_completed_at": now.isoformat(),
        },
    )
    db.commit()
    return {
        "success": True,
        "payment_intent_id": getattr(payment, "payment_intent_id", None),
        "has_locked_funds": getattr(booking, "has_locked_funds", False) is True,
        "locked_parent_id": booking.rescheduled_from_booking_id,
        "instructor_id": booking.instructor_id,
        "completed_booking_id": booking.id,
        "completed_at": booking.completed_at,
    }


def run_post_completion_side_effects(
    api: PaymentTasksFacadeApi,
    db: Session,
    completion_context: Dict[str, Any],
) -> None:
    try:
        from app.services.referral_service import ReferralService

        ReferralService(db).on_instructor_lesson_completed(
            instructor_user_id=completion_context["instructor_id"],
            booking_id=completion_context["completed_booking_id"],
            completed_at=completion_context["completed_at"],
        )
    except Exception as exc:
        api.logger.error(
            "Failed to process instructor referral for auto-completed booking %s: %s",
            completion_context["completed_booking_id"],
            exc,
            exc_info=True,
        )
    try:
        api.PricingService(db).evaluate_and_persist_instructor_tier(
            instructor_user_id=completion_context["instructor_id"]
        )
    except Exception as exc:
        api.logger.error(
            "Failed to refresh instructor tier for auto-completed booking %s: %s",
            completion_context["completed_booking_id"],
            exc,
            exc_info=True,
        )


def finalize_auto_completion_capture(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    completion_context: Dict[str, Any],
) -> Dict[str, Any]:
    if completion_context.get("has_locked_funds") and completion_context.get("locked_parent_id"):
        lock_result = api._resolve_locked_booking_from_task(
            completion_context["locked_parent_id"],
            "new_lesson_completed",
        )
        if lock_result.get("success") or lock_result.get("skipped"):
            api._mark_child_booking_settled(booking_id)
        return {
            "success": True,
            "auto_completed": True,
            "captured": bool(lock_result.get("success") or lock_result.get("skipped")),
            "capture_attempted": True,
            "lock_result": lock_result,
        }
    if not completion_context.get("payment_intent_id"):
        api.logger.warning("Skipping capture for booking %s: no payment_intent_id", booking_id)
        return {
            "success": True,
            "auto_completed": True,
            "captured": False,
            "capture_attempted": False,
        }
    capture_result = api._process_capture_for_booking(booking_id, "auto_completed")
    return {
        "success": True,
        "auto_completed": True,
        "captured": capture_result.get("success", False),
        "capture_attempted": True,
    }


def auto_complete_booking_impl(
    api: PaymentTasksFacadeApi, booking_id: str, now: datetime
) -> Dict[str, Any]:
    """Auto-complete a booking and capture payment."""
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        completion_context = complete_booking_status(api, db, booking_id, now)
        if not completion_context.get("success") or completion_context.get("skipped"):
            return completion_context
        run_post_completion_side_effects(api, db, completion_context)
    finally:
        db.close()
    return finalize_auto_completion_capture(api, booking_id, completion_context)


def collect_capture_candidates(
    api: PaymentTasksFacadeApi,
    db: Session,
    now: datetime,
) -> Dict[str, Any]:
    booking_repo = api.RepositoryFactory.create_booking_repository(db)
    payment_repo = api.RepositoryFactory.create_payment_repository(db)
    capture_cutoff = now - timedelta(hours=24)
    auto_complete_cutoff = now - timedelta(hours=24)
    seven_days_ago = now - timedelta(days=7)
    capture_booking_ids = [
        booking.id
        for booking in cast(Sequence[Booking], booking_repo.get_bookings_for_payment_capture())
        if api._get_booking_end_utc(booking) <= capture_cutoff
        and (getattr(booking.payment_detail, "payment_intent_id", None) or booking.has_locked_funds)
    ]
    auto_complete_booking_ids = [
        booking.id
        for booking in cast(Sequence[Booking], booking_repo.get_bookings_for_auto_completion())
        if api._get_booking_end_utc(booking) <= auto_complete_cutoff
    ]
    expired_auth_data: List[Dict[str, Any]] = []
    for booking in cast(Sequence[Booking], booking_repo.get_bookings_with_expired_auth()):
        auth_events = cast(
            Sequence[PaymentEvent], payment_repo.get_payment_events_for_booking(booking.id)
        )
        auth_event = next(
            (
                event
                for event in auth_events
                if event.event_type in ["auth_succeeded", "auth_retry_succeeded"]
            ),
            None,
        )
        if auth_event and auth_event.created_at <= seven_days_ago:
            expired_auth_data.append(
                {
                    "booking_id": booking.id,
                    "status": booking.status,
                    "auth_created_at": auth_event.created_at.isoformat(),
                }
            )
    return {
        "capture_booking_ids": capture_booking_ids,
        "auto_complete_booking_ids": auto_complete_booking_ids,
        "expired_auth_data": expired_auth_data,
    }


def _process_completed_capture(
    api: PaymentTasksFacadeApi, booking_id: str, results: CaptureJobResults
) -> None:
    with api.booking_lock_sync(booking_id) as acquired:
        if not acquired:
            return
        capture_result = api._process_capture_for_booking(booking_id, "instructor_completed")
    if capture_result.get("success"):
        results["captured"] += 1
    elif not capture_result.get("skipped"):
        results["failed"] += 1


def _process_auto_complete(
    api: PaymentTasksFacadeApi, booking_id: str, now: datetime, results: CaptureJobResults
) -> None:
    with api.booking_lock_sync(booking_id) as acquired:
        if not acquired:
            return
        auto_result = api._auto_complete_booking(booking_id, now)
    if auto_result.get("auto_completed"):
        results["auto_completed"] += 1
    if auto_result.get("captured"):
        results["captured"] += 1
    elif auto_result.get("capture_attempted") and not auto_result.get("captured"):
        results["failed"] += 1


def _handle_expired_auth_booking(
    api: PaymentTasksFacadeApi,
    booking_id: str,
    expired_data: Dict[str, Any],
    now: datetime,
    results: CaptureJobResults,
) -> None:
    from app.database import SessionLocal

    db_expired: Session = SessionLocal()
    try:
        repo = api.BookingRepository(db_expired)
        booking = repo.get_by_id(booking_id)
        if not booking or booking.status in {BookingStatus.CANCELLED, BookingStatus.PAYMENT_FAILED}:
            return
        payment = booking.payment_detail
        if getattr(payment, "payment_status", None) in {PaymentStatus.MANUAL_REVIEW.value, None}:
            return
        if getattr(payment, "payment_status", None) != PaymentStatus.AUTHORIZED.value:
            return
        if booking.status == BookingStatus.COMPLETED:
            capture_result = api._process_capture_for_booking(booking_id, "expired_auth")
            if capture_result.get("success"):
                results["captured"] += 1
            else:
                payment_repo = api.RepositoryFactory.create_payment_repository(db_expired)
                new_auth_result = api.create_new_authorization_and_capture(
                    booking,
                    payment_repo,
                    db_expired,
                    lock_acquired=True,
                )
                db_expired.commit()
                if new_auth_result["success"]:
                    results["captured"] += 1
                else:
                    results["failed"] += 1
        else:
            payment_record = repo.ensure_payment(booking.id)
            payment_record.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
            payment_record.capture_failed_at = now
            payment_record.capture_retry_count = (
                int(getattr(payment_record, "capture_retry_count", 0) or 0) + 1
            )
            api.RepositoryFactory.create_payment_repository(db_expired).create_payment_event(
                booking_id=booking_id,
                event_type="auth_expired",
                event_data={
                    "payment_intent_id": getattr(payment, "payment_intent_id", None),
                    "expired_at": now.isoformat(),
                    "auth_created_at": expired_data["auth_created_at"],
                },
            )
            db_expired.commit()
        results["expired_handled"] += 1
    finally:
        db_expired.close()


def capture_completed_lessons_impl(api: PaymentTasksFacadeApi) -> CaptureJobResults:
    """Capture payments for completed lessons."""
    from app.database import SessionLocal

    now = api.datetime.now(timezone.utc)
    results: CaptureJobResults = {
        "captured": 0,
        "failed": 0,
        "auto_completed": 0,
        "expired_handled": 0,
        "processed_at": now.isoformat(),
    }
    db_read: Session = SessionLocal()
    try:
        candidate_data = collect_capture_candidates(api, db_read, now)
        db_read.commit()
    finally:
        db_read.close()
    for booking_id in candidate_data["capture_booking_ids"]:
        try:
            _process_completed_capture(api, booking_id, results)
        except Exception as exc:
            api.logger.error("Error processing capture for booking %s: %s", booking_id, exc)
            results["failed"] += 1
    for booking_id in candidate_data["auto_complete_booking_ids"]:
        try:
            _process_auto_complete(api, booking_id, now, results)
        except Exception as exc:
            api.logger.error("Error auto-completing booking %s: %s", booking_id, exc)
            results["failed"] += 1
    for expired_data in candidate_data["expired_auth_data"]:
        booking_id = expired_data["booking_id"]
        try:
            with api.booking_lock_sync(booking_id) as acquired:
                if not acquired:
                    continue
                _handle_expired_auth_booking(api, booking_id, expired_data, now, results)
        except Exception as exc:
            api.logger.error("Error handling expired auth for booking %s: %s", booking_id, exc)
            results["failed"] += 1
    api.logger.info(
        "Capture job completed: %s captured, %s failed, %s auto-completed, %s expired handled",
        results["captured"],
        results["failed"],
        results["auto_completed"],
        results["expired_handled"],
    )
    return results
