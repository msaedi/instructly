"""Best-effort click capture for the self-learning location alias loop."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.location_alias import NYC_CITY_ID
from app.repositories.address_repository import InstructorServiceAreaRepository
from app.repositories.search_query_repository import SearchQueryRepository
from app.repositories.unresolved_location_query_repository import UnresolvedLocationQueryRepository
from app.services.search.alias_learning_service import AliasLearningService

logger = logging.getLogger(__name__)


class LocationLearningClickService:
    """
    Records click outcomes for unresolved location searches.

    If a search had `location_not_found=True`, and the user clicks an instructor result, we:
    - attribute that click to the instructor's primary service area region
    - update `unresolved_location_queries` click evidence
    - attempt to promote it to a learned `location_aliases` mapping
    """

    def __init__(self, db: Session, *, city_id: str = NYC_CITY_ID) -> None:
        self.search_query_repo = SearchQueryRepository(db)
        self.service_area_repo = InstructorServiceAreaRepository(db)
        self.unresolved_repo = UnresolvedLocationQueryRepository(db, city_id=city_id)
        self.learning_service = AliasLearningService(db, city_id=city_id)

    def capture_location_learning_click(
        self, *, search_query_id: str, instructor_user_id: str
    ) -> None:
        normalized = self.search_query_repo.get_normalized_query(search_query_id)
        if not isinstance(normalized, dict):
            return

        if normalized.get("location_not_found") is not True:
            return

        location_text = normalized.get("location")
        if not isinstance(location_text, str) or not location_text.strip():
            return

        neighborhood_id = self.service_area_repo.get_primary_active_neighborhood_id(
            instructor_user_id
        )
        if not neighborhood_id:
            return

        self.unresolved_repo.record_click(
            location_text,
            region_boundary_id=neighborhood_id,
            original_query=location_text,
        )

        self.learning_service.maybe_learn_from_query(location_text)
