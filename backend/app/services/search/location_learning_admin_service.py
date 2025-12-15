"""Admin service for the location self-learning loop."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.location_alias import NYC_CITY_ID
from app.repositories.location_alias_repository import LocationAliasRepository
from app.repositories.location_resolution_repository import LocationResolutionRepository
from app.repositories.unresolved_location_query_repository import UnresolvedLocationQueryRepository
from app.schemas.admin_location_learning_responses import (
    AdminLocationLearningClickCount,
    AdminLocationLearningLearnedAliasItem,
    AdminLocationLearningPendingAliasesResponse,
    AdminLocationLearningPendingAliasItem,
    AdminLocationLearningProcessResponse,
    AdminLocationLearningUnresolvedQueriesResponse,
    AdminLocationLearningUnresolvedQueryItem,
)
from app.services.search.alias_learning_service import AliasLearningService


class LocationLearningAdminService:
    """Service layer for admin-only location learning endpoints."""

    def __init__(
        self,
        db: Session,
        *,
        city_id: str = NYC_CITY_ID,
        region_code: str = "nyc",
    ) -> None:
        self.unresolved_repo = UnresolvedLocationQueryRepository(db, city_id=city_id)
        self.location_resolution_repo = LocationResolutionRepository(
            db, region_code=region_code, city_id=city_id
        )
        self.location_alias_repo = LocationAliasRepository(db, city_id=city_id)
        self.learning_service = AliasLearningService(db, city_id=city_id, region_code=region_code)

    def list_unresolved(self, *, limit: int) -> AdminLocationLearningUnresolvedQueriesResponse:
        rows = self.unresolved_repo.list_pending(limit=limit)

        region_ids: set[str] = set()
        for row in rows:
            counts = row.click_region_counts or {}
            if isinstance(counts, dict):
                region_ids.update(str(k) for k in counts.keys() if k)

        region_name_by_id: dict[str, str] = {}
        if region_ids:
            regions = self.location_resolution_repo.get_regions_by_ids(list(region_ids))
            region_name_by_id = {str(r.id): str(r.region_name) for r in regions if r and r.id}

        def _format_clicks(counts: object) -> list[AdminLocationLearningClickCount]:
            if not isinstance(counts, dict):
                return []

            items: list[AdminLocationLearningClickCount] = []
            for region_id, count in counts.items():
                try:
                    c_int = int(count or 0)
                except Exception:
                    continue

                rid = str(region_id)
                items.append(
                    AdminLocationLearningClickCount(
                        region_boundary_id=rid,
                        region_name=region_name_by_id.get(rid),
                        count=c_int,
                    )
                )

            items.sort(key=lambda x: x.count, reverse=True)
            return items

        queries: list[AdminLocationLearningUnresolvedQueryItem] = []
        for row in rows:
            queries.append(
                AdminLocationLearningUnresolvedQueryItem(
                    id=str(row.id),
                    query_normalized=str(row.query_normalized),
                    search_count=int(row.search_count or 0),
                    unique_user_count=int(row.unique_user_count or 0),
                    click_count=int(row.click_count or 0),
                    clicks=_format_clicks(row.click_region_counts),
                    sample_original_queries=[
                        str(s) for s in (row.sample_original_queries or []) if s
                    ],
                    first_seen_at=row.first_seen_at,
                    last_seen_at=row.last_seen_at,
                    status=str(row.status),
                )
            )

        return AdminLocationLearningUnresolvedQueriesResponse(queries=queries, total=len(queries))

    def list_pending_aliases(
        self, *, limit: int = 500
    ) -> AdminLocationLearningPendingAliasesResponse:
        aliases = self.location_alias_repo.list_by_source_and_status(
            source="user_learning",
            status="pending_review",
            limit=limit,
        )

        items: list[AdminLocationLearningPendingAliasItem] = []
        for alias in aliases:
            items.append(
                AdminLocationLearningPendingAliasItem(
                    id=str(alias.id),
                    alias_normalized=str(alias.alias_normalized),
                    region_boundary_id=str(alias.region_boundary_id)
                    if alias.region_boundary_id
                    else None,
                    confidence=float(alias.confidence or 0.0),
                    user_count=int(alias.user_count or 0),
                    status=str(alias.status),
                    created_at=alias.created_at,
                )
            )
        return AdminLocationLearningPendingAliasesResponse(aliases=items)

    def process(self, *, limit: int) -> AdminLocationLearningProcessResponse:
        learned = self.learning_service.process_pending(limit=limit)
        return AdminLocationLearningProcessResponse(
            learned=[
                AdminLocationLearningLearnedAliasItem(
                    alias_normalized=l.alias_normalized,
                    region_boundary_id=l.region_boundary_id,
                    confidence=l.confidence,
                    status=l.status,
                    confirmations=l.confirmations,
                )
                for l in learned
            ],
            learned_count=len(learned),
        )

    def set_alias_status(self, alias_id: str, status: str) -> bool:
        return self.location_alias_repo.update_status(alias_id, status)

    def approve_alias(self, alias_id: str) -> bool:
        return self.set_alias_status(alias_id, "active")

    def reject_alias(self, alias_id: str) -> bool:
        return self.set_alias_status(alias_id, "deprecated")

    def resolve_region_name(self, region_boundary_id: Optional[str]) -> Optional[str]:
        if not region_boundary_id:
            return None
        region = self.location_resolution_repo.get_region_by_id(region_boundary_id)
        return str(region.region_name) if region else None
