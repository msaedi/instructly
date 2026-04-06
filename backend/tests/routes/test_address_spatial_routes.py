
import pytest
from sqlalchemy import text

from app.core.ulid_helper import generate_ulid
from app.models.region_boundary import RegionBoundary


def _square_wkt(lng_min: float, lat_min: float, lng_max: float, lat_max: float) -> str:
    return (
        f"POLYGON(({lng_min} {lat_min},{lng_max} {lat_min},{lng_max} {lat_max},"
        f"{lng_min} {lat_max},{lng_min} {lat_min}))"
    )


def test_neighborhood_selector_route(db, client):
    r = client.get("/api/v1/addresses/neighborhoods/selector", params={"market": "nyc"})
    assert r.status_code == 200
    data = r.json()
    assert set(["market", "boroughs", "total_items"]).issubset(data.keys())
    assert data["market"] == "nyc"
    assert isinstance(data["boroughs"], list)
    assert r.headers["Cache-Control"] == "public, max-age=86400"


def test_neighborhood_polygons_route(db, client):
    r = client.get("/api/v1/addresses/neighborhoods/polygons", params={"market": "nyc"})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)
    if data["features"]:
        props = data["features"][0]["properties"]
        assert {"display_key", "display_name", "borough"}.issubset(props.keys())
    assert r.headers["Cache-Control"] == "public, max-age=86400"


def test_neighborhood_polygons_route_rejects_unsupported_market(db, client):
    r = client.get("/api/v1/addresses/neighborhoods/polygons", params={"market": "la"})
    assert r.status_code == 400


def test_neighborhood_lookup_route(db, client):
    try:
        db.execute(text("SELECT postgis_full_version();"))
    except Exception:
        pytest.skip("PostGIS not available in test database")

    boundary_id = generate_ulid()
    boundary = RegionBoundary(
        id=boundary_id,
        region_type="nyc",
        region_code=f"TST-{boundary_id[-6:]}",
        region_name="Lookup Test Raw",
        display_name="Lookup Test",
        display_key="nyc-manhattan-lookup-test",
        display_order=0,
        parent_region="Manhattan",
    )
    db.add(boundary)
    db.flush()

    lat_min = 40.7745
    lat_max = 40.7755
    lng_min = -73.9555
    lng_max = -73.9545
    lat = (lat_min + lat_max) / 2
    lng = (lng_min + lng_max) / 2
    wkt = _square_wkt(lng_min, lat_min, lng_max, lat_max)

    try:
        db.execute(
            text(
                """
                UPDATE region_boundaries
                SET boundary = ST_Multi(ST_GeomFromText(:wkt, 4326)),
                    centroid = ST_Centroid(ST_Multi(ST_GeomFromText(:wkt, 4326)))
                WHERE id = :id
                """
            ),
            {"id": boundary_id, "wkt": wkt},
        )
        db.commit()

        r = client.get(
            "/api/v1/addresses/neighborhoods/lookup",
            params={"market": "nyc", "lat": lat, "lng": lng},
        )
        assert r.status_code == 200
        assert r.json() == {
            "display_key": "nyc-manhattan-lookup-test",
            "display_name": "Lookup Test",
            "borough": "Manhattan",
        }
    finally:
        db.query(RegionBoundary).filter(RegionBoundary.id == boundary_id).delete(
            synchronize_session=False
        )
        db.commit()


def test_neighborhood_lookup_route_returns_null_for_no_match(db, client):
    r = client.get(
        "/api/v1/addresses/neighborhoods/lookup",
        params={"market": "nyc", "lat": 0.0, "lng": 0.0},
    )
    assert r.status_code == 200
    assert r.json() is None


def test_neighborhood_lookup_route_rejects_unsupported_market(db, client):
    r = client.get(
        "/api/v1/addresses/neighborhoods/lookup",
        params={"market": "la", "lat": 40.7750, "lng": -73.9550},
    )
    assert r.status_code == 400


def test_neighborhood_lookup_rejects_invalid_coordinates(db, client):
    response = client.get(
        "/api/v1/addresses/neighborhoods/lookup",
        params={"market": "nyc", "lat": 999, "lng": -73.99},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Invalid coordinates: lat must be -90..90, lng must be -180..180"
    )


def test_neighborhood_lookup_rejects_out_of_range_lng(db, client):
    response = client.get(
        "/api/v1/addresses/neighborhoods/lookup",
        params={"market": "nyc", "lat": 40.73, "lng": 999},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Invalid coordinates: lat must be -90..90, lng must be -180..180"
    )


def test_bulk_coverage_route_empty_ids(db, client):
    r = client.get("/api/v1/addresses/coverage/bulk", params={"ids": ""})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []
