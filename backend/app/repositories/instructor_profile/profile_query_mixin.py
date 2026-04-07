"""Profile CRUD and public/admin-facing lookup helpers."""

from __future__ import annotations

from typing import List, Optional, cast

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query

from ...core.exceptions import RepositoryException
from ...models.instructor import InstructorProfile
from ...models.user import User
from .mixin_base import InstructorProfileRepositoryMixinBase


class ProfileQueryMixin(InstructorProfileRepositoryMixinBase):
    """Core instructor profile lookup and mutation helpers."""

    def _apply_public_visibility(self, query: Query) -> Query:
        """Restrict results to instructors eligible for public display."""

        return query.filter(
            InstructorProfile.is_live.is_(True),
            InstructorProfile.bgc_status == "passed",
            InstructorProfile.identity_name_mismatch.is_(False),
            InstructorProfile.bgc_name_mismatch.is_(False),
        )

    def get_public_by_id(self, instructor_id: str) -> Optional[InstructorProfile]:
        """Return a public-facing instructor profile when visible."""

        try:
            query = self._apply_public_visibility(
                self.db.query(InstructorProfile)
                .join(InstructorProfile.user)
                .options(*self._detail_options())
            )
            return cast(
                Optional[InstructorProfile],
                query.filter(
                    or_(
                        InstructorProfile.user_id == instructor_id,
                        InstructorProfile.id == instructor_id,
                    )
                ).first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load public instructor profile %s: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to load public instructor profile") from exc

    def get_by_user_id(self, user_id: str) -> Optional[InstructorProfile]:
        """
        Get instructor profile by user ID.

        Used by PrivacyService for data export and deletion.
        """
        return cast(
            Optional[InstructorProfile],
            self.db.query(InstructorProfile).filter(InstructorProfile.user_id == user_id).first(),
        )

    def list_active_for_tier_evaluation(self) -> List[InstructorProfile]:
        """Return instructor profiles whose user accounts are currently active."""

        return cast(
            List[InstructorProfile],
            self.db.query(InstructorProfile)
            .join(InstructorProfile.user)
            .filter(User.account_status == "active")
            .filter(InstructorProfile.is_founding_instructor.is_(False))
            .order_by(InstructorProfile.id.asc())
            .all(),
        )

    def get_all_with_details(self, skip: int = 0, limit: int = 100) -> List[InstructorProfile]:
        """
        Get all instructor profiles with user and services eager loaded.

        The service layer handles filtering inactive services when converting to DTOs.
        """
        try:
            query = self.db.query(InstructorProfile)
            query = query.join(InstructorProfile.user)
            query = query.filter(User.account_status == "active")
            query = self._apply_public_visibility(query)
            query = query.options(*self._detail_options())
            query = query.order_by(InstructorProfile.id)
            query = query.distinct().offset(skip).limit(limit)

            profiles = cast(List[InstructorProfile], query.all())

            return profiles

        except Exception as e:
            self.logger.error("Error getting all profiles with details: %s", str(e))
            raise RepositoryException(f"Failed to get instructor profiles: {str(e)}")

    def get_by_user_id_with_details(self, user_id: str) -> Optional[InstructorProfile]:
        """
        Get a single instructor profile by user_id with all relationships loaded.

        The service layer handles filtering inactive services when converting to DTOs.
        """
        try:
            profile = cast(
                Optional[InstructorProfile],
                (
                    self.db.query(InstructorProfile)
                    .join(InstructorProfile.user)
                    .options(*self._detail_options())
                    .filter(InstructorProfile.user_id == user_id)
                    .first()
                ),
            )

            return profile

        except Exception as e:
            self.logger.error("Error getting profile by user_id: %s", str(e))
            raise RepositoryException(f"Failed to get instructor profile: {str(e)}")

    def count_profiles(self) -> int:
        """Count total number of instructor profiles."""
        try:
            return cast(int, self.db.query(InstructorProfile).count())
        except Exception as e:
            self.logger.error("Error counting active profiles: %s", str(e))
            raise RepositoryException(f"Failed to count profiles: {str(e)}")

    def set_live(self, instructor_id: str, is_live: bool) -> None:
        """Toggle instructor live status without loading the full profile."""

        try:
            updated = (
                self.db.query(self.model)
                .filter(self.model.id == instructor_id)
                .update({self.model.is_live: is_live})
            )
            if not updated:
                raise RepositoryException(f"Instructor profile {instructor_id} not found")
            self.db.flush()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to update live status for instructor %s: %s",
                instructor_id,
                str(exc),
            )
            self.db.rollback()
            raise RepositoryException("Failed to update live status") from exc
