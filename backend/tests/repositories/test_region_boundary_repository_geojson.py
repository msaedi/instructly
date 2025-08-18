from typing import List

import pytest

from app.core.ulid_helper import generate_ulid
from app.repositories.region_boundary_repository import RegionBoundaryRepository


def _square_wkt(lng_min: float, lat_min: float, lng_max: float, lat_max: float) -> str:
    return f"POLYGON(({lng_min} {lat_min},{lng_max} {lat_min},{lng_max} {lat_max},{lng_min} {lat_max},{lng_min} {lat_min}))"


def test_get_simplified_geojson_by_ids_returns_geometry(db):
    repo = RegionBoundaryRepository(db)

    # Ensure PostGIS boundary column exists; otherwise skip
    if not repo.table_has_boundary():
        pytest.skip("Boundary column not present; PostGIS likely unavailable in test DB")

    # Insert a tiny square region with a valid 26-char ULID (far from Times Square to avoid test collisions)
    region_id = generate_ulid()
    wkt = _square_wkt(-73.9000, 40.7000, -73.8900, 40.7100)
    repo.insert_wkt(
        region_id=region_id,
        region_type="nyc_test",
        region_code="TST",
        region_name="Test Region A",
        parent_region="Queens",
        wkt_polygon=wkt,
        metadata={"source": "unit_test"},
    )
    db.commit()

    rows: List[dict] = repo.get_simplified_geojson_by_ids([region_id], tolerance=0.0001)

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == region_id
    assert row["region_name"] == "Test Region A"
    assert row["parent_region"] == "Manhattan"
    assert row["region_type"] == "nyc"
    assert row["geometry"] is not None
    assert isinstance(row["geometry"], dict)
    assert row["geometry"].get("type") in {"Polygon", "MultiPolygon"}
    assert row["geometry"].get("coordinates")
