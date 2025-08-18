from typing import List

import pytest

from app.core.ulid_helper import generate_ulid
from app.repositories.address_repository import InstructorServiceAreaRepository
from app.repositories.region_boundary_repository import RegionBoundaryRepository
from app.services.address_service import AddressService


def _square_wkt(lng_min: float, lat_min: float, lng_max: float, lat_max: float) -> str:
    return f"POLYGON(({lng_min} {lat_min},{lng_max} {lat_min},{lng_max} {lat_max},{lng_min} {lat_max},{lng_min} {lat_min}))"


def test_list_neighborhoods_pagination_and_format(db):
    service = AddressService(db)
    repo = RegionBoundaryRepository(db)

    # Ensure we have at least a couple of regions
    if not repo.table_has_boundary():
        pytest.skip("Boundary column not present; PostGIS likely unavailable in test DB")

    # Seed two small regions if empty
    rows = service.list_neighborhoods(limit=2, offset=0)
    if len(rows) == 0:
        repo.insert_wkt(
            region_id="TESTREGION_NEI_01_123456789012",
            region_type="nyc",
            region_code="T01",
            region_name="UnitTest One",
            parent_region="Manhattan",
            wkt_polygon=_square_wkt(-73.99, 40.75, -73.98, 40.76),
            metadata={"seed": True},
        )
        repo.insert_wkt(
            region_id="TESTREGION_NEI_02_123456789012",
            region_type="nyc",
            region_code="T02",
            region_name="UnitTest Two",
            parent_region="Manhattan",
            wkt_polygon=_square_wkt(-73.98, 40.75, -73.97, 40.76),
            metadata={"seed": True},
        )
        db.commit()

    page1 = service.list_neighborhoods(region_type="nyc", borough=None, limit=1, offset=0)
    page2 = service.list_neighborhoods(region_type="nyc", borough=None, limit=1, offset=1)

    assert len(page1) == 1
    assert len(page2) == 1
    assert {"id", "name", "borough", "code"}.issubset(page1[0].keys())


def test_get_coverage_geojson_for_instructors_builds_featurecollection(db, test_instructor):
    service = AddressService(db)
    region_repo = RegionBoundaryRepository(db)
    area_repo = InstructorServiceAreaRepository(db)

    if not region_repo.table_has_boundary():
        pytest.skip("Boundary column not present; PostGIS likely unavailable in test DB")

    # Insert a region with valid 26-char ULID
    region_id = generate_ulid()
    region_repo.insert_wkt(
        region_id=region_id,
        region_type="nyc",
        region_code="C01",
        region_name="Coverage One",
        parent_region="Manhattan",
        wkt_polygon=_square_wkt(-73.987, 40.757, -73.985, 40.759),
        metadata={"seed": True},
    )
    db.commit()

    # Attach region to instructor via repo (repository pattern)
    area_repo.upsert_area(
        instructor_id=test_instructor.id,
        neighborhood_id=region_id,
        coverage_type="primary",
        max_distance_miles=2.0,
        is_active=True,
    )
    db.commit()

    geo = service.get_coverage_geojson_for_instructors([test_instructor.id])
    assert geo["type"] == "FeatureCollection"
    assert isinstance(geo["features"], list)
    assert len(geo["features"]) >= 1
    f = geo["features"][0]
    assert f["type"] == "Feature"
    assert f["geometry"] and isinstance(f["geometry"], dict)
    assert f["properties"]["region_id"] == region_id
    assert test_instructor.id in f["properties"]["instructors"]
