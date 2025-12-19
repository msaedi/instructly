"""
Tier 4: Embedding-based location resolution.

This service:
- Embeds user location text (e.g., "museum mile") using OpenAI embeddings
- Finds nearest `region_boundaries` rows via pgvector similarity on `name_embedding`

Notes:
- Only runs when `region_boundaries.name_embedding` is populated (otherwise returns []).
- Designed to be awaited from async contexts (no blocking OpenAI calls).
- Uses strict timeouts to fail fast under load (no retries).
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.services.search.config import get_search_config

logger = logging.getLogger(__name__)

# Strict OpenAI timeouts for async calls.
# Fail fast rather than block the event loop with retries.
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "2.0"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "0"))


class LocationEmbeddingService:
    """Embedding-based semantic matcher for location strings."""

    # Filter out low-confidence candidates (0..1 after normalization)
    # Raised from 0.7 to 0.82 to prevent false positives on nonsense queries
    # (e.g., "madeupplace" was matching to "Baisley Park" at 0.7)
    SIMILARITY_THRESHOLD = 0.82
    # If the top candidate is only slightly better than the second, treat as ambiguous.
    AMBIGUITY_MARGIN = 0.1

    def __init__(self, repository: Any) -> None:
        self._repository = repository
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                timeout=OPENAI_TIMEOUT_S,
                max_retries=OPENAI_MAX_RETRIES,
            )
        return self._client

    async def get_candidates(
        self,
        query: str,
        *,
        limit: int = 5,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return similar region candidates for a location query.

        Output shape:
            [{region_id, region_name, borough, similarity}, ...]
        """
        normalized = " ".join(str(query or "").strip().split())
        if not normalized:
            return []

        # Only attempt when embeddings are populated (avoid unnecessary OpenAI calls).
        has_embeddings = await asyncio.to_thread(self._repository.has_region_name_embeddings)
        if not has_embeddings:
            return []

        if not os.getenv("OPENAI_API_KEY"):
            return []

        embedding = await self._embed_location_text(normalized)
        if not embedding:
            return []

        pairs = await asyncio.to_thread(
            self._repository.find_regions_by_name_embedding,
            embedding,
            limit=limit,
        )
        if not pairs:
            return []

        min_similarity = float(threshold if threshold is not None else self.SIMILARITY_THRESHOLD)
        out: List[Dict[str, Any]] = []
        for region, similarity in pairs:
            try:
                sim_val = float(similarity)
            except Exception:
                continue
            if sim_val < min_similarity:
                continue
            out.append(
                {
                    "region_id": str(region.id),
                    "region_name": str(getattr(region, "region_name", "") or ""),
                    "borough": getattr(region, "parent_region", None),
                    "similarity": sim_val,
                }
            )
        return out

    @classmethod
    def pick_best_or_ambiguous(
        cls, candidates: List[Dict[str, Any]]
    ) -> tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """
        Decide whether candidates resolve to a single best match or remain ambiguous.

        Returns:
            (best_candidate, ambiguous_candidates)
        """
        if not candidates:
            return None, None

        # Sort by similarity descending.
        ordered = sorted(candidates, key=lambda c: float(c.get("similarity") or 0.0), reverse=True)
        best = ordered[0]
        if len(ordered) == 1:
            return best, None

        second = ordered[1]
        if (
            float(best.get("similarity") or 0.0) - float(second.get("similarity") or 0.0)
            >= cls.AMBIGUITY_MARGIN
        ):
            return best, None

        # Ambiguous: return a small candidate set.
        return None, ordered[:5]

    @classmethod
    def build_candidates_from_embeddings(
        cls,
        query_embedding: List[float],
        region_embeddings: List[Dict[str, Any]],
        *,
        limit: int = 5,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build region candidates from preloaded embeddings without DB access.

        region_embeddings expects entries with:
        - region_id, region_name, borough, embedding, norm
        """
        if not query_embedding or not region_embeddings:
            return []

        query_norm = math.sqrt(sum(x * x for x in query_embedding))
        if query_norm <= 0:
            return []

        min_similarity = float(threshold if threshold is not None else cls.SIMILARITY_THRESHOLD)

        candidates: List[Dict[str, Any]] = []
        for row in region_embeddings:
            embedding = row.get("embedding")
            norm = float(row.get("norm") or 0.0)
            if not embedding or norm <= 0:
                continue

            dot = 0.0
            for a, b in zip(query_embedding, embedding):
                dot += float(a) * float(b)

            cosine_sim = dot / (query_norm * norm) if (query_norm * norm) else 0.0
            similarity = (cosine_sim + 1.0) / 2.0
            if similarity < min_similarity:
                continue

            candidates.append(
                {
                    "region_id": str(row.get("region_id") or ""),
                    "region_name": str(row.get("region_name") or ""),
                    "borough": row.get("borough"),
                    "similarity": similarity,
                }
            )

        candidates.sort(key=lambda c: float(c.get("similarity") or 0.0), reverse=True)
        return candidates[:limit]

    async def embed_location_text(self, query: str) -> Optional[List[float]]:
        """Embed a location query string using the configured OpenAI embedding model."""
        config = get_search_config()
        model = config.embedding_model

        try:
            embed_text = f"{query}, NYC location"
            response = await self.client.embeddings.create(
                model=model,
                input=embed_text,
                dimensions=1536,
            )
            return list(response.data[0].embedding)
        except Exception as exc:
            logger.debug("Location embedding failed for '%s': %s", query, str(exc))
            return None

    async def _embed_location_text(self, query: str) -> Optional[List[float]]:
        """Embed a location query string using the configured OpenAI embedding model."""
        return await self.embed_location_text(query)
