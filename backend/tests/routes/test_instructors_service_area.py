from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.core.ulid_helper import generate_ulid
from tests.conftest import _ensure_region_boundary, add_service_area


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


def test_check_service_area_returns_true(client, db, test_instructor) -> None:
    region = _ensure_region_boundary(db, "Manhattan")
    add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    _set_region_geometry(db, region.id, lon=-73.985, lat=40.758)
    db.commit()

    response = client.get(
        f"/api/v1/instructors/{test_instructor.id}/check-service-area?lat=40.758&lng=-73.985"
    )

    assert response.status_code == 200
    assert response.json()["is_covered"] is True


def test_check_service_area_returns_false(client, db, test_instructor) -> None:
    region = _ensure_region_boundary(db, "Manhattan")
    add_service_area(db, user=test_instructor, neighborhood_id=region.id)
    _set_region_geometry(db, region.id, lon=-73.985, lat=40.758)
    db.commit()

    response = client.get(
        f"/api/v1/instructors/{test_instructor.id}/check-service-area?lat=40.8&lng=-73.94"
    )

    assert response.status_code == 200
    assert response.json()["is_covered"] is False


def test_check_service_area_returns_404_for_missing_instructor(client) -> None:
    missing_id = generate_ulid()
    response = client.get(
        f"/api/v1/instructors/{missing_id}/check-service-area?lat=40.7&lng=-73.9"
    )
    assert response.status_code == 404


def test_check_service_area_requires_lat_lng(client, test_instructor) -> None:
    response = client.get(f"/api/v1/instructors/{test_instructor.id}/check-service-area?lat=40.7")
    assert response.status_code == 422
