"""Repositories for address and spatial models."""

from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.address import InstructorServiceArea, NYCNeighborhood, UserAddress
from ..models.region_boundary import RegionBoundary
from .base_repository import BaseRepository


class UserAddressRepository(BaseRepository[UserAddress]):
    def __init__(self, db: Session):
        super().__init__(db, UserAddress)

    def list_for_user(self, user_id: str, active_only: bool = True) -> List[UserAddress]:
        query = self._build_query().filter(UserAddress.user_id == user_id)
        if active_only:
            query = query.filter(UserAddress.is_active.is_(True))
        return self._execute_query(query.order_by(UserAddress.is_default.desc(), UserAddress.created_at.desc()))

    def unset_default(self, user_id: str) -> int:
        return (
            self.db.query(UserAddress)
            .filter(UserAddress.user_id == user_id, UserAddress.is_default.is_(True))
            .update({"is_default": False})
        )


class NYCNeighborhoodRepository(BaseRepository[NYCNeighborhood]):
    def __init__(self, db: Session):
        super().__init__(db, NYCNeighborhood)

    def get_by_ntacode(self, ntacode: str) -> Optional[NYCNeighborhood]:
        return self.find_one_by(ntacode=ntacode)


class InstructorServiceAreaRepository(BaseRepository[InstructorServiceArea]):
    def __init__(self, db: Session):
        super().__init__(db, InstructorServiceArea)

    def list_for_instructor(self, instructor_id: str, active_only: bool = True) -> List[InstructorServiceArea]:
        query = self._build_query().filter(InstructorServiceArea.instructor_id == instructor_id)
        if active_only:
            query = query.filter(InstructorServiceArea.is_active.is_(True))
        return self._execute_query(query)

    def replace_areas(self, instructor_id: str, neighborhood_ids: List[str]) -> int:
        # Soft-clear existing
        (
            self.db.query(InstructorServiceArea)
            .filter(InstructorServiceArea.instructor_id == instructor_id)
            .update({"is_active": False})
        )
        # Upsert new active
        for nid in neighborhood_ids:
            existing = (
                self.db.query(InstructorServiceArea)
                .filter(
                    InstructorServiceArea.instructor_id == instructor_id,
                    InstructorServiceArea.neighborhood_id == nid,
                )
                .first()
            )
            if existing:
                existing.is_active = True
            else:
                self.create(instructor_id=instructor_id, neighborhood_id=nid, is_active=True)
        return len(neighborhood_ids)
