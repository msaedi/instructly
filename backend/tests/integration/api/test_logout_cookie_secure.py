from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.utils.cookies import session_cookie_base_name

CSRF_COOKIE = "csrftoken"
CSRF_HEADER = "X-CSRFToken"
CSRF_ORIGIN = "https://preview.instainstru.com"


def _set_cookie_headers(response) -> list[str]:
    headers = response.headers
    get_list = getattr(headers, "get_list", None)
    if callable(get_list):
        return get_list("set-cookie")
    value = headers.get("set-cookie")
    return [value] if value else []


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = "testtoken"
    client.cookies.set(CSRF_COOKIE, token)
    return {
        CSRF_HEADER: token,
        "Origin": CSRF_ORIGIN,
        "Referer": f"{CSRF_ORIGIN}/",
    }


def test_logout_clears_host_cookie_secure(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("SITE_MODE", "preview")

    response = client.post("/api/v1/public/logout", headers=_csrf_headers(client))
    assert response.status_code == 204

    set_cookie_headers = _set_cookie_headers(response)
    target_cookie = session_cookie_base_name("preview")
    host_cookie_headers = [header for header in set_cookie_headers if f"{target_cookie}=" in header]
    assert host_cookie_headers, f"expected {target_cookie} cookie deletion"
    for header in host_cookie_headers:
        assert "Path=/" in header
        if settings.session_cookie_secure:
            assert "Secure" in header
        else:
            assert "Secure" not in header
        assert "Max-Age=0" in header

    auth_me = client.get("/api/v1/auth/me")
    assert auth_me.status_code == 401
