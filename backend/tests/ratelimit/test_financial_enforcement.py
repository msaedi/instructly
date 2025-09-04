from fastapi.testclient import TestClient

from app.main import fastapi_app


def test_financial_route_shadow_no_500(monkeypatch):
    client = TestClient(fastapi_app)

    # Use a POST on a financial route that has dependency; we expect 401/403 but must not 500
    r = client.post("/api/payments/connect/onboard")
    assert r.status_code in (200, 401, 403)
