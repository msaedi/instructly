"""
Tier 4: Embedding-based location resolution.

This service:
- Embeds user location text (e.g., "museum mile") using OpenAI embeddings
- Finds nearest `region_boundaries` rows via pgvector similarity on `name_embedding`

Notes:
- Only runs when `region_boundaries.name_embedding` is populated (otherwise returns []).
- Designed to be called from background threads (FilterService uses `asyncio.to_thread`).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.services.search.config import get_search_config

logger = logging.getLogger(__name__)


class LocationEmbeddingService:
    """Embedding-based semantic matcher for location strings."""

    # Filter out low-confidence candidates (0..1 after normalization)
    SIMILARITY_THRESHOLD = 0.7
    # If the top candidate is only slightly better than the second, treat as ambiguous.
    AMBIGUITY_MARGIN = 0.1

    def __init__(self, repository: Any) -> None:
        self._repository = repository
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI()
        return self._client

    def get_candidates(
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
        if not self._repository.has_region_name_embeddings():
            return []

        if not os.getenv("OPENAI_API_KEY"):
            return []

        embedding = self._embed_location_text(normalized)
        if not embedding:
            return []

        pairs = self._repository.find_regions_by_name_embedding(embedding, limit=limit)
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

    def pick_best_or_ambiguous(
        self, candidates: List[Dict[str, Any]]
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
            >= self.AMBIGUITY_MARGIN
        ):
            return best, None

        # Ambiguous: return a small candidate set.
        return None, ordered[:5]

    def _embed_location_text(self, query: str) -> Optional[List[float]]:
        """Embed a location query string using the configured OpenAI embedding model."""
        config = get_search_config()
        model = config.embedding_model

        try:
            # Provide a small hint to steer embeddings toward place semantics.
            embed_text = f"{query}, NYC location"
            response = self.client.embeddings.create(
                model=model,
                input=embed_text,
                dimensions=1536,
            )
            return list(response.data[0].embedding)
        except Exception as exc:
            logger.debug("Location embedding failed for '%s': %s", query, str(exc))
            return None
