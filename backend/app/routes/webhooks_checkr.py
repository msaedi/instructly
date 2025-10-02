"""Checkr webhook endpoints for background check updates."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..api.dependencies.repositories import get_instructor_repo
from ..core.config import settings
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..schemas.webhook_responses import WebhookAckResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/checkr", tags=["webhooks"])


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
        status_value = "passed" if result == "clear" else "review"
        repository.update_bgc_by_report_id(
            report_id,
            status=status_value,
            completed_at=datetime.now(timezone.utc),
        )
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
