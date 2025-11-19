from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.user import User


def _login(client: TestClient, email: str, password: str) -> None:
    payload = {
        "email": email,
        "password": password,
        "guest_session_id": "guard-cookie",
    }
    resp = client.post("/auth/login-with-session", json=payload)
    assert resp.status_code == 200, resp.text


def test_cookie_allows_api_addresses(client: TestClient, test_student: User, test_password: str) -> None:
    _login(client, test_student.email, test_password)
    resp = client.get("/api/addresses/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body


def test_missing_cookie_returns_401(client: TestClient, test_student: User, test_password: str) -> None:
    _login(client, test_student.email, test_password)
    client.cookies.clear()
    resp = client.get("/api/addresses/me")
    assert resp.status_code == 401
