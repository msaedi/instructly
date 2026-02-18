"""Celery tasks for video session monitoring and no-show detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable, Optional, ParamSpec, Protocol, TypedDict, TypeVar, cast

from sqlalchemy.orm import Session

from app.core.booking_lock import booking_lock_sync
from app.core.config import settings
from app.database import get_db
from app.domain.video_utils import compute_grace_minutes
from app.models.booking import BookingStatus
from app.monitoring.sentry_crons import monitor_if_configured
from app.repositories.factory import RepositoryFactory
from app.services.booking_service import BookingService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class TaskWrapper(Protocol[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        ...

    def delay(self, *args: P.args, **kwargs: P.kwargs) -> Any:
        ...

    def apply_async(self, *args: Any, **kwargs: Any) -> Any:
        ...


def typed_task(
    *task_args: Any, **task_kwargs: Any
) -> Callable[[Callable[P, R]], TaskWrapper[P, R]]:
    """Return a typed Celery task decorator for mypy."""
    return cast(
        Callable[[Callable[P, R]], TaskWrapper[P, R]],
        celery_app.task(*task_args, **task_kwargs),
    )


# ── Constants ────────────────────────────────────────────────────────────

MIN_GRACE_MINUTES = 8  # ceil(30 * 0.25) — shortest possible grace (30-min lesson)


class VideoNoShowResults(TypedDict):
    processed: int
    reported: int
    skipped: int
    failed: int
    processed_at: str


# ── Helpers ──────────────────────────────────────────────────────────────


def _determine_no_show_type(video_session: Any) -> str | None:
    """Determine no-show type from video session join timestamps.

    Returns:
        "instructor" if only student joined,
        "student" if only instructor joined,
        None if both joined (lesson happened) or neither joined (ambiguous).
    """
    instructor_joined = video_session.instructor_joined_at is not None
    student_joined = video_session.student_joined_at is not None

    if instructor_joined and student_joined:
        return None  # lesson happened
    if not instructor_joined and student_joined:
        return "instructor"
    if instructor_joined and not student_joined:
        return "student"
    # Neither joined — ambiguous, skip for manual review
    return None


# ── Task ─────────────────────────────────────────────────────────────────


@typed_task(name="app.tasks.video_tasks.detect_video_no_shows")
@monitor_if_configured("detect-video-no-shows")
def detect_video_no_shows() -> VideoNoShowResults:
    """Detect no-shows for online bookings based on video session attendance.

    Grace period runs from lesson START (not end). A no-show means a participant
    didn't join within the first min(duration_minutes * 0.25, 15) minutes.

    Two-stage filtering:
    1. SQL uses MIN_GRACE_MINUTES=8 as generous cutoff to catch ALL candidates
    2. Python computes exact per-booking grace and filters precisely
    """
    now = datetime.now(timezone.utc)
    results: VideoNoShowResults = {
        "processed": 0,
        "reported": 0,
        "skipped": 0,
        "failed": 0,
        "processed_at": now.isoformat(),
    }

    if not settings.hundredms_enabled:
        return results

    db: Optional[Session] = None
    try:
        db = cast(Session, next(get_db()))
        booking_repo = RepositoryFactory.get_booking_repository(db)
        booking_service = BookingService(db)

        sql_cutoff = now - timedelta(minutes=MIN_GRACE_MINUTES)
        candidates = booking_repo.get_video_no_show_candidates(sql_cutoff)

        for booking, video_session in candidates:
            results["processed"] += 1
            booking_id = booking.id
            try:
                # Per-booking grace period
                grace = compute_grace_minutes(booking.duration_minutes)
                grace_deadline = booking.booking_start_utc + timedelta(minutes=grace)
                if now < grace_deadline:
                    results["skipped"] += 1
                    continue

                # Determine no-show type
                no_show_type = _determine_no_show_type(video_session)
                if no_show_type is None:
                    results["skipped"] += 1
                    continue

                with booking_lock_sync(str(booking_id)) as acquired:
                    if not acquired:
                        results["skipped"] += 1
                        continue

                    # Re-check under lock
                    refreshed = booking_repo.get_by_id(booking_id)
                    if refreshed is None or refreshed.status != BookingStatus.CONFIRMED.value:
                        results["skipped"] += 1
                        continue

                    existing_no_show = booking_repo.get_no_show_by_booking_id(booking_id)
                    if (
                        existing_no_show is not None
                        and existing_no_show.no_show_reported_at is not None
                    ):
                        results["skipped"] += 1
                        continue

                    booking_service.report_automated_no_show(
                        booking_id=booking_id,
                        no_show_type=no_show_type,
                        reason=f"Automated: {no_show_type} did not join video session within {grace:.1f} min grace period",
                    )
                    results["reported"] += 1

            except Exception as exc:
                logger.error(
                    "Failed to process video no-show for booking %s: %s",
                    booking_id,
                    exc,
                )
                results["failed"] += 1

        return results
    finally:
        if db is not None:
            db.close()
