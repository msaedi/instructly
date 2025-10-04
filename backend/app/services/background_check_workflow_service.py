"""Service layer for background check webhook workflows."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Final, Optional, Tuple, TypedDict

import ulid

from ..core.config import settings
from ..core.exceptions import RepositoryException
from ..core.metrics import (
    BGC_FINAL_ADVERSE_EXECUTED_TOTAL,
    BGC_FINAL_ADVERSE_SCHEDULED_TOTAL,
)
from ..database import SessionLocal
from ..models.instructor import InstructorProfile
from ..repositories.background_job_repository import BackgroundJobRepository
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..services.adverse_action_email_templates import (
    build_final_adverse_email,
    build_pre_adverse_email,
)
from ..services.email import EmailService
from ..utils.business_days import add_us_business_days, us_federal_holidays

logger = logging.getLogger(__name__)

FINAL_ADVERSE_BUSINESS_DAYS: Final[int] = 5
FINAL_ADVERSE_JOB_TYPE: Final[str] = "background_check.final_adverse_action"
ADVERSE_EVENT_FINAL: Final[str] = "final_adverse_sent"


class FinalAdversePayload(TypedDict):
    """Serialized payload for final adverse action jobs."""

    profile_id: str
    pre_adverse_notice_id: str
    pre_adverse_sent_at: str


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _collect_holidays(anchor: datetime) -> set[date]:
    years = {anchor.year - 1, anchor.year, anchor.year + 1}
    holidays: set[date] = set()
    for year in years:
        if year >= 1900:
            holidays |= us_federal_holidays(year)
    return holidays


class BackgroundCheckWorkflowService:
    """Encapsulates background check webhook workflows."""

    def __init__(self, repo: InstructorProfileRepository):
        self.repo = repo
        self.logger = logging.getLogger(self.__class__.__name__)

    def handle_report_completed(
        self,
        *,
        report_id: str,
        result: str,
        package: Optional[str],
        env: str,
        completed_at: datetime,
    ) -> Tuple[str, Optional[InstructorProfile], bool]:
        """Process a report.completed webhook event."""

        normalized_result = result.lower() if result else "unknown"
        status_value = "passed" if normalized_result == "clear" else "review"
        completed_at = _ensure_utc(completed_at)

        updated = self.repo.update_bgc_by_report_id(
            report_id,
            status=status_value,
            completed_at=completed_at,
        )
        if updated == 0:
            raise RepositoryException(
                f"No instructor profile linked to report {report_id}; will retry later"
            )

        profile = self.repo.get_by_report_id(report_id)
        if not profile:
            raise RepositoryException(f"Unable to load instructor profile for report {report_id}")

        self.repo.append_history(
            instructor_id=profile.id,
            report_id=report_id,
            result=normalized_result,
            package=package,
            env=env,
            completed_at=completed_at,
        )

        requires_follow_up = normalized_result != "clear"

        if normalized_result == "clear":
            valid_until = completed_at + timedelta(days=365)
            self.repo.update_valid_until(profile.id, valid_until)
            profile.bgc_valid_until = valid_until
        else:
            self.repo.update_valid_until(profile.id, None)
            profile.bgc_valid_until = None
            metadata = self._send_pre_adverse_email(profile)
            if metadata:
                notice_id, sent_at = metadata
                self._schedule_final_adverse_action(
                    profile.id, notice_id=notice_id, sent_at=sent_at
                )

        return status_value, profile, requires_follow_up

    def handle_report_suspended(self, report_id: str) -> None:
        """Process a report.suspended webhook event."""

        updated = self.repo.update_bgc_by_report_id(
            report_id,
            status="review",
            completed_at=None,
        )
        if updated == 0:
            raise RepositoryException(
                f"No instructor profile linked to report {report_id}; cannot suspend"
            )

    def schedule_final_adverse_action(
        self,
        profile_id: str,
        *,
        notice_id: str | None = None,
        sent_at: datetime | None = None,
    ) -> None:
        """Public helper to (re)schedule the final adverse action job."""

        self._schedule_final_adverse_action(profile_id, notice_id=notice_id, sent_at=sent_at)

    def execute_final_adverse_action(
        self, profile_id: str, notice_id: str, scheduled_at: datetime
    ) -> bool:
        """Execute the persisted final adverse action."""

        return self._execute_final_adverse_action(profile_id, notice_id, scheduled_at)

    def _send_pre_adverse_email(self, profile: InstructorProfile) -> tuple[str, datetime] | None:
        user = getattr(profile, "user", None)
        recipient = getattr(user, "email", None)
        if not recipient:
            logger.warning(
                "Skipping pre-adverse email; missing recipient",
                extra={"profile": profile.id},
            )
            return None

        notice_id = str(ulid.ULID())
        sent_at = _ensure_utc(datetime.now(timezone.utc))
        try:
            self.repo.set_pre_adverse_notice(profile.id, notice_id, sent_at)
        except RepositoryException:
            logger.exception(
                "Failed to persist pre-adverse metadata",
                extra={"profile_id": profile.id},
            )
            return None

        template = build_pre_adverse_email(business_days=FINAL_ADVERSE_BUSINESS_DAYS)
        self._send_email(template.subject, template.html, recipient, template.text)
        return notice_id, sent_at

    def _send_final_adverse_email(self, profile: InstructorProfile) -> None:
        user = getattr(profile, "user", None)
        recipient = getattr(user, "email", None)
        if not recipient:
            logger.warning(
                "Skipping final adverse email; missing recipient",
                extra={"profile": profile.id},
            )
            return

        template = build_final_adverse_email()
        self._send_email(template.subject, template.html, recipient, template.text)

    def _send_email(
        self, subject: str, html_body: str, recipient: str, text_body: str | None = None
    ) -> None:
        if settings.bgc_suppress_adverse_emails:
            logger.info(
                "Adverse-action email suppressed by configuration",
                extra={"recipient": recipient, "subject": subject},
            )
            return

        session = SessionLocal()
        try:
            email_service = EmailService(session)
            email_service.send_email(recipient, subject, html_body, text_content=text_body)
        except Exception as exc:  # pragma: no cover - logging only
            logger.error("Failed to send adverse-action email: %s", str(exc))
            session.rollback()
        finally:
            session.close()

    def _schedule_final_adverse_action(
        self,
        profile_id: str,
        *,
        notice_id: str | None = None,
        sent_at: datetime | None = None,
    ) -> None:
        if getattr(settings, "is_testing", False) or not getattr(
            settings, "scheduler_enabled", True
        ):
            logger.debug(
                "Skipping final adverse action scheduling",
                extra={"profile_id": profile_id, "reason": "scheduler_disabled"},
            )
            return

        profile: InstructorProfile | None = None
        if notice_id is None or sent_at is None:
            profile = self.repo.get_by_id(profile_id, load_relationships=False)
            if not profile:
                logger.warning(
                    "Skipping final adverse scheduling; profile not found",
                    extra={"profile_id": profile_id},
                )
                return
            notice_id = notice_id or getattr(profile, "bgc_pre_adverse_notice_id", None)
            sent_at = sent_at or getattr(profile, "bgc_pre_adverse_sent_at", None)

        if not notice_id or not sent_at:
            logger.warning(
                "Skipping final adverse scheduling; missing metadata",
                extra={"profile_id": profile_id},
            )
            return

        sent_at = _ensure_utc(sent_at)
        holidays = _collect_holidays(sent_at)
        available_at = add_us_business_days(sent_at, FINAL_ADVERSE_BUSINESS_DAYS, holidays)

        job_repo = BackgroundJobRepository(self.repo.db)
        existing = job_repo.get_pending_final_adverse_job(profile_id, notice_id)
        if existing:
            logger.info(
                "Final adverse action already scheduled",
                extra={
                    "profile_id": profile_id,
                    "notice_id": notice_id,
                    "job_id": existing.id,
                    "available_at": existing.available_at.isoformat()
                    if existing.available_at
                    else None,
                },
            )
            return

        payload: FinalAdversePayload = {
            "profile_id": profile_id,
            "pre_adverse_notice_id": notice_id,
            "pre_adverse_sent_at": sent_at.isoformat(),
        }
        job_id = job_repo.enqueue(
            type=FINAL_ADVERSE_JOB_TYPE,
            payload=dict(payload),
            available_at=available_at,
        )
        BGC_FINAL_ADVERSE_SCHEDULED_TOTAL.inc()
        logger.info(
            "Scheduled final adverse action",
            extra={
                "profile_id": profile_id,
                "notice_id": notice_id,
                "job_id": job_id,
                "available_at": available_at.isoformat(),
            },
        )

    def _execute_final_adverse_action(
        self, profile_id: str, notice_id: str, scheduled_at: datetime
    ) -> bool:
        scheduled_at = _ensure_utc(scheduled_at)

        session = SessionLocal()
        try:
            repo = InstructorProfileRepository(session)
            profile = repo.get_by_id(profile_id, load_relationships=True)
            if not profile:
                logger.warning(
                    "Final adverse action skipped; profile missing",
                    extra={"profile_id": profile_id},
                )
                BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="skipped_status").inc()
                return False

            current_notice_id = getattr(profile, "bgc_pre_adverse_notice_id", None)
            pre_sent_at = getattr(profile, "bgc_pre_adverse_sent_at", None)

            if not current_notice_id or not pre_sent_at:
                logger.info(
                    "Final adverse action skipped; metadata missing",
                    extra={"profile_id": profile_id},
                )
                BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="skipped_status").inc()
                return False

            pre_sent_at = _ensure_utc(pre_sent_at)

            if current_notice_id != notice_id:
                logger.info(
                    "Final adverse action superseded by newer notice",
                    extra={
                        "profile_id": profile_id,
                        "current_notice_id": current_notice_id,
                        "job_notice_id": notice_id,
                    },
                )
                BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="superseded").inc()
                return False

            if repo.has_adverse_event(profile_id, notice_id, ADVERSE_EVENT_FINAL):
                logger.info(
                    "Final adverse action already processed",
                    extra={"profile_id": profile_id, "notice_id": notice_id},
                )
                BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="finalized").inc()
                return False

            current_status = (getattr(profile, "bgc_status", "") or "").lower()
            if current_status != "review":
                logger.info(
                    "Final adverse action skipped; status changed",
                    extra={"profile_id": profile_id, "status": current_status},
                )
                BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="skipped_status").inc()
                return False

            if getattr(profile, "is_live", False):
                logger.info(
                    "Final adverse action skipped; profile already live",
                    extra={"profile_id": profile_id},
                )
                BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="skipped_status").inc()
                return False

            dispute_opened_at = getattr(profile, "bgc_dispute_opened_at", None)
            now = _ensure_utc(datetime.now(timezone.utc))
            if dispute_opened_at:
                dispute_opened_at = _ensure_utc(dispute_opened_at)
                if dispute_opened_at >= pre_sent_at and dispute_opened_at <= now:
                    logger.info(
                        "Final adverse action skipped; dispute in flight",
                        extra={"profile_id": profile_id, "scheduled_at": scheduled_at.isoformat()},
                    )
                    BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="skipped_dispute").inc()
                    return False

            profile.bgc_status = "failed"
            profile.bgc_completed_at = now
            profile.is_live = False

            repo.set_final_adverse_sent_at(profile_id, now)
            repo.record_adverse_event(profile_id, notice_id, ADVERSE_EVENT_FINAL)
            session.flush()
            session.commit()

            self._send_final_adverse_email(profile)

            BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="finalized").inc()
            logger.info(
                "Final adverse action finalized",
                extra={
                    "profile_id": profile_id,
                    "notice_id": notice_id,
                    "scheduled_at": scheduled_at.isoformat(),
                },
            )
            return True
        except Exception as exc:  # pragma: no cover - safety logging
            logger.error("Failed to complete final adverse action: %s", str(exc))
            session.rollback()
            BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="skipped_status").inc()
            return False
        finally:
            session.close()
