"""Repository for persisted background jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any, List, Optional, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import ulid

from ..core.config import settings
from ..core.exceptions import RepositoryException
from ..models.instructor import BackgroundJob

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..services.background_check_workflow_service import FinalAdversePayload


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BackgroundJobRepository:
    """Data access helpers for background_jobs table."""

    def __init__(self, db: Session):
        self.db = db
        self.logger = logger

    def enqueue(
        self,
        *,
        type: str,
        payload: dict[str, Any],
        available_at: datetime | None = None,
    ) -> str:
        """Persist a new job ready for processing."""

        try:
            job_id = str(ulid.ULID())
            job = BackgroundJob(
                id=job_id,
                type=type,
                payload=payload,
                status="queued",
                attempts=0,
                available_at=available_at or _utcnow(),
            )
            self.db.add(job)
            self.db.flush()
            return job_id
        except SQLAlchemyError as exc:
            self.logger.error("Failed to enqueue job %s: %s", type, str(exc))
            self.db.rollback()
            raise RepositoryException("Failed to enqueue background job") from exc

    def fetch_due(self, *, limit: int = 50) -> List[BackgroundJob]:
        """Return queued jobs that are ready to run."""

        try:
            now = _utcnow()
            jobs = (
                self.db.query(BackgroundJob)
                .filter(
                    BackgroundJob.status == "queued",
                    BackgroundJob.available_at <= now,
                )
                .order_by(BackgroundJob.available_at.asc())
                .limit(limit)
                .all()
            )
            return cast(List[BackgroundJob], jobs)
        except SQLAlchemyError as exc:
            self.logger.error("Failed to fetch due jobs: %s", str(exc))
            raise RepositoryException("Failed to fetch background jobs") from exc

    def mark_running(self, job_id: str) -> None:
        """Mark a job as running."""

        try:
            self.db.query(BackgroundJob).filter(BackgroundJob.id == job_id).update(
                {
                    BackgroundJob.status: "running",
                    BackgroundJob.updated_at: _utcnow(),
                }
            )
        except SQLAlchemyError as exc:
            self.logger.error("Failed to mark job %s running: %s", job_id, str(exc))
            self.db.rollback()
            raise RepositoryException("Failed to mark job running") from exc

    def mark_succeeded(self, job_id: str) -> None:
        """Mark a job as completed successfully."""

        try:
            self.db.query(BackgroundJob).filter(BackgroundJob.id == job_id).update(
                {
                    BackgroundJob.status: "succeeded",
                    BackgroundJob.updated_at: _utcnow(),
                }
            )
        except SQLAlchemyError as exc:
            self.logger.error("Failed to mark job %s succeeded: %s", job_id, str(exc))
            self.db.rollback()
            raise RepositoryException("Failed to mark job succeeded") from exc

    def mark_failed(self, job_id: str, error: str) -> None:
        """Increment attempt counters and reschedule a job after a failure."""

        try:
            job = self.db.get(BackgroundJob, job_id)
            if job is None:
                self.logger.warning("Attempted to mark missing job %s failed", job_id)
                return

            attempts = (job.attempts or 0) + 1
            base = getattr(settings, "jobs_backoff_base", 30)
            cap = getattr(settings, "jobs_backoff_cap", 1800)
            backoff_seconds = min(cap, base * (2 ** (attempts - 1)))

            job.status = "queued"
            job.attempts = attempts
            job.available_at = _utcnow() + timedelta(seconds=backoff_seconds)
            job.last_error = error
            job.updated_at = _utcnow()

            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error("Failed to reschedule job %s: %s", job_id, str(exc))
            self.db.rollback()
            raise RepositoryException("Failed to reschedule background job") from exc

    def get_next_scheduled(self, job_type: str) -> BackgroundJob | None:
        """Return the next scheduled job for a given type, if any."""

        try:
            now = _utcnow()
            result = (
                self.db.query(BackgroundJob)
                .filter(
                    BackgroundJob.type == job_type,
                    BackgroundJob.status.in_(["queued", "running"]),
                    BackgroundJob.available_at >= now - timedelta(days=1),
                )
                .order_by(BackgroundJob.available_at.asc())
                .first()
            )
            return cast(Optional[BackgroundJob], result)
        except SQLAlchemyError as exc:
            self.logger.error("Failed to load scheduled job for type %s: %s", job_type, str(exc))
            raise RepositoryException("Failed to load scheduled job") from exc

    def get_pending_final_adverse_job(
        self, profile_id: str, notice_id: str
    ) -> BackgroundJob | None:
        """Return existing queued final adverse jobs for the given profile/notice."""

        try:
            jobs = cast(
                List[BackgroundJob],
                (
                    self.db.query(BackgroundJob)
                    .filter(
                        BackgroundJob.type == "background_check.final_adverse_action",
                        BackgroundJob.status == "queued",
                    )
                    .all()
                ),
            )
            for job in jobs:
                payload_raw = job.payload
                if not isinstance(payload_raw, dict):
                    continue
                payload = cast("FinalAdversePayload", payload_raw)
                if (
                    payload["profile_id"] == profile_id
                    and payload["pre_adverse_notice_id"] == notice_id
                ):
                    return job
            return None
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to check pending final adverse job for %s: %s",
                profile_id,
                str(exc),
            )
            raise RepositoryException("Failed to inspect background jobs") from exc
