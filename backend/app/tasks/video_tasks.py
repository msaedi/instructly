"""Celery tasks for video session monitoring and no-show detection."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Optional, ParamSpec, Protocol, TypedDict, TypeVar, cast

from sqlalchemy.orm import Session

from app.core.booking_lock import booking_lock_sync
from app.core.config import settings
from app.database import get_db
from app.domain.video_utils import compute_join_closes_at
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


class VideoNoShowResults(TypedDict):
    processed: int
    reported: int
    skipped: int
    failed: int
    processed_at: str


# ── Helpers ──────────────────────────────────────────────────────────────


def _determine_no_show_type(video_session: Any | None) -> str | None:
    """Determine no-show type from video session join timestamps.

    Returns:
        "mutual" if video_session is None (neither party clicked join),
        "mutual" if both joined_at are None (both clicked join but neither connected),
        "instructor" if only student joined,
        "student" if only instructor joined,
        None if both joined (lesson happened).
    """
    if video_session is None:
        # No video session row exists. This is usually a true mutual no-show
        # (neither participant clicked join), but it can also happen when room
        # creation fails before attendance is recorded. We classify as "mutual"
        # and rely on the dispute workflow for edge-case correction.
        return "mutual"

    instructor_joined = video_session.instructor_joined_at is not None
    student_joined = video_session.student_joined_at is not None

    if instructor_joined and student_joined:
        return None  # lesson happened
    if not instructor_joined and student_joined:
        return "instructor"
    if instructor_joined and not student_joined:
        return "student"
    return "mutual"  # Both clicked join but neither actually connected


# ── Task ─────────────────────────────────────────────────────────────────


@typed_task(name="app.tasks.video_tasks.detect_video_no_shows")
@monitor_if_configured("detect-video-no-shows")
def detect_video_no_shows() -> VideoNoShowResults:
    """Detect no-shows for online bookings based on video session attendance.

    Automated no-shows only run after the scheduled lesson end so they remain
    aligned with the join window, which stays open until session end.

    Two-stage filtering:
    1. SQL fetches online confirmed bookings whose scheduled end has passed
    2. Python re-checks the scheduled end from the booking payload before reporting
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
        booking_repo = RepositoryFactory.create_booking_repository(db)
        booking_service = BookingService(db)

        sql_cutoff = now
        candidates = booking_repo.get_video_no_show_candidates(sql_cutoff)

        for booking, video_session in candidates:  # video_session may be None
            results["processed"] += 1
            booking_id = booking.id
            try:
                booking_start_utc = getattr(booking, "booking_start_utc", None)
                duration_minutes = getattr(booking, "duration_minutes", None)
                if (
                    not isinstance(booking_start_utc, datetime)
                    or not isinstance(duration_minutes, (int, float))
                    or duration_minutes <= 0
                ):
                    scheduled_end_utc = None
                else:
                    scheduled_end_utc = compute_join_closes_at(
                        booking_start_utc=booking_start_utc,
                        duration_minutes=float(duration_minutes),
                        booking_end_utc=getattr(booking, "booking_end_utc", None),
                    )
                if scheduled_end_utc is None or now < scheduled_end_utc:
                    results["skipped"] += 1
                    continue

                # Determine no-show type (handles None video_session → "mutual")
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
                    if refreshed is not None:
                        booking_repo.refresh(refreshed)
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

                    if no_show_type == "mutual":
                        reason = "Automated: neither party joined before scheduled session end"
                    else:
                        reason = (
                            f"Automated: {no_show_type} did not join before scheduled session end"
                        )
                    booking_service.report_automated_no_show(
                        booking_id=booking_id,
                        no_show_type=no_show_type,
                        reason=reason,
                    )
                    results["reported"] += 1

            except Exception as exc:
                db.rollback()  # Isolate failure — don't poison session for remaining bookings
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
