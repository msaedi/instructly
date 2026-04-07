"""Shared typing surface for instructor profile repository mixins."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Query, Session

from ...models.instructor import InstructorProfile

_UNSET = object()

if TYPE_CHECKING:

    class InstructorProfileRepositoryMixinBase:
        """Typed attribute/method surface supplied by the instructor profile facade."""

        db: Session
        logger: logging.Logger
        model: type[InstructorProfile]
        dialect_name: str

        def _apply_eager_loading(self, query: Query) -> Query:
            ...

        def _apply_public_visibility(self, query: Query) -> Query:
            ...

        def _detail_options(self) -> tuple[Any, ...]:
            ...

        def _resolve_profile_id_by_report(self, report_id: str | None) -> str | None:
            ...

        def get_by_id(
            self, id: str, load_relationships: bool = True
        ) -> Optional[InstructorProfile]:
            ...

        def commit(self) -> None:
            ...

else:

    class InstructorProfileRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
        model: type[InstructorProfile]
        dialect_name: str

        def commit(self) -> None:
            """Commit pending changes to the database."""
            self.db.commit()
