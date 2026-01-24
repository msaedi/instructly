from fastapi.testclient import TestClient

METRICS = [
    "instructor.registered",
    "instructor.onboarding",
    "instructor.live",
    "instructor.paused",
    "founding.cap",
    "founding.used",
    "search.zero_result",
    "search.conversion",
    "booking.completed",
    "booking.cancelled",
    "booking.no_show",
]


def test_metric_definition_returns_data(client: TestClient, auth_headers_admin):
    res = client.get("/api/v1/admin/mcp/metrics/instructor.live", headers=auth_headers_admin)
    assert res.status_code == 200
    body = res.json()
    assert body["data"]["metric"] == "instructor.live"
    assert "definition" in body["data"]
    assert "requirements" in body["data"]


def test_metric_unknown_returns_404(client: TestClient, auth_headers_admin):
    res = client.get("/api/v1/admin/mcp/metrics/unknown.metric", headers=auth_headers_admin)
    assert res.status_code == 404


def test_all_metrics_have_structure(client: TestClient, auth_headers_admin):
    for metric in METRICS:
        res = client.get(f"/api/v1/admin/mcp/metrics/{metric}", headers=auth_headers_admin)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["metric"] == metric
        assert isinstance(data["requirements"], list)
        assert isinstance(data["source_fields"], list)
        assert isinstance(data["related_metrics"], list)


def test_metrics_permission_required(client: TestClient, auth_headers):
    res = client.get("/api/v1/admin/mcp/metrics/instructor.live", headers=auth_headers)
    assert res.status_code == 403
