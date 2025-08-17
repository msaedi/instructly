"""Repository for region boundaries with helper to insert WKT polygons.

This encapsulates the small amount of raw SQL needed for geometry inserts
without introducing a GeoAlchemy dependency in the app layer.
"""

import json

from sqlalchemy import text
from sqlalchemy.orm import Session


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
        metadata: dict = None,
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
            "region_metadata" if "region_metadata" in colnames else ("metadata" if "metadata" in colnames else None)
        )

        json_meta = json.dumps(metadata or {})

        if meta_column == "region_metadata":
            # Explicit branch to avoid dynamic column injection; satisfies Bandit B608
            sql = (
                "\n                INSERT INTO region_boundaries\n"
                "                    (id, region_type, region_code, region_name, parent_region, boundary, region_metadata, created_at, updated_at)\n"
                "                VALUES\n"
                "                    (:id, :type, :code, :name, :parent, ST_GeomFromText(:wkt, 4326), CAST(:meta AS JSONB), NOW(), NOW())\n"
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
        elif meta_column == "metadata":
            # Explicit branch to avoid dynamic column injection; satisfies Bandit B608
            sql = (
                "\n                INSERT INTO region_boundaries\n"
                "                    (id, region_type, region_code, region_name, parent_region, boundary, metadata, created_at, updated_at)\n"
                "                VALUES\n"
                "                    (:id, :type, :code, :name, :parent, ST_GeomFromText(:wkt, 4326), CAST(:meta AS JSONB), NOW(), NOW())\n"
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
                    (:id, :type, :code, :name, :parent, ST_GeomFromText(:wkt, 4326), NOW(), NOW())
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
                text("SELECT 1 FROM pg_available_extensions WHERE name='postgis' AND installed_version IS NOT NULL")
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

    def find_region_by_point(self, lat: float, lng: float, region_type: str):
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
                LIMIT 1
                """
            )
            return self.db.execute(sql, {"lat": lat, "lng": lng, "rtype": region_type}).mappings().first()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return None
