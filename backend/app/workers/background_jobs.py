from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import threading
import time
from typing import Any, cast

from app.core.config import settings
from app.core.exceptions import NonRetryableError, RepositoryException
from app.core.metrics import (
    BACKGROUND_JOB_FAILURES_TOTAL,
    BACKGROUND_JOBS_FAILED,
    BGC_PENDING_7D,
)
from app.database.sessions import SchedulerSessionLocal
from app.events.handlers import process_event
from app.repositories.background_job_repository import BackgroundJobRepository
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.services.background_check_workflow_service import (
    FINAL_ADVERSE_JOB_TYPE,
    BackgroundCheckWorkflowService,
    FinalAdversePayload,
)

logger = logging.getLogger("app.main")


def _next_expiry_run(now: datetime | None = None) -> datetime:
    reference = now or datetime.now(timezone.utc)
    next_run = reference.replace(hour=3, minute=0, second=0, microsecond=0)
    if next_run <= reference:
        next_run += timedelta(days=1)
    return next_run


def _expiry_recheck_url() -> str:
    base_url = (settings.frontend_url or "").rstrip("/")
    return f"{base_url}/instructor/onboarding/verification"


def _normalize_utc_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        raise RepositoryException(f"Unsupported datetime payload type: {type(value)!r}")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _required_payload_value(payload: dict[str, Any], key: str, error_message: str) -> str:
    value = payload.get(key)
    if not value:
        raise RepositoryException(error_message)
    return str(value)


def _update_failed_jobs_gauge(job_repo: BackgroundJobRepository) -> None:
    BACKGROUND_JOBS_FAILED.set(job_repo.count_failed_jobs())


def _send_recheck_email(
    workflow: BackgroundCheckWorkflowService,
    profile: Any,
    *,
    now_utc: datetime,
    recheck_url: str,
    is_past_due: bool,
) -> None:
    expiry_dt = getattr(profile, "bgc_valid_until", None)
    expiry_dt_utc = _normalize_utc_datetime(expiry_dt) or now_utc
    context: dict[str, object] = {
        "candidate_name": workflow.candidate_name(profile) or "",
        "expiry_date": workflow.format_date(expiry_dt_utc),
        "is_past_due": is_past_due,
        "recheck_url": recheck_url,
        "support_email": settings.bgc_support_email,
    }
    workflow.send_expiry_recheck_email(profile, context)


def _handle_report_completed(
    payload: dict[str, Any],
    workflow: BackgroundCheckWorkflowService,
) -> None:
    workflow.handle_report_completed(
        report_id=_required_payload_value(payload, "report_id", "Missing report_id in job payload"),
        result=str(payload.get("result", "unknown")),
        assessment=payload.get("assessment"),
        package=payload.get("package"),
        env=payload.get("env", settings.checkr_env),
        completed_at=_normalize_utc_datetime(payload.get("completed_at"))
        or datetime.now(timezone.utc),
        candidate_id=payload.get("candidate_id"),
        invitation_id=payload.get("invitation_id"),
        includes_canceled=payload.get("includes_canceled"),
    )


def _handle_report_suspended(
    payload: dict[str, Any],
    workflow: BackgroundCheckWorkflowService,
) -> None:
    report_id = _required_payload_value(
        payload,
        "report_id",
        "Missing report_id in suspended payload",
    )
    workflow.handle_report_suspended(report_id)


def _handle_report_canceled(
    payload: dict[str, Any],
    workflow: BackgroundCheckWorkflowService,
) -> None:
    workflow.handle_report_canceled(
        report_id=_required_payload_value(
            payload,
            "report_id",
            "Missing report_id in canceled payload",
        ),
        env=payload.get("env", settings.checkr_env),
        canceled_at=_normalize_utc_datetime(payload.get("canceled_at"))
        or datetime.now(timezone.utc),
        candidate_id=payload.get("candidate_id"),
        invitation_id=payload.get("invitation_id"),
    )


