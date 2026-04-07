"""Background-check lifecycle, consent, and adverse-action persistence helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, List, Optional, cast

from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from ...core.crypto import encrypt_str
from ...core.exceptions import RepositoryException
from ...models.instructor import (
    BackgroundCheck,
    BGCAdverseActionEvent,
    BGCConsent,
    InstructorProfile,
)
from .mixin_base import _UNSET, InstructorProfileRepositoryMixinBase


class BgcLifecycleMixin(InstructorProfileRepositoryMixinBase):
    """Background-check status tracking, consent, and adverse-action workflow."""

    def count_by_bgc_status(self, status: str) -> int:
        """Return total profiles matching a single background-check status."""

        return self.count_by_bgc_statuses([status])

    def count_by_bgc_statuses(self, statuses: Iterable[str]) -> int:
        """Return total profiles matching any of the provided statuses."""

        normalized = [(value or "").strip().lower() for value in statuses if (value or "").strip()]
        if not normalized:
            return 0

        try:
            total = (
                self.db.query(func.count(InstructorProfile.id))
                .filter(InstructorProfile.bgc_status.in_(normalized))
                .scalar()
            )
            return int(total or 0)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to count instructor profiles by bgc_status IN %s: %s",
                normalized,
                str(exc),
            )
            raise RepositoryException(
                "Failed to count profiles by background check statuses"
            ) from exc

    def latest_consent(self, instructor_id: str) -> Optional[BGCConsent]:
        """Return the most recent consent record for an instructor."""

        return cast(
            Optional[BGCConsent],
            self.db.query(BGCConsent)
            .filter(BGCConsent.instructor_id == instructor_id)
            .order_by(BGCConsent.consented_at.desc())
            .first(),
        )

    def update_bgc(
        self,
        instructor_id: str,
        *,
        status: str,
        report_id: str | None,
        env: str,
        report_result: str | None = None,
        candidate_id: str | None = None,
        invitation_id: str | None = None,
        note: Any = _UNSET,
        includes_canceled: Any = _UNSET,
        submitted_first_name: Any = _UNSET,
        submitted_last_name: Any = _UNSET,
        submitted_dob: Any = _UNSET,
    ) -> None:
        """Persist background check metadata for a specific instructor profile."""

        try:
            profile = self.get_by_id(instructor_id, load_relationships=False)
            if not profile:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")

            profile.bgc_status = status
            profile.bgc_report_id = report_id
            profile.bgc_env = env
            profile.bgc_report_result = report_result
            if candidate_id is not None:
                profile.checkr_candidate_id = candidate_id
            if invitation_id is not None:
                profile.checkr_invitation_id = invitation_id
            if note is not _UNSET:
                profile.bgc_note = cast(Optional[str], note)
            if includes_canceled is not _UNSET:
                profile.bgc_includes_canceled = bool(includes_canceled)
            if submitted_first_name is not _UNSET:
                profile.bgc_submitted_first_name = cast(Optional[str], submitted_first_name)
            if submitted_last_name is not _UNSET:
                profile.bgc_submitted_last_name = cast(Optional[str], submitted_last_name)
            if submitted_dob is not _UNSET:
                profile.bgc_submitted_dob = submitted_dob

            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update background check metadata for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException(
                f"Failed to update background check metadata for instructor {instructor_id}"
            ) from exc

    def update_bgc_by_report_id(
        self,
        report_id: str,
        *,
        status: str | None = None,
        completed_at: datetime | None = None,
        result: Any = _UNSET,
        note: Any = _UNSET,
        includes_canceled: Any = _UNSET,
    ) -> int:
        """Update background check fields based on a Checkr report identifier."""

        try:
            profile_id = self._resolve_profile_id_by_report(report_id)
            if profile_id is None:
                return 0

            profile = self.get_by_id(profile_id, load_relationships=False)
            if not profile:
                return 0

            if status is not None:
                profile.bgc_status = status
            if completed_at is not None:
                profile.bgc_completed_at = completed_at
            if result is not _UNSET:
                profile.bgc_report_result = cast(Optional[str], result)
            if note is not _UNSET:
                profile.bgc_note = cast(Optional[str], note)
            if includes_canceled is not _UNSET:
                profile.bgc_includes_canceled = bool(includes_canceled)

            self.db.flush()
            return 1
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update background check metadata for report %s: %s",
                report_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException(
                f"Failed to update background check metadata for report {report_id}"
            ) from exc

    def update_eta_by_report_id(self, report_id: str, eta: datetime | None) -> int:
        """Update the stored ETA for the profile linked to a report."""

        try:
            profile_id = self._resolve_profile_id_by_report(report_id)
            if profile_id is None:
                return 0

            profile = self.get_by_id(profile_id, load_relationships=False)
            if not profile:
                return 0

            profile.bgc_eta = eta
            self.db.flush()
            return 1
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update background check ETA for report %s: %s",
                report_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException(
                f"Failed to update background check ETA for report {report_id}"
            ) from exc

    def update_valid_until(self, instructor_id: str, valid_until: datetime | None) -> None:
        """Persist the background check validity window for an instructor."""

        try:
            profile = self.get_by_id(instructor_id, load_relationships=False)
            if not profile:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")

            profile.bgc_valid_until = valid_until
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update bgc_valid_until for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to update background check validity") from exc

    def set_bgc_invited_at(self, instructor_id: str, when: datetime) -> None:
        """Record when the most recent Checkr invite was sent."""

        try:
            profile = self.get_by_id(instructor_id, load_relationships=False)
            if not profile:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")

            profile.bgc_invited_at = when
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update bgc_invited_at for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to update background check invite timestamp") from exc

    def set_pre_adverse_notice(self, instructor_id: str, notice_id: str, sent_at: datetime) -> None:
        """Persist metadata for the latest pre-adverse notice."""

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update(
                    {
                        self.model.bgc_pre_adverse_notice_id: notice_id,
                        self.model.bgc_pre_adverse_sent_at: sent_at,
                    }
                )
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to persist pre-adverse metadata for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to persist pre-adverse metadata") from exc

    def mark_review_email_sent(self, instructor_id: str, sent_at: datetime) -> None:
        """Persist when the neutral review status email was delivered."""

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update({self.model.bgc_review_email_sent_at: sent_at})
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to persist review email timestamp for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to persist review email metadata") from exc

    def set_final_adverse_sent_at(self, instructor_id: str, sent_at: datetime) -> None:
        """Store when the final adverse email was delivered."""

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update({self.model.bgc_final_adverse_sent_at: sent_at})
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update final adverse timestamp for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to persist final adverse timestamp") from exc

    def record_adverse_event(self, instructor_id: str, notice_id: str, event_type: str) -> str:
        """Insert an idempotency marker for adverse-action notifications."""

        try:
            event = BGCAdverseActionEvent(
                profile_id=instructor_id, notice_id=notice_id, event_type=event_type
            )
            self.db.add(event)
            self.db.flush()
            return cast(str, event.id)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to record adverse-action event for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to record adverse-action event") from exc

    def has_adverse_event(self, instructor_id: str, notice_id: str, event_type: str) -> bool:
        """Return True if an adverse-action event marker already exists."""

        try:
            exists = (
                self.db.query(BGCAdverseActionEvent.id)
                .filter(
                    BGCAdverseActionEvent.profile_id == instructor_id,
                    BGCAdverseActionEvent.notice_id == notice_id,
                    BGCAdverseActionEvent.event_type == event_type,
                )
                .first()
            )
            return exists is not None
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to check adverse-action event for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to check adverse-action event") from exc

    def count_pending_older_than(self, days: int) -> int:
        """Return count of instructors pending longer than the provided number of days."""

        cutoff = datetime.now(timezone.utc) - timedelta(days=max(days, 0))
        try:
            total = (
                self.db.query(func.count(self.model.id))
                .filter(
                    self.model.bgc_status == "pending",
                    self.model.updated_at <= cutoff,
                )
                .scalar()
            )
            return int(total or 0)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to count pending background checks older than %s days: %s",
                days,
                str(exc),
            )
            raise RepositoryException("Failed to count pending background checks") from exc

    def set_dispute_open(self, instructor_id: str, note: str | None) -> None:
        """Mark an instructor's background check as disputed with optional note."""

        now = datetime.now(timezone.utc)
        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update(
                    {
                        self.model.bgc_in_dispute: True,
                        self.model.bgc_dispute_opened_at: now,
                        self.model.bgc_dispute_resolved_at: None,
                        self.model.bgc_dispute_note: note,
                    }
                )
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to open dispute for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to mark dispute open") from exc

    def set_dispute_resolved(self, instructor_id: str, note: str | None) -> None:
        """Resolve an instructor's background check dispute and persist a note."""

        now = datetime.now(timezone.utc)
        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update(
                    {
                        self.model.bgc_in_dispute: False,
                        self.model.bgc_dispute_resolved_at: now,
                        self.model.bgc_dispute_note: note,
                    }
                )
            )
            if updated == 0:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to resolve dispute for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to resolve dispute") from exc

    def list_expiring_within(self, days: int, limit: int = 1000) -> list[InstructorProfile]:
        """Return instructors whose background checks expire within the given window."""

        try:
            now = datetime.now(timezone.utc)
            end = now + timedelta(days=max(days, 0))
            results = (
                self.db.query(self.model)
                .options(selectinload(self.model.user))
                .filter(
                    self.model.bgc_valid_until.isnot(None),
                    self.model.bgc_valid_until >= now,
                    self.model.bgc_valid_until <= end,
                )
                .order_by(
                    self.model.bgc_valid_until.asc(),
                    self.model.id.asc(),
                )
                .limit(limit)
                .all()
            )
            return cast(List[InstructorProfile], results)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to list expiring background checks within %s days: %s",
                days,
                str(exc),
            )
            raise RepositoryException("Failed to list expiring background checks") from exc

    def list_expired(self, limit: int = 1000) -> list[InstructorProfile]:
        """Return instructors whose background checks have expired while live."""

        try:
            now = datetime.now(timezone.utc)
            results = (
                self.db.query(self.model)
                .options(selectinload(self.model.user))
                .filter(
                    self.model.bgc_valid_until.isnot(None),
                    self.model.bgc_valid_until < now,
                    self.model.is_live.is_(True),
                )
                .order_by(
                    self.model.bgc_valid_until.asc(),
                    self.model.id.asc(),
                )
                .limit(limit)
                .all()
            )
            return cast(List[InstructorProfile], results)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to list expired background checks: %s",
                str(exc),
            )
            raise RepositoryException("Failed to list expired background checks") from exc

    def append_history(
        self,
        instructor_id: str,
        report_id: str | None,
        *,
        result: str,
        package: str | None,
        env: str,
        completed_at: datetime,
    ) -> str:
        """Append a background check completion record."""

        try:
            record = BackgroundCheck(
                instructor_id=instructor_id,
                report_id_enc=encrypt_str(report_id) if report_id else None,
                result=result,
                package=package,
                env=env,
                completed_at=completed_at,
            )
            self.db.add(record)
            self.db.flush()
            return str(record.id)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to append background check history for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to append background check history") from exc

    def get_history(
        self,
        instructor_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[BackgroundCheck]:
        """Fetch background check history entries in reverse-chronological order."""

        try:
            query = (
                self.db.query(BackgroundCheck)
                .filter(BackgroundCheck.instructor_id == instructor_id)
                .order_by(desc(BackgroundCheck.created_at), desc(BackgroundCheck.id))
            )

            if cursor:
                query = query.filter(BackgroundCheck.id < cursor)

            return list(query.limit(max(limit, 1)).all())
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load background check history for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to load background check history") from exc

    def record_bgc_consent(
        self,
        instructor_id: str,
        *,
        consent_version: str,
        ip_address: str | None,
    ) -> BGCConsent:
        """Persist a new consent acknowledgement for the instructor."""

        try:
            consent = BGCConsent(
                instructor_id=instructor_id,
                consent_version=consent_version,
                consented_at=datetime.now(timezone.utc),
                ip_address=ip_address,
            )
            self.db.add(consent)
            self.db.flush()
            return consent
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to persist background check consent for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to record background check consent") from exc

    def has_recent_consent(self, instructor_id: str, window: timedelta) -> bool:
        """Return True when instructor has consented within the provided window."""

        try:
            latest = self.latest_consent(instructor_id)
            if not latest:
                return False
            threshold = datetime.now(timezone.utc) - window
            return bool(latest.consented_at and latest.consented_at >= threshold)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to check background check consent recency for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to verify consent recency") from exc
