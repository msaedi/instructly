"""Shared eager-loading helpers for instructor profile queries."""

from __future__ import annotations

from typing import Any, Optional, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query, contains_eager, joinedload, selectinload

from ...core.exceptions import RepositoryException
from ...models.address import InstructorServiceArea
from ...models.instructor import InstructorProfile
from ...models.service_catalog import InstructorService as Service
from ...models.user import User
from .mixin_base import InstructorProfileRepositoryMixinBase


class EagerLoadingMixin(InstructorProfileRepositoryMixinBase):
    """Relationship-loading helpers and detail query building blocks."""

    def _detail_options(self) -> tuple[Any, ...]:
        """Common eager-loading strategy for profile detail views."""
        return (
            contains_eager(InstructorProfile.user)
            .selectinload(User.service_areas)
            .joinedload(InstructorServiceArea.neighborhood),
            selectinload(InstructorProfile.instructor_services).joinedload(Service.catalog_entry),
            selectinload(InstructorProfile.instructor_services).joinedload(Service.format_prices),
        )

    def get_by_id_join_user(self, instructor_id: str) -> Optional[InstructorProfile]:
        """Fetch an instructor profile with user eager-loaded."""

        try:
            return cast(
                Optional[InstructorProfile],
                self.db.query(self.model)
                .options(joinedload(self.model.user))
                .filter(self.model.id == instructor_id)
                .first(),
            )
        except SQLAlchemyError as exc:
            self.logger.error(
                "Failed to load instructor profile %s with user: %s",
                instructor_id,
                str(exc),
            )
            raise RepositoryException("Failed to load instructor profile") from exc

    def _apply_eager_loading(self, query: Query) -> Query:
        """Override eager loading used by BaseRepository.get_by_id()."""
        return query.options(
            selectinload(InstructorProfile.user)
            .selectinload(User.service_areas)
            .selectinload(InstructorServiceArea.neighborhood),
            selectinload(InstructorProfile.instructor_services).selectinload(Service.catalog_entry),
        )

    def get_bgc_case_base_query(self) -> Query:
        """
        Get base query for BGC cases with user relationship loaded.

        Returns a SQLAlchemy Query object that can be further filtered.
        """
        return self.db.query(self.model).options(selectinload(self.model.user))