def _handle_report_eta(
    payload: dict[str, Any],
    workflow: BackgroundCheckWorkflowService,
) -> None:
    workflow.handle_report_eta_updated(
        report_id=_required_payload_value(payload, "report_id", "Missing report_id in ETA payload"),
        env=payload.get("env", settings.checkr_env),
        eta=_normalize_utc_datetime(payload.get("eta")),
        candidate_id=payload.get("candidate_id"),
    )


def _handle_final_adverse(
    payload: dict[str, Any],
    scheduled_at: datetime,
    workflow: BackgroundCheckWorkflowService,
) -> None:
    final_payload = cast(FinalAdversePayload, payload)
    workflow.execute_final_adverse_action(
        final_payload["profile_id"],
        final_payload["pre_adverse_notice_id"],
        scheduled_at,
    )


def _handle_expiry_sweep(
    payload: dict[str, Any],
    job_repo: BackgroundJobRepository,
    repo: InstructorProfileRepository,
    workflow: BackgroundCheckWorkflowService,
) -> None:
    if not getattr(settings, "bgc_expiry_enabled", False):
        logger.info("Skipping bgc.expiry_sweep job because expiry is disabled")
        return

    days = int(payload.get("days", 30))
    BGC_PENDING_7D.set(repo.count_pending_older_than(7))

    now_utc = datetime.now(timezone.utc)
    recheck_url = _expiry_recheck_url()

    for profile in repo.list_expiring_within(days):
        _send_recheck_email(
            workflow,
            profile,
            now_utc=now_utc,
            recheck_url=recheck_url,
            is_past_due=False,
        )

    for profile in repo.list_expired():
        repo.set_live(profile.id, False)
        _send_recheck_email(
            workflow,
            profile,
            now_utc=now_utc,
            recheck_url=recheck_url,
            is_past_due=True,
        )

    job_repo.enqueue(
        type="bgc.expiry_sweep",
        payload={"days": days},
        available_at=_next_expiry_run(),
    )


def _dispatch_known_job(
    job: Any,
    payload: dict[str, Any],
    job_repo: BackgroundJobRepository,
    repo: InstructorProfileRepository,
    workflow: BackgroundCheckWorkflowService,
) -> None:
    if job.type == "webhook.report_completed":
        _handle_report_completed(payload, workflow)
        return
    if job.type == "webhook.report_suspended":
        _handle_report_suspended(payload, workflow)
        return
    if job.type == "webhook.report_canceled":
        _handle_report_canceled(payload, workflow)
        return
    if job.type == "webhook.report_eta":
        _handle_report_eta(payload, workflow)
        return
    if job.type == FINAL_ADVERSE_JOB_TYPE:
        _handle_final_adverse(
            payload,
            job.available_at or datetime.now(timezone.utc),
            workflow,
        )
        return
    if job.type == "bgc.expiry_sweep":
        _handle_expiry_sweep(payload, job_repo, repo, workflow)
        return
    logger.warning(
        "Unknown background job type encountered",
        extra={"job_id": job.id, "type": job.type},
    )


def _record_non_retryable_failure(
    db: Any,
    job: Any,
    job_repo: BackgroundJobRepository,
    exc: NonRetryableError,
) -> None:
    db.rollback()
    job_type = job.type or "unknown"
    attempts = getattr(job, "attempts", 0)
    logger.warning(
        "Non-retryable background job error: %s",
        str(exc),
        extra={
            "evt": "bgc_job_failed",
            "job_id": job.id,
            "type": job.type,
            "attempts": attempts,
        },
    )
    BACKGROUND_JOB_FAILURES_TOTAL.labels(type=job_type).inc()
    job_repo.mark_terminal_failure(job.id, error=str(exc))
    db.commit()
    _update_failed_jobs_gauge(job_repo)


