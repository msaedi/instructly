"""Repository for SearchQuery lookups used by search analytics and learning."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.nl_search import SearchQuery

logger = logging.getLogger(__name__)


class SearchQueryRepository:
    """Encapsulates SearchQuery reads needed by other services."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_normalized_query(self, search_query_id: str) -> Optional[dict[str, Any]]:
        """Return SearchQuery.normalized_query as a dict (best-effort)."""
        try:
            row = self.db.get(SearchQuery, search_query_id)
            if not isinstance(row, SearchQuery):
                return None

            payload: Any = getattr(row, "normalized_query", None)

            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    return None

            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.debug(
                "Failed to load SearchQuery.normalized_query '%s': %s", search_query_id, str(exc)
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            return None
