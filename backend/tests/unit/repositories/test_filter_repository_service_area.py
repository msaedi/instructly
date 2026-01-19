from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from tests.conftest import _ensure_region_boundary, add_service_area

from app.repositories.filter_repository import FilterRepository


def _deactivate_service_areas(db, instructor_id: str) -> None:
    db.execute(
        text(
            """
            UPDATE instructor_service_areas
            SET is_active = false
            WHERE instructor_id = :instructor_id
            """
        ),
        {"instructor_id": instructor_id},
    )
    db.flush()


def _boundary_expects_multipolygon(db) -> bool:
    try:
        row = db.execute(
            text(
                """
                SELECT type
                FROM geometry_columns
                WHERE f_table_schema = 'public'
                  AND f_table_name = 'region_boundaries'
                  AND f_geometry_column = 'boundary'
                """
            )
        ).first()
        if row and row[0]:
            return "MULTIPOLYGON" in str(row[0]).upper()
    except Exception:
        pass

    try:
        row = db.execute(
            text(
                """
                SELECT postgis_typmod_type(a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = 'region_boundaries'
                  AND a.attname = 'boundary'
                """
            )
        ).first()
        if row and row[0]:
            return "MULTIPOLYGON" in str(row[0]).upper()
    except Exception:
        pass

    return False


def _set_region_geometry(db, region_id: str, lon: float, lat: float) -> None:
    if not db.bind or db.bind.dialect.name != "postgresql":
        pytest.skip("PostGIS required")

    geom = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - 0.01, lat - 0.01],
                [lon + 0.01, lat - 0.01],
                [lon + 0.01, lat + 0.01],
                [lon - 0.01, lat + 0.01],
                [lon - 0.01, lat - 0.01],
            ]
        ],
    }
    geom_expr = "ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)"
    if _boundary_expects_multipolygon(db):
        geom_expr = f"ST_Multi({geom_expr})"
    db.execute(
        text(
            f"""
            UPDATE region_boundaries
            SET boundary = {geom_expr},
                centroid = ST_Centroid({geom_expr})
            WHERE id = :id
            """
        ),
        {"geom": json.dumps(geom), "id": region_id},
    )
    db.flush()


def test_point_inside_polygon_returns_true(db, test_instructor) -> None:
    repo = FilterRepository(db)
    _deactivate_service_areas(db, test_instructor.id)
    region = _ensure_region_boundary(db, "Manhattan")
    add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    _set_region_geometry(db, region.id, lon=-73.985, lat=40.758)
    db.commit()

    assert repo.is_location_in_service_area(
        instructor_id=test_instructor.id,
        lat=40.758,
        lng=-73.985,
    )


def test_point_outside_polygon_returns_false(db, test_instructor) -> None:
    repo = FilterRepository(db)
    _deactivate_service_areas(db, test_instructor.id)
    region = _ensure_region_boundary(db, "Manhattan")
    add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    _set_region_geometry(db, region.id, lon=-73.985, lat=40.758)
    db.commit()

    assert not repo.is_location_in_service_area(
        instructor_id=test_instructor.id,
        lat=40.8,
        lng=-73.94,
    )


def test_point_on_boundary_returns_true(db, test_instructor) -> None:
    repo = FilterRepository(db)
    _deactivate_service_areas(db, test_instructor.id)
    region = _ensure_region_boundary(db, "Manhattan")
    add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    _set_region_geometry(db, region.id, lon=-73.985, lat=40.758)
    db.commit()

    assert repo.is_location_in_service_area(
        instructor_id=test_instructor.id,
        lat=40.768,
        lng=-73.985,
    )


def test_inactive_service_area_not_checked(db, test_instructor) -> None:
    repo = FilterRepository(db)
    _deactivate_service_areas(db, test_instructor.id)
    region = _ensure_region_boundary(db, "Manhattan")
    isa = add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    isa.is_active = False
    db.flush()
    _set_region_geometry(db, region.id, lon=-73.985, lat=40.758)
    db.commit()

    assert not repo.is_location_in_service_area(
        instructor_id=test_instructor.id,
        lat=40.758,
        lng=-73.985,
    )


def test_multiple_service_areas_any_match(db, test_instructor) -> None:
    repo = FilterRepository(db)
    _deactivate_service_areas(db, test_instructor.id)
    region_primary = _ensure_region_boundary(db, "Manhattan")
    region_secondary = _ensure_region_boundary(db, "Brooklyn")
    add_service_area(db, user=test_instructor, neighborhood_id=region_primary.id)
    add_service_area(db, user=test_instructor, neighborhood_id=region_secondary.id)
    _set_region_geometry(db, region_primary.id, lon=-73.985, lat=40.758)
    _set_region_geometry(db, region_secondary.id, lon=-73.95, lat=40.68)
    db.commit()

    assert repo.is_location_in_service_area(
        instructor_id=test_instructor.id,
        lat=40.758,
        lng=-73.985,
    )
