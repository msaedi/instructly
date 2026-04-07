"""Report, invitation, and candidate binding helpers for background checks."""

from __future__ import annotations

from typing import Any, Optional, Sequence, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from ...core.crypto import decrypt_report_token, encrypt_report_token
from ...core.exceptions import RepositoryException
from ...core.metrics import BGC_REPORT_ID_DECRYPT_TOTAL, BGC_REPORT_ID_ENCRYPT_TOTAL
from ...models.instructor import InstructorProfile
from .mixin_base import _UNSET, InstructorProfileRepositoryMixinBase


class BgcReportBindingMixin(InstructorProfileRepositoryMixinBase):
    """Lookup and binding operations for Checkr-linked identifiers."""

    @staticmethod
    def _encrypt_report_id(report_id: str | None, *, source: str = "write") -> str | None:
        """Encrypt report identifier strings for storage and track metrics."""

        if report_id in (None, ""):
            return report_id

        report_id_str = cast(str, report_id)
        encrypted = encrypt_report_token(report_id_str)
        if encrypted != report_id_str:
            BGC_REPORT_ID_ENCRYPT_TOTAL.labels(source=source).inc()
        return encrypted

    @staticmethod
    def _decrypt_report_id(value: str | None) -> str | None:
        """Decrypt stored report identifiers while tolerating legacy plaintext."""

        if value in (None, ""):
            return value

        try:
            value_str = cast(str, value)
            decrypted = decrypt_report_token(value_str)
        except ValueError:
            return value

        if decrypted != value_str:
            BGC_REPORT_ID_DECRYPT_TOTAL.inc()
        return decrypted

    def _resolve_profile_id_by_report(self, report_id: str | None) -> str | None:
        """Locate the instructor profile identifier matching a Checkr report."""

        if not report_id:
            return None

        try:
            candidates: Sequence[tuple[str, str | None]] = (
                self.db.query(self.model.id, self.model._bgc_report_id)
                .filter(self.model._bgc_report_id.isnot(None))
                .all()
            )
        except SQLAlchemyError as exc:
            self.logger.error("Failed resolving report %s: %s", report_id, str(exc))
            raise RepositoryException("Failed to look up instructor by report id") from exc

        for candidate_id, stored_value in candidates:
            if self._decrypt_report_id(stored_value) == report_id:
                return candidate_id
        return None

    def get_by_report_id(self, report_id: str) -> Optional[InstructorProfile]:
        """Return the instructor profile associated with a Checkr report."""

        try:
            profile_id = self._resolve_profile_id_by_report(report_id)
            if profile_id is None:
                return None

            return cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .options(joinedload(self.model.user))
                .filter(self.model.id == profile_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile by report %s: %s",
                report_id,
                str(exc),
            )
            raise RepositoryException("Failed to load instructor profile by report id") from exc

    def get_by_invitation_id(self, invitation_id: str) -> Optional[InstructorProfile]:
        """Return the instructor profile associated with a Checkr invitation."""

        if not invitation_id:
            return None

        try:
            return cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .filter(self.model.checkr_invitation_id == invitation_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile by invitation %s: %s",
                invitation_id,
                str(exc),
            )
            raise RepositoryException("Failed to load instructor profile by invitation id") from exc

    def get_by_candidate_id(self, candidate_id: str) -> Optional[InstructorProfile]:
        """Return the instructor profile associated with a Checkr candidate."""

        if not candidate_id:
            return None

        try:
            return cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .filter(self.model.checkr_candidate_id == candidate_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile by candidate %s: %s",
                candidate_id,
                str(exc),
            )
            raise RepositoryException("Failed to load instructor profile by candidate id") from exc

    def update_bgc_by_invitation(
        self,
        invitation_id: str,
        *,
        status: str | None = None,
        note: Any = _UNSET,
    ) -> Optional[InstructorProfile]:
        """Update status metadata for the profile matching a Checkr invitation."""

        if not invitation_id:
            return None

        try:
            profile = cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .filter(self.model.checkr_invitation_id == invitation_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile by invitation %s: %s",
                invitation_id,
                str(exc),
            )
            raise RepositoryException(
                "Failed to update background check invitation metadata"
            ) from exc

        if profile is None:
            return None

        if status is not None:
            profile.bgc_status = status
        if note is not _UNSET:
            profile.bgc_note = cast(Optional[str], note)
        self.db.flush()
        return profile

    def update_bgc_by_candidate(
        self,
        candidate_id: str,
        *,
        status: str | None = None,
        note: Any = _UNSET,
    ) -> Optional[InstructorProfile]:
        """Update status metadata for the profile matching a Checkr candidate id."""

        if not candidate_id:
            return None

        try:
            profile = cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .filter(self.model.checkr_candidate_id == candidate_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile by candidate %s: %s",
                candidate_id,
                str(exc),
            )
            raise RepositoryException(
                "Failed to update background check candidate metadata"
            ) from exc

        if profile is None:
            return None

        if status is not None:
            profile.bgc_status = status
        if note is not _UNSET:
            profile.bgc_note = cast(Optional[str], note)
        self.db.flush()
        return profile

    def bind_report_to_candidate(
        self,
        candidate_id: str | None,
        report_id: str,
        *,
        env: str | None = None,
    ) -> str | None:
        """Ensure the candidate-linked profile stores the provided report id."""

        if not candidate_id or not report_id:
            return None

        try:
            profile = cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .filter(self.model.checkr_candidate_id == candidate_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to bind report %s via candidate %s: %s",
                report_id,
                candidate_id,
                str(exc),
            )
            raise RepositoryException("Failed to bind report to candidate") from exc

        if profile is None:
            return None

        current_report = profile.bgc_report_id
        if current_report != report_id:
            profile.bgc_report_id = report_id
        if env and profile.bgc_env != env:
            profile.bgc_env = env

        self.db.flush()
        return str(profile.id)

    def bind_report_to_invitation(
        self,
        invitation_id: str | None,
        report_id: str,
        *,
        env: str | None = None,
    ) -> str | None:
        """Bind a Checkr report to the instructor tracked by an invitation id."""

        if not invitation_id or not report_id:
            return None

        try:
            profile = cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .filter(self.model.checkr_invitation_id == invitation_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to bind report %s via invitation %s: %s",
                report_id,
                invitation_id,
                str(exc),
            )
            raise RepositoryException("Failed to bind report to invitation") from exc

        if profile is None:
            return None

        current_report = profile.bgc_report_id
        if current_report != report_id:
            profile.bgc_report_id = report_id
        if env and profile.bgc_env != env:
            profile.bgc_env = env

        self.db.flush()
        return str(profile.id)

    def find_profile_ids_by_report_fragment(self, fragment: str) -> set[str]:
        """Return profile identifiers whose report matches the provided substring."""

        normalized = (fragment or "").strip().lower()
        if not normalized:
            return set()

        try:
            candidates: Sequence[tuple[str, str | None]] = (
                self.db.query(self.model.id, self.model._bgc_report_id)
                .filter(self.model._bgc_report_id.isnot(None))
                .all()
            )
        except SQLAlchemyError as exc:
            self.logger.error("Failed to search report ids containing '%s': %s", fragment, str(exc))
            raise RepositoryException(
                "Failed to search instructor profiles by report fragment"
            ) from exc

        matches: set[str] = set()
        for candidate_id, stored_value in candidates:
            decrypted = self._decrypt_report_id(stored_value)
            if decrypted and normalized in decrypted.lower():
                matches.add(candidate_id)
        return matches
