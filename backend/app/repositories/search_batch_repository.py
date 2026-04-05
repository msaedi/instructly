"""Batched database queries for NL search pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.location_alias import NYC_CITY_ID, LocationAlias
from app.models.region_boundary import RegionBoundary
from app.repositories.location_resolution_repository import LocationResolutionRepository
from app.repositories.retriever_repository import RetrieverRepository


@dataclass(frozen=True)
class RegionInfo:
    """Lightweight region metadata for in-memory lookup."""

    region_id: str
    region_name: str
    borough: Optional[str]
    display_name: Optional[str] = None
    display_key: Optional[str] = None


@dataclass(frozen=True)
class RegionEmbeddingInfo(RegionInfo):
    """Region metadata with name embedding for in-memory similarity."""

    embedding: List[float] = field(default_factory=list)
    norm: float = 0.0


@dataclass(frozen=True)
class RegionLookup:
    """Preloaded region lookup data for location resolution."""

    region_names: List[str]
    by_name: Dict[str, RegionInfo]
    by_id: Dict[str, RegionInfo]
    embeddings: List[RegionEmbeddingInfo]
    by_display_key: Dict[str, List[RegionInfo]] = field(default_factory=dict)


@dataclass(frozen=True)
class CachedAliasInfo:
    """Cached LLM alias metadata for fast resolution."""

    confidence: float
    is_resolved: bool
    is_ambiguous: bool
    region_id: Optional[str]
    candidate_region_ids: List[str]


class SearchBatchRepository:
    """Groups search-related DB reads for batch execution."""

    def __init__(
        self, db: Session, *, region_code: str = "nyc", city_id: str = NYC_CITY_ID
    ) -> None:
        self.db = db
        self.region_code = region_code
        self.city_id = city_id
        self._location_repo = LocationResolutionRepository(
            db, region_code=region_code, city_id=city_id
        )
        self._retriever_repo = RetrieverRepository(db)

    def has_service_embeddings(self) -> bool:
        return self._retriever_repo.has_embeddings()

    def text_search(
        self,
        corrected_query: str,
        original_query: str,
        *,
        limit: int,
    ) -> Dict[str, Tuple[float, Dict[str, Any]]]:
        rows = self._retriever_repo.text_search(corrected_query, original_query, limit)
        return {
            str(row["id"]): (
                float(row["text_score"]),
                {
                    "service_catalog_id": row["catalog_id"],
                    "name": row["name"],
                    "description": row["description"],
                    "min_hourly_rate": row["min_hourly_rate"],
                    "price_per_hour": row.get("price_per_hour", row["min_hourly_rate"]),
                    "instructor_id": row["instructor_id"],
                    "subcategory_id": row.get("subcategory_id"),
                },
            )
            for row in rows
        }

    def vector_search(
        self,
        embedding: List[float],
        *,
        limit: int,
    ) -> Dict[str, Tuple[float, Dict[str, Any]]]:
        rows = self._retriever_repo.vector_search(embedding, limit)
        return {
            str(row["id"]): (
                float(row["vector_score"]),
                {
                    "service_catalog_id": row["catalog_id"],
                    "name": row["name"],
                    "description": row["description"],
                    "min_hourly_rate": row["min_hourly_rate"],
                    "price_per_hour": row.get("price_per_hour", row["min_hourly_rate"]),
                    "instructor_id": row["instructor_id"],
                    "subcategory_id": row.get("subcategory_id"),
                },
            )
            for row in rows
        }

    def get_best_fuzzy_score(self, normalized: str) -> float:
        return self._location_repo.get_best_fuzzy_score(normalized)

    def get_fuzzy_candidate_names(self, normalized: str, *, limit: int = 5) -> List[str]:
        return self._location_repo.list_fuzzy_region_names(normalized, limit=limit)

    def get_cached_llm_alias(self, normalized: str) -> Optional[CachedAliasInfo]:
        row = self._location_repo.find_cached_alias(normalized, source="llm")
        if not row or not isinstance(row, LocationAlias):
            return None

        candidate_ids = list(row.candidate_region_ids or [])
        return CachedAliasInfo(
            confidence=float(row.confidence or 0.5),
            is_resolved=bool(row.is_resolved),
            is_ambiguous=bool(row.is_ambiguous),
            region_id=str(row.region_boundary_id) if row.region_boundary_id else None,
            candidate_region_ids=[str(cid) for cid in candidate_ids if cid],
        )

    def load_region_lookup(self, *, limit: int = 2000) -> RegionLookup:
        regions = self._location_repo.list_regions(limit=limit)

        region_names: List[str] = []
        by_name: Dict[str, RegionInfo] = {}
        by_id: Dict[str, RegionInfo] = {}
        embeddings: List[RegionEmbeddingInfo] = []
        by_display_key: Dict[str, List[RegionInfo]] = {}

        for region in regions:
            if not isinstance(region, RegionBoundary):
                continue

            region_id = str(region.id)
            region_name = str(region.region_name or "").strip()
            borough = getattr(region, "parent_region", None)
            display_name_raw = getattr(region, "display_name", None)
            display_name = str(display_name_raw) if display_name_raw else None
            display_key_raw = getattr(region, "display_key", None)
            display_key = str(display_key_raw) if display_key_raw else None
            info = RegionInfo(
                region_id=region_id,
                region_name=region_name,
                borough=borough,
                display_name=display_name,
                display_key=display_key,
            )

            if region_name:
                key = region_name.lower()
                if key not in by_name:
                    region_names.append(region_name)
                    by_name[key] = info

            if region_id and region_id not in by_id:
                by_id[region_id] = info

            if display_key:
                by_display_key.setdefault(display_key, []).append(info)

            embedding_raw = getattr(region, "name_embedding", None)
            if embedding_raw is None:
                continue

            embedding = [float(x) for x in list(embedding_raw)]
            norm = math.sqrt(sum(x * x for x in embedding)) if embedding else 0.0
            if norm <= 0:
                continue
            embeddings.append(
                RegionEmbeddingInfo(
                    region_id=region_id,
                    region_name=region_name,
                    borough=borough,
                    display_name=display_name,
                    display_key=display_key,
                    embedding=embedding,
                    norm=norm,
                )
            )

        for display_key, infos in by_display_key.items():
            by_display_key[display_key] = sorted(
                infos,
                key=lambda info: (info.region_name.strip().lower(), info.region_id),
            )

        return RegionLookup(
            region_names=region_names,
            by_name=by_name,
            by_id=by_id,
            embeddings=embeddings,
            by_display_key=by_display_key,
        )
