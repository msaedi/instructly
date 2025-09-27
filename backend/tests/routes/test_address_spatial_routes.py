

def test_neighborhoods_list_route(db, client):
    r = client.get("/api/addresses/regions/neighborhoods", params={"page": 1, "per_page": 1})
    assert r.status_code == 200
    data = r.json()
    assert set(["items", "total", "page", "per_page"]).issubset(data.keys())
    assert isinstance(data["items"], list)


def test_bulk_coverage_route_empty_ids(db, client):
    r = client.get("/api/addresses/coverage/bulk", params={"ids": ""})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []
