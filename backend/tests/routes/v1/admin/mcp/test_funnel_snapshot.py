from fastapi.testclient import TestClient


def test_funnel_snapshot_returns_structure(
    client: TestClient, test_student, mcp_service_headers
):
    res = client.get(
        "/api/v1/admin/mcp/funnel/snapshot",
        headers=mcp_service_headers,
    )
    assert res.status_code == 200

    data = res.json()
    assert "current_period" in data
    assert "stages" in data["current_period"]
    assert "overall_conversion" in data["current_period"]
    assert "insights" in data


def test_funnel_snapshot_with_comparison(client: TestClient, mcp_service_headers):
    res = client.get(
        "/api/v1/admin/mcp/funnel/snapshot",
        headers=mcp_service_headers,
        params={"compare_to": "previous_period"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["comparison_period"] is not None
    assert data["deltas"] is not None


def test_funnel_snapshot_requires_authentication(client: TestClient):
    res = client.get("/api/v1/admin/mcp/funnel/snapshot")
    assert res.status_code == 401
