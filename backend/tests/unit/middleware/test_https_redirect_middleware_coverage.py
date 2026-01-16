from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.https_redirect import HTTPSRedirectMiddleware, create_https_redirect_middleware


def test_https_redirect_excluded_path() -> None:
    app = FastAPI()
    app.add_middleware(HTTPSRedirectMiddleware, force_https=True, exclude_paths=["/health"])

    @app.get("/health")
    def _health():
        return {"ok": True}

    client = TestClient(app, base_url="http://testserver")
    response = client.get("/health", headers={"X-Forwarded-Proto": "http"})
    assert response.status_code == 200


def test_https_redirect_redirects_http() -> None:
    app = FastAPI()
    app.add_middleware(HTTPSRedirectMiddleware, force_https=True)

    @app.get("/data")
    def _data():
        return {"ok": True}

    client = TestClient(app)
    response = client.get(
        "/data",
        headers={"X-Forwarded-Proto": "http"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"].startswith("https://")


def test_https_redirect_adds_security_headers_for_https() -> None:
    app = FastAPI()
    app.add_middleware(HTTPSRedirectMiddleware, force_https=True)

    @app.get("/data")
    def _data():
        return {"ok": True}

    client = TestClient(app, base_url="https://testserver")
    response = client.get("/data")
    assert response.status_code == 200
    assert "Strict-Transport-Security" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src" in response.headers["Content-Security-Policy"]


def test_https_redirect_disabled_force_https() -> None:
    app = FastAPI()
    app.add_middleware(HTTPSRedirectMiddleware, force_https=False)

    @app.get("/data")
    def _data():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/data", headers={"X-Forwarded-Proto": "http"})
    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers


def test_https_redirect_factory_sets_flag() -> None:
    middleware_cls = create_https_redirect_middleware(force_https=False)
    app = FastAPI()
    app.add_middleware(middleware_cls)

    @app.get("/data")
    def _data():
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/data", headers={"X-Forwarded-Proto": "http"})
    assert response.status_code == 200
