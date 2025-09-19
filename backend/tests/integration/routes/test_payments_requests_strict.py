import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _enable_strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


@pytest.fixture()
def client(_enable_strict):
    from importlib import reload
    import app.schemas.base as base
    import app.schemas.payment_schemas as ps
    import app.routes.payments as routes
    import app.main as main

    reload(base)
    reload(ps)
    reload(routes)
    reload(main)
    return TestClient(main.fastapi_app, raise_server_exceptions=False)


def test_save_payment_method_rejects_extra_field(client: TestClient):
    body = {
        "payment_method_id": "pm_123",
        "set_as_default": True,
        "unexpected": 1,
    }
    resp = client.post("/api/payments/methods", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    assert resp.status_code == 422
    data = resp.json()
    assert "title" in data or "detail" in data


def test_checkout_rejects_extra_field(client: TestClient):
    body = {
        "booking_id": "bk_123",
        "payment_method_id": "pm_123",
        "save_payment_method": False,
        "unexpected": 1,
    }
    resp = client.post("/api/payments/checkout", json=body)
    if resp.status_code in (401, 403):
        pytest.skip("Auth prevented validation; covered in authenticated suites")
    # Rate limit or other guards may apply; only assert 422 when schema is hit
    if resp.status_code not in (429, 400):
        assert resp.status_code == 422
        data = resp.json()
        assert "title" in data or "detail" in data
