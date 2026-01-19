"""Repository for region boundaries with helper to insert WKT polygons.

This encapsulates the small amount of raw SQL needed for geometry inserts
without introducing a GeoAlchemy dependency in the app layer.
"""

import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, cast

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class RegionBoundaryRepository:
    def __init__(self, db: Session):
        self.db = db

    def insert_wkt(
        self,
        region_id: str,
        region_type: str,
        region_code: str,
        region_name: str,
        parent_region: str,
        wkt_polygon: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Detect which metadata column exists: prefer region_metadata; fallback to metadata; or none
        cols = self.db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'region_boundaries'
                """
            )
        ).fetchall()
        colnames = {row[0] for row in cols}
        meta_column = (
            "region_metadata"
            if "region_metadata" in colnames
            else ("metadata" if "metadata" in colnames else None)
        )

        json_meta = json.dumps(metadata or {})

        if meta_column == "region_metadata":
            # Explicit branch to avoid dynamic column injection; satisfies Bandit B608
            sql = (
                "\n                INSERT INTO region_boundaries\n"
                "                    (id, region_type, region_code, region_name, parent_region, boundary, region_metadata, created_at, updated_at)\n"
                "                VALUES\n"
                "                    (:id, :type, :code, :name, :parent, ST_Multi(ST_GeomFromText(:wkt, 4326)), CAST(:meta AS JSONB), NOW(), NOW())\n"
                "                ON CONFLICT (id) DO NOTHING\n                "
            )
            params: Dict[str, Any] = {
                "id": region_id,
                "type": region_type,
                "code": region_code,
                "name": region_name,
                "parent": parent_region,
                "wkt": wkt_polygon,
                "meta": json_meta,
            }
        elif meta_column == "metadata":
            # Explicit branch to avoid dynamic column injection; satisfies Bandit B608
            sql = (
                "\n                INSERT INTO region_boundaries\n"
                "                    (id, region_type, region_code, region_name, parent_region, boundary, metadata, created_at, updated_at)\n"
                "                VALUES\n"
                "                    (:id, :type, :code, :name, :parent, ST_Multi(ST_GeomFromText(:wkt, 4326)), CAST(:meta AS JSONB), NOW(), NOW())\n"
                "                ON CONFLICT (id) DO NOTHING\n                "
            )
            params = {
                "id": region_id,
                "type": region_type,
                "code": region_code,
                "name": region_name,
                "parent": parent_region,
                "wkt": wkt_polygon,
                "meta": json_meta,
            }
        else:
            sql = """
                INSERT INTO region_boundaries
                    (id, region_type, region_code, region_name, parent_region, boundary, created_at, updated_at)
                VALUES
                    (:id, :type, :code, :name, :parent, ST_Multi(ST_GeomFromText(:wkt, 4326)), NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """
            params = {
                "id": region_id,
                "type": region_type,
                "code": region_code,
                "name": region_name,
                "parent": parent_region,
                "wkt": wkt_polygon,
            }

        self.db.execute(text(sql), params)
        self.db.flush()

    # --- Query helpers (repository pattern) ---

    def has_postgis(self) -> bool:
        try:
            res = self.db.execute(
                text(
                    "SELECT 1 FROM pg_available_extensions WHERE name='postgis' AND installed_version IS NOT NULL"
                )
            ).first()
            return res is not None
        except Exception:
            return False

    def table_has_boundary(self) -> bool:
        try:
            res = self.db.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'region_boundaries' AND column_name = 'boundary'
                    """
                )
            ).first()
            return res is not None
        except Exception:
            return False

    def find_region_by_point(
        self, lat: float, lng: float, region_type: str
    ) -> Optional[Mapping[str, Any]]:
        """Return the first region row whose boundary intersects the given point.

        Returns a mapping with keys: region_type, region_code, region_name, parent_region, region_metadata
        or None if not found/available.
        """
        try:
            sql = text(
                """
                SELECT region_type, region_code, region_name, parent_region, region_metadata
                FROM region_boundaries
                WHERE boundary IS NOT NULL
                  AND ST_Intersects(boundary, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326))
                  AND region_type = :rtype
                ORDER BY ST_Area(boundary) ASC NULLS LAST
                LIMIT 1
                """
            )
            return cast(
                Optional[Mapping[str, Any]],
                self.db.execute(sql, {"lat": lat, "lng": lng, "rtype": region_type})
                .mappings()
                .first(),
            )
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return None

    # --- Listing and GeoJSON helpers ---

    def list_regions(
        self,
        region_type: str,
        parent_region: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Mapping[str, Any]]:
        """List regions of a given type, optionally filtered by parent (e.g., borough).

        Returns mappings with: id, region_type, region_code, region_name, parent_region
        """
        try:
            base_sql = (
                "SELECT id, region_type, region_code, region_name, parent_region FROM region_boundaries "
                "WHERE region_type = :rtype"
            )
            params: Dict[str, Any] = {"rtype": region_type, "limit": limit, "offset": offset}
            if parent_region:
                base_sql += " AND parent_region = :parent"
                params["parent"] = parent_region
            base_sql += " ORDER BY parent_region, region_name LIMIT :limit OFFSET :offset"
            return cast(
                List[Mapping[str, Any]],
                self.db.execute(text(base_sql), params).mappings().all(),
            )
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return []

    def get_simplified_geojson_by_ids(
        self, ids: Sequence[str], tolerance: float = 0.0008
    ) -> List[Dict[str, Any]]:
        """Return list of mappings with id, region_name, parent_region, region_type, geometry (parsed GeoJSON)."""
        if not ids:
            return []
        try:
            rows = cast(
                List[Mapping[str, Any]],
                self.db.execute(
                    text(
                        """
                    SELECT id, region_name, parent_region, region_type,
                           ST_AsGeoJSON(ST_Simplify(boundary, :tol)) AS geojson
                    FROM region_boundaries
                    WHERE id = ANY(:ids)
                    """
                    ),
                    {"ids": ids, "tol": tolerance},
                )
                .mappings()
                .all(),
            )
            import json as _json

            results: List[Dict[str, Any]] = []
            for row in rows:
                results.append(
                    {
                        "id": row["id"],
                        "region_name": row["region_name"],
                        "parent_region": row["parent_region"],
                        "region_type": row["region_type"],
                        "geometry": (row["geojson"] and _json.loads(row["geojson"])) or None,
                    }
                )
            return results
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return []

    def find_region_ids_by_partial_names(
        self, names: list[str], region_type: str = "nyc"
    ) -> dict[str, str]:
        """Return a mapping from partial name to region id by simple ILIKE match (first result)."""
        if not names:
            return {}
        result: dict[str, str] = {}
        for n in names:
            try:
                row = self.db.execute(
                    text(
                        """
                        SELECT id
                        FROM region_boundaries
                        WHERE region_type = :rtype AND region_name ILIKE :n
                        ORDER BY region_name
                        LIMIT 1
                        """
                    ),
                    {"rtype": region_type, "n": f"%{n}%"},
                ).first()
                if row and row[0]:
                    result[n] = row[0]
            except Exception:
                try:
                    self.db.rollback()
                except Exception:
                    logger.debug("Non-fatal error ignored", exc_info=True)
        return result

    # --- Maintenance helpers (used by tests and admin flows) ---
    def delete_by_region_name(self, region_name: str, region_type: str | None = None) -> int:
        try:
            if region_type:
                sql = text(
                    """
                    DELETE FROM region_boundaries
                    WHERE region_name = :rname AND region_type = :rtype
                    """
                )
                res = self.db.execute(sql, {"rname": region_name, "rtype": region_type})
            else:
                sql = text(
                    """
                    DELETE FROM region_boundaries
                    WHERE region_name = :rname
                    """
                )
                res = self.db.execute(sql, {"rname": region_name})
            self.db.flush()
            return getattr(res, "rowcount", 0) or 0
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return 0

    def delete_by_region_code(self, region_code: str, region_type: str | None = None) -> int:
        try:
            if region_type:
                sql = text(
                    """
                    DELETE FROM region_boundaries
                    WHERE region_code = :rcode AND region_type = :rtype
                    """
                )
                res = self.db.execute(sql, {"rcode": region_code, "rtype": region_type})
            else:
                sql = text(
                    """
                    DELETE FROM region_boundaries
                    WHERE region_code = :rcode
                    """
                )
                res = self.db.execute(sql, {"rcode": region_code})
            self.db.flush()
            return getattr(res, "rowcount", 0) or 0
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                logger.debug("Non-fatal error ignored", exc_info=True)
            return 0
