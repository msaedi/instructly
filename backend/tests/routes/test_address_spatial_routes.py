
def test_neighborhood_selector_route(db, client):
    r = client.get("/api/v1/addresses/neighborhoods/selector", params={"market": "nyc"})
    assert r.status_code == 200
    data = r.json()
    assert set(["market", "boroughs", "total_items"]).issubset(data.keys())
    assert data["market"] == "nyc"
    assert isinstance(data["boroughs"], list)


def test_bulk_coverage_route_empty_ids(db, client):
    r = client.get("/api/v1/addresses/coverage/bulk", params={"ids": ""})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []
