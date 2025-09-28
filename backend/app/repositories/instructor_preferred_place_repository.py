"""Repository for instructor preferred places (teaching/public spaces)."""

from __future__ import annotations

from typing import List, cast

from sqlalchemy.orm import Session

from ..models.instructor import InstructorPreferredPlace
from .base_repository import BaseRepository


class InstructorPreferredPlaceRepository(BaseRepository[InstructorPreferredPlace]):
    """Data access layer for InstructorPreferredPlace records."""

    def __init__(self, db: Session):
        super().__init__(db, InstructorPreferredPlace)

    def list_for_instructor(self, instructor_id: str) -> List[InstructorPreferredPlace]:
        return cast(
            List[InstructorPreferredPlace],
            self._build_query()
            .filter(InstructorPreferredPlace.instructor_id == instructor_id)
            .order_by(InstructorPreferredPlace.kind, InstructorPreferredPlace.position)
            .all(),
        )

    def list_for_instructor_and_kind(
        self, instructor_id: str, kind: str
    ) -> List[InstructorPreferredPlace]:
        return cast(
            List[InstructorPreferredPlace],
            self._build_query()
            .filter(
                InstructorPreferredPlace.instructor_id == instructor_id,
                InstructorPreferredPlace.kind == kind,
            )
            .order_by(InstructorPreferredPlace.position)
            .all(),
        )

    def delete_for_kind(self, instructor_id: str, kind: str) -> int:
        deleted = (
            self.db.query(InstructorPreferredPlace)
            .filter(
                InstructorPreferredPlace.instructor_id == instructor_id,
                InstructorPreferredPlace.kind == kind,
            )
            .delete(synchronize_session=False)
        )
        return int(deleted or 0)

    def create_for_kind(
        self,
        instructor_id: str,
        kind: str,
        address: str,
        label: str | None,
        position: int,
        place_id: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
    ) -> InstructorPreferredPlace:
        return self.create(
            instructor_id=instructor_id,
            kind=kind,
            address=address,
            label=label,
            position=position,
            place_id=place_id,
            lat=lat,
            lng=lng,
        )
