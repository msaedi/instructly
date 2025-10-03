"""Checkr webhook endpoints for background check updates."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..api.dependencies.repositories import get_instructor_repo
from ..core.config import settings
from ..database import SessionLocal
from ..models.instructor import InstructorProfile
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.webhook_responses import WebhookAckResponse
from ..services.email import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/checkr", tags=["webhooks"])

FINAL_ADVERSE_DELAY = timedelta(days=5)
SUMMARY_OF_RIGHTS_URL = "https://www.consumerfinance.gov/rules-policy/regulations/603/"


def _compute_signature(secret: str, payload: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload, sha256)
    return mac.hexdigest()


def _verify_signature(payload: bytes, signature: str | None) -> None:
    secret_value = settings.checkr_webhook_secret.get_secret_value()
    if not secret_value:
        logger.error("Checkr webhook secret is not configured")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook secret not configured",
        )

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Checkr-Signature header",
        )

    expected = _compute_signature(secret_value, payload)
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )


@router.post("/", response_model=WebhookAckResponse)
async def handle_checkr_webhook(
    request: Request,
    repository: InstructorProfileRepository = Depends(get_instructor_repo),
) -> WebhookAckResponse:
    """Process Checkr webhook events for background check reports."""

    raw_body = await request.body()
    signature = request.headers.get("X-Checkr-Signature")

    _verify_signature(raw_body, signature)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = payload.get("type", "")
    data_object = payload.get("data", {}).get("object", {}) or {}
    report_id = data_object.get("id")

    logger.info("Checkr webhook received", extra={"event_type": event_type, "report_id": report_id})

    if not event_type:
        return WebhookAckResponse(ok=True)

    if event_type == "report.completed":
        if not report_id:
            return WebhookAckResponse(ok=True)

        result = (data_object.get("result") or data_object.get("adjudication") or "").lower()
        profile = repository.find_one_by(bgc_report_id=report_id)

        status_value = "passed" if result == "clear" else "review"
        repository.update_bgc_by_report_id(
            report_id,
            status=status_value,
            completed_at=datetime.now(timezone.utc),
        )

        if status_value == "review" and profile:
            _handle_non_clear_report(profile)

        return WebhookAckResponse(ok=True)

    if event_type == "report.suspended":
        if not report_id:
            return WebhookAckResponse(ok=True)

        repository.update_bgc_by_report_id(
            report_id,
            status="review",
            completed_at=None,
        )
        return WebhookAckResponse(ok=True)

    # Other event types are acknowledged but ignored
    logger.debug("Ignoring unsupported Checkr webhook event", extra={"event_type": event_type})
    return WebhookAckResponse(ok=True)


def _send_email(subject: str, html_body: str, recipient: str) -> None:
    if settings.bgc_suppress_adverse_emails:
        logger.info(
            "Adverse-action email suppressed by configuration",
            extra={"recipient": recipient, "subject": subject},
        )
        return

    session = SessionLocal()
    try:
        email_service = EmailService(session)
        email_service.send_email(recipient, subject, html_body)
    except Exception as exc:  # pragma: no cover - logging only
        logger.error("Failed to send adverse-action email: %s", str(exc))
    finally:
        session.close()


def _send_pre_adverse_email(profile: InstructorProfile) -> None:
    user = getattr(profile, "user", None)
    recipient = getattr(user, "email", None)
    if not recipient:
        logger.warning(
            "Skipping pre-adverse email; missing recipient", extra={"profile": profile.id}
        )
        return

    html = (
        "<p>We are reviewing your background check results and wanted to let you know. "
        "This is a pre-adverse action notice. Please review the attached report and your "
        f"rights: <a href='{SUMMARY_OF_RIGHTS_URL}'>Summary of Rights under the FCRA</a>. "
        "If you believe the report is inaccurate, contact us within five business days to initiate a dispute."
        "</p>"
    )

    _send_email("Background check under review", html, recipient)


def _send_final_adverse_email(profile: InstructorProfile) -> None:
    user = getattr(profile, "user", None)
    recipient = getattr(user, "email", None)
    if not recipient:
        logger.warning(
            "Skipping final adverse email; missing recipient", extra={"profile": profile.id}
        )
        return

    html = (
        "<p>We completed our review of your background report. Unfortunately, we are unable to move forward."
        " You have already received a copy of your report and the Summary of Rights under the FCRA. "
        "If you would like to dispute the findings, please reach out to support@instainstru.com."
        "</p>"
    )

    _send_email("Background check decision", html, recipient)


async def _finalize_after_delay(profile_id: str, delay: timedelta) -> None:
    await asyncio.sleep(max(delay.total_seconds(), 0))
    await asyncio.to_thread(_execute_final_adverse_action, profile_id)


def schedule_final_adverse_action(profile_id: str) -> None:
    if getattr(settings, "is_testing", False) or not getattr(settings, "scheduler_enabled", True):
        logger.debug(
            "Skipping final adverse action scheduling",
            extra={"profile_id": profile_id, "reason": "scheduler_disabled"},
        )
        return

    if str(settings.site_mode).lower() == "prod":
        logger.info(
            "Phase-2 TODO: enqueue persisted final adverse action task",
            extra={"profile_id": profile_id},
        )
        return

    loop = asyncio.get_event_loop()
    loop.create_task(_finalize_after_delay(profile_id, FINAL_ADVERSE_DELAY))


def _execute_final_adverse_action(profile_id: str) -> None:
    session = SessionLocal()
    try:
        repo = InstructorProfileRepository(session)
        profile = repo.get_by_id(profile_id, load_relationships=True)
        if not profile:
            logger.warning(
                "Final adverse action skipped; profile missing", extra={"profile_id": profile_id}
            )
            return

        current_status = (getattr(profile, "bgc_status", "") or "").lower()
        if current_status != "review":
            logger.info(
                "Final adverse action skipped; status changed",
                extra={"profile_id": profile_id, "status": current_status},
            )
            return

        profile.bgc_status = "failed"
        profile.bgc_completed_at = datetime.now(timezone.utc)
        session.flush()
        session.commit()
        _send_final_adverse_email(profile)
    except Exception as exc:  # pragma: no cover - safety logging
        logger.error("Failed to complete final adverse action: %s", str(exc))
        session.rollback()
    finally:
        session.close()


def _handle_non_clear_report(profile: InstructorProfile) -> None:
    _send_pre_adverse_email(profile)
    schedule_final_adverse_action(profile.id)
