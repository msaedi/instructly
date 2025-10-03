"""Service layer for background check webhook workflows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Tuple

from ..core.config import settings
from ..core.exceptions import RepositoryException
from ..database import SessionLocal
from ..models.instructor import InstructorProfile
from ..repositories.instructor_profile_repository import InstructorProfileRepository
from ..services.email import EmailService

logger = logging.getLogger(__name__)

SUMMARY_OF_RIGHTS_URL = "https://www.consumerfinance.gov/rules-policy/regulations/603/"
FINAL_ADVERSE_DELAY = timedelta(days=5)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
            self._send_pre_adverse_email(profile)

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

    def schedule_final_adverse_action(self, profile_id: str) -> None:
        """Expose scheduling helper for legacy callers/tests."""

        self._schedule_final_adverse_action(profile_id)

    def execute_final_adverse_action(self, profile_id: str) -> bool:
        """Expose final adverse action executor for legacy callers/tests."""

        return self._execute_final_adverse_action(profile_id)

    def _handle_non_clear_report(self, profile: InstructorProfile) -> None:
        self._send_pre_adverse_email(profile)
        self._schedule_final_adverse_action(profile.id)

    def _send_pre_adverse_email(self, profile: InstructorProfile) -> None:
        user = getattr(profile, "user", None)
        recipient = getattr(user, "email", None)
        if not recipient:
            logger.warning(
                "Skipping pre-adverse email; missing recipient",
                extra={"profile": profile.id},
            )
            return

        html = (
            "<p>We are reviewing your background check results and wanted to let you know. "
            "This is a pre-adverse action notice. Please review the attached report and your "
            f"rights: <a href='{SUMMARY_OF_RIGHTS_URL}'>Summary of Rights under the FCRA</a>. "
            "If you believe the report is inaccurate, contact us within five business days to initiate a dispute."
            "</p>"
        )

        self._send_email("Background check under review", html, recipient)

    def _send_final_adverse_email(self, profile: InstructorProfile) -> None:
        user = getattr(profile, "user", None)
        recipient = getattr(user, "email", None)
        if not recipient:
            logger.warning(
                "Skipping final adverse email; missing recipient",
                extra={"profile": profile.id},
            )
            return

        html = (
            "<p>We completed our review of your background report. Unfortunately, we are unable to move forward."
            " You have already received a copy of your report and the Summary of Rights under the FCRA. "
            "If you would like to dispute the findings, please reach out to support@instainstru.com."
            "</p>"
        )

        self._send_email("Background check decision", html, recipient)

    def _send_email(self, subject: str, html_body: str, recipient: str) -> None:
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
            session.rollback()
        finally:
            session.close()

    def _schedule_final_adverse_action(self, profile_id: str) -> None:
        if getattr(settings, "is_testing", False) or not getattr(
            settings, "scheduler_enabled", True
        ):
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
        loop.create_task(self._finalize_after_delay(profile_id, FINAL_ADVERSE_DELAY))

    async def _finalize_after_delay(self, profile_id: str, delay: timedelta) -> None:
        await asyncio.sleep(max(delay.total_seconds(), 0))
        await asyncio.to_thread(self._execute_final_adverse_action, profile_id)

    def _execute_final_adverse_action(self, profile_id: str) -> bool:
        session = SessionLocal()
        try:
            repo = InstructorProfileRepository(session)
            profile = repo.get_by_id(profile_id, load_relationships=True)
            if not profile:
                logger.warning(
                    "Final adverse action skipped; profile missing",
                    extra={"profile_id": profile_id},
                )
                return False

            if getattr(profile, "bgc_in_dispute", False):
                logger.info(
                    "Final adverse action paused due to dispute",
                    extra={"evt": "bgc_adverse_paused", "instructor_id": profile_id},
                )
                return False

            current_status = (getattr(profile, "bgc_status", "") or "").lower()
            if current_status != "review":
                logger.info(
                    "Final adverse action skipped; status changed",
                    extra={"profile_id": profile_id, "status": current_status},
                )
                return False

            profile.bgc_status = "failed"
            profile.bgc_completed_at = _ensure_utc(datetime.now(timezone.utc))
            session.flush()
            session.commit()
            self._send_final_adverse_email(profile)
            return True
        except Exception as exc:  # pragma: no cover - safety logging
            logger.error("Failed to complete final adverse action: %s", str(exc))
            session.rollback()
            return False
        finally:
            session.close()
