
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


def test_bulk_coverage_route_empty_ids(db, client):
    r = client.get("/api/v1/addresses/coverage/bulk", params={"ids": ""})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []
