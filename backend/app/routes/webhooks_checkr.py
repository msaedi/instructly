"""Checkr webhook endpoints for background check updates."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..api.dependencies.repositories import get_background_job_repo
from ..api.dependencies.services import get_background_check_workflow_service
from ..core.config import settings
from ..core.exceptions import RepositoryException
from ..core.metrics import CHECKR_WEBHOOK_TOTAL
from ..repositories.background_job_repository import BackgroundJobRepository
from ..schemas.webhook_responses import WebhookAckResponse
from ..services.background_check_workflow_service import (
    BackgroundCheckWorkflowService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/checkr", tags=["webhooks"])


def _compute_signature(secret: str, payload: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload, sha256)
    return mac.hexdigest()


def _result_label(result: str) -> str:
    normalized = (result or "").lower()
    if normalized == "clear":
        return "clear"
    if normalized == "consider":
        return "consider"
    return "other"


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
    workflow_service: BackgroundCheckWorkflowService = Depends(
        get_background_check_workflow_service
    ),
    job_repository: BackgroundJobRepository = Depends(get_background_job_repo),
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

    if not event_type:
        return WebhookAckResponse(ok=True)

    if event_type == "report.completed":
        if not report_id:
            return WebhookAckResponse(ok=True)

        raw_result = (data_object.get("result") or data_object.get("adjudication") or "").lower()
        normalized_result = {
            "clear": "clear",
            "consider": "consider",
            "suspended": "suspended",
        }.get(raw_result, "unknown")
        result_label = _result_label(normalized_result)

        completed_at = datetime.now(timezone.utc)
        package_value = data_object.get("package") or settings.checkr_package

        try:
            status_value, profile, requires_follow_up = workflow_service.handle_report_completed(
                report_id=report_id,
                result=normalized_result,
                package=package_value,
                env=settings.checkr_env,
                completed_at=completed_at,
            )
            if requires_follow_up and profile is not None:
                logger.info(
                    "Background check requires review",
                    extra={"instructor_id": profile.id, "report_id": report_id},
                )
                workflow_service.schedule_final_adverse_action(profile.id)

            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="success").inc()
            logger.info(
                "Checkr webhook processed",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "result": normalized_result,
                    "report_id": report_id,
                    "outcome": "success",
                },
            )
        except RepositoryException as exc:
            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="queued").inc()
            logger.warning(
                "Background check workflow deferred: %s",
                str(exc),
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "result": normalized_result,
                    "report_id": report_id,
                    "outcome": "queued",
                },
            )
            job_repository.enqueue(
                type="webhook.report_completed",
                payload={
                    "report_id": report_id,
                    "result": normalized_result,
                    "package": package_value,
                    "env": settings.checkr_env,
                    "completed_at": completed_at.isoformat(),
                },
            )
        except Exception:  # pragma: no cover - safety fallback
            CHECKR_WEBHOOK_TOTAL.labels(result=result_label, outcome="error").inc()
            logger.exception(
                "Unhandled error processing report.completed; enqueueing retry",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "result": normalized_result,
                    "report_id": report_id,
                    "outcome": "error",
                },
            )
            job_repository.enqueue(
                type="webhook.report_completed",
                payload={
                    "report_id": report_id,
                    "result": normalized_result,
                    "package": package_value,
                    "env": settings.checkr_env,
                    "completed_at": completed_at.isoformat(),
                },
            )

        return WebhookAckResponse(ok=True)

    if event_type == "report.suspended":
        if not report_id:
            return WebhookAckResponse(ok=True)

        try:
            workflow_service.handle_report_suspended(report_id)
            logger.info(
                "Checkr webhook processed",
                extra={
                    "evt": "checkr_webhook",
                    "type": event_type,
                    "report_id": report_id,
                    "outcome": "success",
                },
            )
        except RepositoryException as exc:
            logger.warning(
                "Unable to process report.suspended event: %s",
                str(exc),
                extra={"report_id": report_id},
            )
        except Exception:  # pragma: no cover - safety fallback
            logger.exception(
                "Unhandled error handling report.suspended",
                extra={"report_id": report_id},
            )
        return WebhookAckResponse(ok=True)

    # Other event types are acknowledged but ignored
    logger.debug("Ignoring unsupported Checkr webhook event", extra={"event_type": event_type})
    return WebhookAckResponse(ok=True)
