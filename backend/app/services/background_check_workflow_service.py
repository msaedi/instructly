"""Service layer for background check webhook workflows."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Final, Mapping, Optional, Tuple, TypedDict

from ..core.config import settings
from ..core.constants import BRAND_NAME
from ..core.exceptions import RepositoryException, ServiceException
from ..core.metrics import (
    BGC_FINAL_ADVERSE_EXECUTED_TOTAL,
    BGC_FINAL_ADVERSE_SCHEDULED_TOTAL,
)
from ..database import SessionLocal
from ..models.instructor import InstructorProfile
from ..repositories.background_job_repository import BackgroundJobRepository
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..services.email import EmailService
from ..services.template_registry import TemplateRegistry
from ..services.template_service import TemplateService
from ..utils.business_days import add_us_business_days, us_federal_holidays

logger = logging.getLogger(__name__)

FINAL_ADVERSE_BUSINESS_DAYS: Final[int] = 5
FINAL_ADVERSE_JOB_TYPE: Final[str] = "background_check.final_adverse_action"
ADVERSE_EVENT_FINAL: Final[str] = "final_adverse_sent"

EMAIL_DATE_FORMAT: Final[str] = "%B %d, %Y"
REVIEW_STATUS_SUBJECT: Final[str] = f"Update: your {BRAND_NAME} background check is under review"
FINAL_ADVERSE_SUBJECT: Final[str] = f"{BRAND_NAME}: Final adverse action decision"
EXPIRY_RECHECK_SUBJECT: Final[str] = f"{BRAND_NAME}: Background check update"


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

    def candidate_name(self, profile: InstructorProfile) -> str | None:
        user = getattr(profile, "user", None)
        if user is None:
            return None
        full_name = getattr(user, "full_name", None)
        if isinstance(full_name, str) and full_name.strip():
            return full_name
        first_raw = getattr(user, "first_name", "")
        last_raw = getattr(user, "last_name", "")
        first = first_raw.strip() if isinstance(first_raw, str) else ""
        last = last_raw.strip() if isinstance(last_raw, str) else ""
        combined = " ".join(part for part in [first, last] if part).strip()
        return combined or None

    def profile_email(self, profile: InstructorProfile) -> str | None:
        user = getattr(profile, "user", None)
        email = getattr(user, "email", None) if user is not None else None
        return email if isinstance(email, str) and email else None

    def format_date(self, value: datetime | None) -> str:
        if not value:
            value = datetime.now(timezone.utc)
        value = _ensure_utc(value)
        return value.strftime(EMAIL_DATE_FORMAT)

    def _send_bgc_template_email(
        self,
        *,
        template: TemplateRegistry,
        subject: str,
        recipient: str | None,
        context: dict[str, object],
        suppress: bool,
        log_extra: Mapping[str, object] | None = None,
    ) -> bool:
        if not recipient:
            logger.warning(
                "Skipping BGC email; missing recipient",
                extra={**dict(log_extra or {}), "subject": subject},
            )
            return False

        if suppress:
            logger.info(
                "BGC email suppressed by configuration",
                extra={**dict(log_extra or {}), "recipient": recipient, "subject": subject},
            )
            return False

        session = SessionLocal()
        try:
            template_service = TemplateService(session)
            email_service = EmailService(session)

            merged_context: dict[str, object] = {**context, "subject": subject}
            html_content = template_service.render_template(template, context=merged_context)

            email_service.send_email(
                to_email=recipient,
                subject=subject,
                html_content=html_content,
                template=template,
            )
            return True
        except ServiceException as exc:
            logger.error(
                "Failed to send BGC email",
                extra={
                    **dict(log_extra or {}),
                    "recipient": recipient,
                    "subject": subject,
                    "error": str(exc),
                },
            )
            session.rollback()
            return False
        except Exception as exc:  # pragma: no cover - safety logging
            logger.exception(
                "Unexpected error sending BGC email",
                extra={
                    **dict(log_extra or {}),
                    "recipient": recipient,
                    "subject": subject,
                    "error": str(exc),
                },
            )
            session.rollback()
            return False
        finally:
            session.close()

    def send_review_status_email(
        self, profile: InstructorProfile, context: dict[str, object]
    ) -> bool:
        return self._send_bgc_template_email(
            template=TemplateRegistry.BGC_REVIEW_STATUS,
            subject=REVIEW_STATUS_SUBJECT,
            recipient=self.profile_email(profile),
            context=context,
            suppress=settings.bgc_suppress_adverse_emails,
            log_extra={"profile_id": getattr(profile, "id", None)},
        )

    def send_final_adverse_email(
        self, profile: InstructorProfile, context: dict[str, object]
    ) -> bool:
        return self._send_bgc_template_email(
            template=TemplateRegistry.BGC_FINAL_ADVERSE,
            subject=FINAL_ADVERSE_SUBJECT,
            recipient=self.profile_email(profile),
            context=context,
            suppress=settings.bgc_suppress_adverse_emails,
            log_extra={"profile_id": getattr(profile, "id", None)},
        )

    def send_expiry_recheck_email(
        self, profile: InstructorProfile, context: dict[str, object]
    ) -> bool:
        return self._send_bgc_template_email(
            template=TemplateRegistry.BGC_EXPIRY_RECHECK,
            subject=EXPIRY_RECHECK_SUBJECT,
            recipient=self.profile_email(profile),
            context=context,
            suppress=getattr(settings, "bgc_suppress_expiry_emails", True),
            log_extra={"profile_id": getattr(profile, "id", None)},
        )

    def _maybe_send_review_status_email(
        self, profile: InstructorProfile, report_completed_at: datetime
    ) -> None:
        already_sent = getattr(profile, "bgc_review_email_sent_at", None)
        if already_sent:
            return

        context: dict[str, object] = {
            "candidate_name": self.candidate_name(profile),
            "report_date": self.format_date(report_completed_at),
            "checkr_portal_url": settings.checkr_applicant_portal_url,
            "support_email": settings.bgc_support_email,
        }
        sent = self.send_review_status_email(profile, context)
        if not sent:
            return

        sent_at = datetime.now(timezone.utc)
        try:
            self.repo.mark_review_email_sent(profile.id, sent_at)
            profile.bgc_review_email_sent_at = sent_at
        except RepositoryException:
            logger.exception(
                "Failed to persist review-status email metadata",
                extra={"profile_id": profile.id},
            )

    def handle_report_completed(
        self,
        *,
        report_id: str,
        result: str,
        assessment: str | None = None,
        package: Optional[str],
        env: str,
        completed_at: datetime,
        candidate_id: str | None = None,
        invitation_id: str | None = None,
    ) -> Tuple[str, Optional[InstructorProfile], bool]:
        """
        Process a report.completed webhook event.

        Operators: if an instructor remains stuck in ``pending`` even though
        Checkr shows a clear result, confirm the profile has ``bgc_report_id``
        set and then re-run the persisted ``webhook.report_completed`` job so
        this workflow can resume.
        """

        normalized_result = (result or "").lower() or "unknown"
        normalized_assessment = (assessment or "").strip().lower() or None
        effective_result = normalized_assessment or normalized_result
        passed_results = {"clear", "eligible"}
        status_value = "passed" if effective_result in passed_results else "review"
        completed_at = _ensure_utc(completed_at)

        updated = self.repo.update_bgc_by_report_id(
            report_id,
            status=status_value,
            completed_at=completed_at,
            result=effective_result,
        )
        if updated == 0:
            bound_profile_id = self.repo.bind_report_to_candidate(candidate_id, report_id, env=env)
            if not bound_profile_id:
                bound_profile_id = self.repo.bind_report_to_invitation(
                    invitation_id, report_id, env=env
                )
            if bound_profile_id:
                updated = self.repo.update_bgc_by_report_id(
                    report_id,
                    status=status_value,
                    completed_at=completed_at,
                    result=effective_result,
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
            result=effective_result,
            package=package,
            env=env,
            completed_at=completed_at,
        )

        requires_follow_up = status_value != "passed"

        if status_value == "passed":
            valid_until = completed_at + timedelta(days=365)
            self.repo.update_valid_until(profile.id, valid_until)
            profile.bgc_valid_until = valid_until
        else:
            self.repo.update_valid_until(profile.id, None)
            profile.bgc_valid_until = None
            self._maybe_send_review_status_email(profile, completed_at)

        self.repo.update_eta_by_report_id(report_id, None)
        profile.bgc_eta = None
        return status_value, profile, requires_follow_up

    def handle_report_suspended(self, report_id: str, note: str | None = None) -> None:
        """Process a report.suspended webhook event."""

        updated = self.repo.update_bgc_by_report_id(
            report_id,
            status="pending",
            completed_at=None,
            note=note if note is not None else "report.suspended",
        )
        if updated == 0:
            raise RepositoryException(
                f"No instructor profile linked to report {report_id}; cannot suspend"
            )

    def handle_report_canceled(
        self,
        *,
        report_id: str,
        env: str,
        canceled_at: datetime,
        candidate_id: str | None = None,
        invitation_id: str | None = None,
    ) -> InstructorProfile:
        """Process a report.canceled webhook event."""

        canceled_at = _ensure_utc(canceled_at)
        note_value = "report.canceled"
        updated = self.repo.update_bgc_by_report_id(
            report_id,
            status="canceled",
            completed_at=canceled_at,
            result="canceled",
            note=note_value,
        )
        if updated == 0:
            bound_profile_id = self.repo.bind_report_to_candidate(candidate_id, report_id, env=env)
            if not bound_profile_id:
                bound_profile_id = self.repo.bind_report_to_invitation(
                    invitation_id, report_id, env=env
                )
            if bound_profile_id:
                updated = self.repo.update_bgc_by_report_id(
                    report_id,
                    status="canceled",
                    completed_at=canceled_at,
                    result="canceled",
                    note=note_value,
                )
        if updated == 0:
            raise RepositoryException(
                f"No instructor profile linked to report {report_id}; cancel event deferred"
            )

        profile = self.repo.get_by_report_id(report_id)
        if not profile:
            raise RepositoryException(f"Unable to load instructor profile for report {report_id}")

        self.repo.update_valid_until(profile.id, None)
        profile.bgc_valid_until = None

        self.repo.append_history(
            instructor_id=profile.id,
            report_id=report_id,
            result="canceled",
            package=None,
            env=env,
            completed_at=canceled_at,
        )

        return profile

    def handle_report_eta_updated(
        self,
        *,
        report_id: str,
        env: str,
        eta: datetime | None,
        candidate_id: str | None = None,
    ) -> None:
        """Persist Checkr's estimated completion time for a pending report."""

        eta_value = _ensure_utc(eta) if eta else None

        updated = self.repo.update_eta_by_report_id(report_id, eta_value)
        if updated == 0:
            bound_profile_id = self.repo.bind_report_to_candidate(candidate_id, report_id, env=env)
            if bound_profile_id:
                updated = self.repo.update_eta_by_report_id(report_id, eta_value)
        if updated == 0:
            raise RepositoryException(
                f"No instructor profile linked to report {report_id}; ETA update deferred"
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

    async def resolve_dispute_and_resume_final_adverse(
        self, instructor_id: str, *, note: str | None = None
    ) -> tuple[bool, datetime | None]:
        """Resume the final adverse workflow once a dispute is resolved.

        Returns a tuple ``(enqueued_now, scheduled_for)`` where:

        * ``enqueued_now`` is ``True`` when a final adverse action job was
          enqueued to execute immediately.
        * ``scheduled_for`` contains the timestamp a job was scheduled for when
          the dispute window has not elapsed yet; otherwise ``None``.
        """

        session = self.repo.db
        profile = self.repo.get_by_id(instructor_id, load_relationships=False)
        if profile is None:
            raise RepositoryException("Instructor profile not found")

        final_sent_at = getattr(profile, "bgc_final_adverse_sent_at", None)
        in_dispute = bool(getattr(profile, "bgc_in_dispute", False))

        if final_sent_at is not None:
            self.repo.set_dispute_resolved(instructor_id, note)
            return False, None

        if not in_dispute:
            self.repo.set_dispute_resolved(instructor_id, note)
            return False, None

        status = (getattr(profile, "bgc_status", "") or "").lower()
        if status not in {"review", "consider"}:
            self.repo.set_dispute_resolved(instructor_id, note)
            return False, None

        pre_sent_at_raw = getattr(profile, "bgc_pre_adverse_sent_at", None)
        notice_id = getattr(profile, "bgc_pre_adverse_notice_id", None)
        if pre_sent_at_raw is None or notice_id is None:
            self.repo.set_dispute_resolved(instructor_id, note)
            return False, None

        pre_sent_at = _ensure_utc(pre_sent_at_raw)
        holidays = _collect_holidays(pre_sent_at)
        final_ready_at = add_us_business_days(pre_sent_at, FINAL_ADVERSE_BUSINESS_DAYS, holidays)

        now = datetime.now(timezone.utc)

        self.repo.set_dispute_resolved(instructor_id, note)

        job_repo = BackgroundJobRepository(session)
        existing = job_repo.get_pending_final_adverse_job(instructor_id, notice_id)

        if now >= final_ready_at:
            if existing:
                existing.available_at = now
                session.flush()
            else:
                immediate_payload: FinalAdversePayload = {
                    "profile_id": instructor_id,
                    "pre_adverse_notice_id": notice_id,
                    "pre_adverse_sent_at": pre_sent_at.isoformat(),
                }
                job_repo.enqueue(
                    type=FINAL_ADVERSE_JOB_TYPE,
                    payload=dict(immediate_payload),
                    available_at=now,
                )
            BGC_FINAL_ADVERSE_SCHEDULED_TOTAL.inc()
            logger.info(
                "Final adverse action immediately enqueued after dispute resolution",
                extra={"profile_id": instructor_id, "notice_id": notice_id},
            )
            return True, None

        if existing:
            existing.available_at = final_ready_at
            session.flush()
            scheduled_for = final_ready_at
        else:
            scheduled_payload: FinalAdversePayload = {
                "profile_id": instructor_id,
                "pre_adverse_notice_id": notice_id,
                "pre_adverse_sent_at": pre_sent_at.isoformat(),
            }
            job_repo.enqueue(
                type=FINAL_ADVERSE_JOB_TYPE,
                payload=dict(scheduled_payload),
                available_at=final_ready_at,
            )
            scheduled_for = final_ready_at
        BGC_FINAL_ADVERSE_SCHEDULED_TOTAL.inc()
        logger.info(
            "Final adverse action rescheduled after dispute resolution",
            extra={
                "profile_id": instructor_id,
                "notice_id": notice_id,
                "available_at": scheduled_for.isoformat(),
            },
        )
        return False, scheduled_for

    def execute_final_adverse_action(
        self, profile_id: str, notice_id: str, scheduled_at: datetime
    ) -> bool:
        """Execute the persisted final adverse action."""

        return self._execute_final_adverse_action(profile_id, notice_id, scheduled_at)

    def _send_final_adverse_email(self, profile: InstructorProfile) -> None:
        context: dict[str, object] = {
            "candidate_name": self.candidate_name(profile),
            "decision_date": self.format_date(datetime.now(timezone.utc)),
            "checkr_portal_url": settings.checkr_applicant_portal_url,
            "checkr_dispute_url": settings.checkr_dispute_contact_url,
            "ftc_rights_url": settings.ftc_summary_of_rights_url,
            "support_email": settings.bgc_support_email,
        }
        self.send_final_adverse_email(profile, context)

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

            if getattr(profile, "bgc_in_dispute", False):
                logger.info(
                    "Final adverse action skipped; dispute flag set",
                    extra={"profile_id": profile_id},
                )
                BGC_FINAL_ADVERSE_EXECUTED_TOTAL.labels(outcome="skipped_dispute").inc()
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
            if current_status not in {"review", "consider"}:
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
