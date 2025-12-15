"""Repository for LocationAlias writes and admin queries."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.location_alias import NYC_CITY_ID, LocationAlias

logger = logging.getLogger(__name__)


class LocationAliasRepository:
    """Encapsulates DB writes for location_aliases."""

    def __init__(self, db: Session, *, city_id: str = NYC_CITY_ID) -> None:
        self.db = db
        self.city_id = city_id

    def add(self, alias: LocationAlias) -> bool:
        """Add a LocationAlias row (flushes; does not commit)."""
        try:
            self.db.add(alias)
            self.db.flush()
            return True
        except Exception as exc:
            logger.debug(
                "Failed to add location alias '%s': %s",
                getattr(alias, "alias_normalized", None),
                str(exc),
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def get_by_id(self, alias_id: str) -> Optional[LocationAlias]:
        """Fetch a LocationAlias row by primary key."""
        try:
            row = self.db.get(LocationAlias, alias_id)
            return row if isinstance(row, LocationAlias) else None
        except Exception as exc:
            logger.debug("Failed to fetch LocationAlias '%s': %s", alias_id, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def update_status(self, alias_id: str, status: str) -> bool:
        """Update alias.status (flushes; does not commit)."""
        alias = self.get_by_id(alias_id)
        if not alias:
            return False
        try:
            alias.status = status
            self.db.flush()
            return True
        except Exception as exc:
            logger.debug("Failed to update LocationAlias '%s' status: %s", alias_id, str(exc))
            try:
                self.db.rollback()
            except Exception:
                pass
            return False

    def list_by_source_and_status(
        self,
        *,
        source: str,
        status: str,
        limit: int = 500,
    ) -> list[LocationAlias]:
        """List aliases filtered by source and status (best-effort)."""
        try:
            rows = (
                self.db.query(LocationAlias)
                .filter(
                    LocationAlias.city_id == self.city_id,
                    LocationAlias.source == source,
                    LocationAlias.status == status,
                )
                .order_by(LocationAlias.created_at.desc())
                .limit(int(limit))
                .all()
            )
            return [a for a in rows if isinstance(a, LocationAlias)]
        except Exception as exc:
            logger.debug(
                "Failed to list LocationAlias rows for source=%s status=%s: %s",
                source,
                status,
                str(exc),
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            return []
