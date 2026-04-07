"""Founding instructor cap enforcement helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from ...core.exceptions import RepositoryException
from ...models.instructor import InstructorProfile
from .mixin_base import InstructorProfileRepositoryMixinBase


class FoundingInstructorMixin(InstructorProfileRepositoryMixinBase):
    """Atomic founding instructor claim operations."""

    _FOUNDING_CLAIM_LOCK_KEY = 0x494E5354_464F554E  # "INSTFOUN" in hex

    def count_founding_instructors(self) -> int:
        """Count total founding instructors for cap enforcement."""
        try:
            total = (
                self.db.query(func.count(InstructorProfile.id))
                .filter(InstructorProfile.is_founding_instructor.is_(True))
                .scalar()
            )
            return int(total or 0)
        except SQLAlchemyError as exc:
            self.logger.error("Failed to count founding instructors: %s", str(exc))
            raise RepositoryException("Failed to count founding instructors") from exc

    def try_claim_founding_status(self, profile_id: str, cap: int) -> tuple[bool, int]:
        """
        Atomically attempt to grant founding instructor status.

        Uses PostgreSQL advisory lock to serialize founding status claims.
        This avoids table-level row locks while ensuring correct cap enforcement.

        Returns (success, current_count_after_attempt).
        """
        if cap <= 0:
            return False, 0

        try:
            with self.db.begin_nested():
                self.db.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": self._FOUNDING_CLAIM_LOCK_KEY},
                )

                profile = (
                    self.db.query(InstructorProfile)
                    .filter(InstructorProfile.id == profile_id)
                    .first()
                )

                current_count = self.count_founding_instructors()

                if not profile:
                    return False, current_count

                if profile.is_founding_instructor:
                    return True, current_count

                if current_count >= cap:
                    return False, current_count

                profile.is_founding_instructor = True
                profile.founding_granted_at = datetime.now(timezone.utc)
                self.db.flush()
                return True, current_count + 1
        except SQLAlchemyError as exc:
            self.logger.error("Failed to claim founding instructor status: %s", str(exc))
            raise RepositoryException("Failed to claim founding instructor status") from exc