def _record_retryable_failure(
    db: Any,
    job: Any,
    job_repo: BackgroundJobRepository,
    exc: Exception,
) -> None:
    db.rollback()
    job_type = job.type or "unknown"
    attempts = getattr(job, "attempts", 0)
    logger.exception(
        "Error processing background job",
        extra={
            "evt": "bgc_job_failed",
            "job_id": job.id,
            "type": job.type,
            "attempts": attempts,
        },
    )
    BACKGROUND_JOB_FAILURES_TOTAL.labels(type=job_type).inc()
    terminal = job_repo.mark_failed(job.id, error=str(exc))
    if terminal:
        logger.error(
            "Background job moved to dead-letter queue",
            extra={
                "evt": "bgc_job_dead_letter",
                "job_id": job.id,
                "type": job_type,
                "attempts": attempts,
            },
        )
    db.commit()
    _update_failed_jobs_gauge(job_repo)


def _process_single_job(
    db: Any,
    job: Any,
    job_repo: BackgroundJobRepository,
    repo: InstructorProfileRepository,
    workflow: BackgroundCheckWorkflowService,
) -> None:
    try:
        job_repo.mark_running(job.id)
        db.flush()

        if process_event(job.type, job.payload, db):
            job_repo.mark_succeeded(job.id)
            db.commit()
            _update_failed_jobs_gauge(job_repo)
            return

        payload = job.payload or {}
        if not isinstance(payload, dict):
            raise RepositoryException("Invalid payload for background job")

        _dispatch_known_job(job, payload, job_repo, repo, workflow)
        job_repo.mark_succeeded(job.id)
        db.commit()
        _update_failed_jobs_gauge(job_repo)
    except NonRetryableError as exc:
        _record_non_retryable_failure(db, job, job_repo, exc)
    except Exception as exc:  # pragma: no cover - safety logging
        _record_retryable_failure(db, job, job_repo, exc)


def _process_due_jobs(shutdown_event: threading.Event, batch_size: int) -> None:
    db = SchedulerSessionLocal()
    try:
        job_repo = BackgroundJobRepository(db)
        repo = InstructorProfileRepository(db)
        workflow = BackgroundCheckWorkflowService(repo)

        db.connection()
        jobs = job_repo.fetch_due(limit=batch_size)
        if not jobs:
            db.commit()
            return

        for job in jobs:
            if shutdown_event.is_set():
                break
            _process_single_job(db, job, job_repo, repo, workflow)
    finally:
        db.close()


def background_jobs_worker_sync(shutdown_event: threading.Event) -> None:
    """Process persisted background jobs with retry support in a dedicated thread."""

    poll_interval = max(1, int(getattr(settings, "jobs_poll_interval", 60)))
    batch_size = max(1, int(getattr(settings, "jobs_batch", 25)))

    while not shutdown_event.is_set():
        try:
            time.sleep(poll_interval)
            if shutdown_event.is_set():
                break
            _process_due_jobs(shutdown_event, batch_size)
        except Exception as exc:  # pragma: no cover - safety logging
            logger.exception("Background job worker loop error: %s", str(exc))


def _ensure_expiry_job_scheduled() -> None:
    """Seed the background check expiry sweep job if missing."""

    if not getattr(settings, "bgc_expiry_enabled", False):
        logger.info("Skipping expiry job seed because bgc_expiry_enabled is False")
        return

    session = SchedulerSessionLocal()
    try:
        job_repo = BackgroundJobRepository(session)
        existing = job_repo.get_next_scheduled("bgc.expiry_sweep")
        if existing is None:
            job_repo.enqueue(
                type="bgc.expiry_sweep",
                payload={"days": 30},
                available_at=_next_expiry_run(),
            )
        session.commit()
    except Exception as exc:  # pragma: no cover - safety logging
        session.rollback()
        logger.warning("Unable to seed expiry sweep job: %s", str(exc))
    finally:
        session.close()


__all__ = [
    "background_jobs_worker_sync",
    "_ensure_expiry_job_scheduled",
    "_expiry_recheck_url",
    "_next_expiry_run",
]
