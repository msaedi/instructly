from __future__ import annotations

from typing import List
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from app.core.ulid_helper import generate_ulid
from app.models.region_boundary import RegionBoundary
from app.repositories.region_boundary_repository import RegionBoundaryRepository


def _square_wkt(lng_min: float, lat_min: float, lng_max: float, lat_max: float) -> str:
    return (
        f"POLYGON(({lng_min} {lat_min},{lng_max} {lat_min},{lng_max} {lat_max},{lng_min} {lat_max},{lng_min} {lat_min}))"
    )


class TestRegionBoundaryRepositoryCoverage:
    def test_insert_and_query_helpers(self, db):
        repo = RegionBoundaryRepository(db)

        if not repo.table_has_boundary() or not repo.has_postgis():
            pytest.skip("PostGIS boundary column unavailable in test DB")

        region_id = generate_ulid()
        parent_region = f"Parent-{region_id[-6:]}"
        wkt = _square_wkt(-73.95, 40.70, -73.94, 40.71)
        region_name = f"Test Region {region_id[-6:]}"
        repo.insert_wkt(
            region_id=region_id,
            region_type="nyc",
            region_code=f"TST-{region_id[-6:]}",
            region_name=region_name,
            parent_region=parent_region,
            wkt_polygon=wkt,
            metadata={"source": "unit_test"},
        )
        db.execute(
            text(
                """
                UPDATE region_boundaries
                SET display_name = :display_name,
                    display_key = :display_key,
                    display_order = 0
                WHERE id = :id
                """
            ),
            {
                "id": region_id,
                "display_name": region_name,
                "display_key": f"nyc-{parent_region.lower()}-{region_id.lower()}",
            },
        )
        db.commit()

        found = repo.find_region_by_point(40.705, -73.945, "nyc")
        assert found is not None
        assert found.get("region_type") == "nyc"
        assert found.get("region_name")

        listed = repo.list_regions("nyc", parent_region=parent_region, limit=10)
        assert any(row.get("id") == region_id for row in listed)

        name_map = repo.find_region_ids_by_partial_names([region_name], region_type="nyc")
        assert name_map.get(region_name) == region_id

    def test_geojson_and_deletes(self, db):
        repo = RegionBoundaryRepository(db)

        if not repo.table_has_boundary() or not repo.has_postgis():
            pytest.skip("PostGIS boundary column unavailable in test DB")

        region_id = generate_ulid()
        region_code = f"DEL-{region_id[-6:]}"
        wkt = _square_wkt(-73.90, 40.72, -73.89, 40.73)
        repo.insert_wkt(
            region_id=region_id,
            region_type="nyc",
            region_code=region_code,
            region_name="Test Delete Region",
            parent_region="Queens",
            wkt_polygon=wkt,
            metadata={"source": "unit_test"},
        )
        db.commit()

        rows: List[dict] = repo.get_simplified_geojson_by_ids([region_id])
        assert rows
        assert rows[0]["id"] == region_id

        assert repo.get_simplified_geojson_by_ids([]) == []

        deleted = repo.delete_by_region_name("Test Delete Region", region_type="nyc")
        assert deleted >= 1

        # reinsert for delete_by_region_code
        repo.insert_wkt(
            region_id=generate_ulid(),
            region_type="nyc",
            region_code=region_code,
            region_name="Test Delete Region",
            parent_region="Queens",
            wkt_polygon=wkt,
            metadata=None,
        )
        db.commit()

        deleted_by_code = repo.delete_by_region_code(region_code, region_type="nyc")
        assert deleted_by_code >= 1

    def test_insert_wkt_branches(self):
        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        for cols in (
            [("region_metadata",)],
            [("metadata",)],
            [("other",)],
        ):
            mock_db = MagicMock()
            mock_db.execute.side_effect = [_Result(cols), MagicMock()]

            repo = RegionBoundaryRepository(mock_db)
            repo.insert_wkt(
                region_id="rid",
                region_type="nyc",
                region_code="code",
                region_name="name",
                parent_region="parent",
                wkt_polygon=_square_wkt(-73.95, 40.7, -73.94, 40.71),
                metadata={"source": "test"},
            )
            assert mock_db.execute.call_count == 2
            mock_db.flush.assert_called_once()

    def test_error_paths_return_defaults(self):
        mock_db = MagicMock()
        mock_db.execute.side_effect = RuntimeError("boom")
        mock_db.rollback = MagicMock()

        repo = RegionBoundaryRepository(mock_db)
        assert repo.has_postgis() is False
        assert repo.table_has_boundary() is False
        assert repo.find_region_by_point(40.0, -73.0, "nyc") is None
        assert repo.list_regions("nyc") == []
        assert repo.get_simplified_geojson_by_ids(["id"]) == []
        assert repo.find_region_ids_by_partial_names(["name"]) == {}
        assert repo.delete_by_region_name("name") == 0
        assert repo.delete_by_region_code("code") == 0
        assert repo.get_simplified_geojson_by_ids([]) == []
        assert repo.find_region_ids_by_partial_names([]) == {}

    def test_find_region_by_point_skips_dropped_polygons_and_uses_display_name(self, db):
        repo = RegionBoundaryRepository(db)

        if not repo.table_has_boundary() or not repo.has_postgis():
            pytest.skip("PostGIS boundary column unavailable in test DB")

        dropped_code = f"MN-CPK-{generate_ulid()[-6:]}"
        active_code = f"MN-UES-{generate_ulid()[-6:]}"
        dropped = RegionBoundary(
            id=generate_ulid(),
            region_type="nyc",
            region_code=dropped_code,
            region_name="Central Park",
            display_name=None,
            display_key=None,
            display_order=None,
            parent_region="Manhattan",
        )
        active = RegionBoundary(
            id=generate_ulid(),
            region_type="nyc",
            region_code=active_code,
            region_name="Upper East Side-Carnegie Hill",
            display_name="Upper East Side",
            display_key="nyc-manhattan-upper-east-side",
            display_order=0,
            parent_region="Manhattan",
        )
        db.add_all([dropped, active])
        db.flush()

        db.execute(
            text(
                """
                UPDATE region_boundaries
                SET boundary = ST_Multi(ST_GeomFromText(:wkt, 4326)),
                    centroid = ST_Centroid(ST_Multi(ST_GeomFromText(:wkt, 4326)))
                WHERE id = :id
                """
            ),
            {
                "id": dropped.id,
                "wkt": _square_wkt(-73.9685, 40.7800, -73.9620, 40.7850),
            },
        )
        db.execute(
            text(
                """
                UPDATE region_boundaries
                SET boundary = ST_Multi(ST_GeomFromText(:wkt, 4326)),
                    centroid = ST_Centroid(ST_Multi(ST_GeomFromText(:wkt, 4326)))
                WHERE id = :id
                """
            ),
            {
                "id": active.id,
                "wkt": _square_wkt(-73.9580, 40.7720, -73.9520, 40.7780),
            },
        )
        db.commit()

        assert repo.find_region_by_point(40.7825, -73.9650, "nyc") is None

        found = repo.find_region_by_point(40.7750, -73.9550, "nyc")
        assert found is not None
        assert found["region_name"] == "Upper East Side"
        assert found["display_key"] == "nyc-manhattan-upper-east-side"
