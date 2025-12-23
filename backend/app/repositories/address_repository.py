"""Repositories for address and spatial models."""

from typing import List, Optional, cast

from sqlalchemy.orm import Session, selectinload

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
        return self._execute_query(
            query.order_by(
                UserAddress.is_default.desc(),
                UserAddress.created_at.desc(),
                UserAddress.id.asc(),
            )
        )

    def get_default_address(self, user_id: str) -> Optional[UserAddress]:
        """
        Get the user's default address, or the first active address if no default is set.

        Returns:
            The default UserAddress, or None if no active address exists.
        """
        query = (
            self._build_query()
            .filter(UserAddress.user_id == user_id)
            .filter(UserAddress.is_active.is_(True))
            .order_by(
                UserAddress.is_default.desc(),
                UserAddress.created_at.desc(),
            )
            .limit(1)
        )
        results = self._execute_query(query)
        return results[0] if results else None

    def unset_default(self, user_id: str) -> int:
        updated = (
            self.db.query(UserAddress)
            .filter(UserAddress.user_id == user_id, UserAddress.is_default.is_(True))
            .update({"is_default": False})
        )
        return int(updated or 0)


class NYCNeighborhoodRepository(BaseRepository[NYCNeighborhood]):
    def __init__(self, db: Session):
        super().__init__(db, NYCNeighborhood)

    def get_by_ntacode(self, ntacode: str) -> Optional[NYCNeighborhood]:
        return self.find_one_by(ntacode=ntacode)


class InstructorServiceAreaRepository(BaseRepository[InstructorServiceArea]):
    def __init__(self, db: Session):
        super().__init__(db, InstructorServiceArea)

    def list_for_instructor(
        self, instructor_id: str, active_only: bool = True
    ) -> List[InstructorServiceArea]:
        query = (
            self._build_query()
            .options(selectinload(InstructorServiceArea.neighborhood))
            .filter(InstructorServiceArea.instructor_id == instructor_id)
        )
        if active_only:
            query = query.filter(InstructorServiceArea.is_active.is_(True))
        return self._execute_query(query)

    def list_for_instructors(
        self, instructor_ids: List[str], active_only: bool = True
    ) -> dict[str, List[InstructorServiceArea]]:
        """
        Fetch service areas for multiple instructors in a single query.

        This is an N+1 optimization method that batches service area lookups.

        Args:
            instructor_ids: List of instructor user IDs
            active_only: If True, only return active service areas

        Returns:
            Dict mapping instructor_id -> List[InstructorServiceArea]
        """
        if not instructor_ids:
            return {}

        query = (
            self._build_query()
            .options(selectinload(InstructorServiceArea.neighborhood))
            .filter(InstructorServiceArea.instructor_id.in_(instructor_ids))
        )
        if active_only:
            query = query.filter(InstructorServiceArea.is_active.is_(True))

        results = self._execute_query(query)

        # Group by instructor_id
        grouped: dict[str, List[InstructorServiceArea]] = {iid: [] for iid in instructor_ids}
        for area in results:
            if area.instructor_id in grouped:
                grouped[area.instructor_id].append(area)

        return grouped

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

    def upsert_area(
        self,
        instructor_id: str,
        neighborhood_id: str,
        coverage_type: str | None = None,
        max_distance_miles: float | None = None,
        is_active: bool = True,
    ) -> InstructorServiceArea:
        existing: InstructorServiceArea | None = (
            self.db.query(InstructorServiceArea)
            .filter(
                InstructorServiceArea.instructor_id == instructor_id,
                InstructorServiceArea.neighborhood_id == neighborhood_id,
            )
            .first()
        )
        if existing:
            existing.is_active = is_active
            if coverage_type is not None:
                existing.coverage_type = coverage_type
            if max_distance_miles is not None:
                existing.max_distance_miles = max_distance_miles
            self.db.add(existing)
            return existing
        return self.create(
            instructor_id=instructor_id,
            neighborhood_id=neighborhood_id,
            coverage_type=coverage_type,
            max_distance_miles=max_distance_miles,
            is_active=is_active,
        )

    def list_neighborhoods_for_instructors(
        self, instructor_ids: List[str]
    ) -> list[InstructorServiceArea]:
        if not instructor_ids:
            return []
        return cast(
            list[InstructorServiceArea],
            self._build_query()
            .options(selectinload(InstructorServiceArea.neighborhood))
            .filter(
                InstructorServiceArea.instructor_id.in_(instructor_ids),
                InstructorServiceArea.is_active.is_(True),
            )
            .order_by(
                InstructorServiceArea.instructor_id.asc(),
                InstructorServiceArea.neighborhood_id.asc(),
            )
            .all(),
        )

    def get_primary_active_neighborhood_id(self, instructor_id: str) -> Optional[str]:
        """
        Best-effort primary neighborhood for an instructor (deterministic).

        Used for self-learning click capture when a user clicks an instructor result after an
        unresolved location search.
        """
        try:
            row = (
                self.db.query(InstructorServiceArea.neighborhood_id)
                .join(RegionBoundary, RegionBoundary.id == InstructorServiceArea.neighborhood_id)
                .filter(
                    InstructorServiceArea.instructor_id == instructor_id,
                    InstructorServiceArea.is_active.is_(True),
                )
                .order_by(RegionBoundary.region_name.asc())
                .first()
            )
            neighborhood_id = getattr(row, "neighborhood_id", None) if row else None
            return str(neighborhood_id) if neighborhood_id else None
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return None
