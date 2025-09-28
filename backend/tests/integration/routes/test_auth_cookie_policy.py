from __future__ import annotations

import pytest

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import RoleName
from app.models.user import User
from app.services.permission_service import PermissionService
from app.utils.cookies import session_cookie_candidates


@pytest.mark.parametrize(
    "site_mode",
    [None, "local", "preview", "prod"],
)
def test_login_cookie_name_matches_site_mode(client, db, test_password, monkeypatch, site_mode):
    monkeypatch.delenv("SITE_MODE", raising=False)
    if site_mode is not None:
        monkeypatch.setenv("SITE_MODE", site_mode)

    email = f"cookie-{(site_mode or 'default').lower()}@example.com"

    db.query(User).filter(User.email == email).delete()
    db.commit()

    user = User(
        email=email,
        first_name="Cookie",
        last_name="Probe",
        phone="+12125550000",
        zip_code="10001",
        hashed_password=get_password_hash(test_password),
        is_active=True,
    )
    db.add(user)
    db.commit()

    # Give admin role to avoid authorization issues later on
    PermissionService(db).assign_role(user.id, RoleName.ADMIN)

    response = client.post(
        "/auth/login",
        data={"username": email, "password": test_password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    expected_names = session_cookie_candidates(site_mode or "")
    assert response.status_code == 200

    set_cookies = response.headers.get_list("set-cookie")
    assert set_cookies, "login response must set at least one cookie"

    primary_cookie_name = expected_names[0]
    primary_header = next((c for c in set_cookies if c.startswith(f"{primary_cookie_name}=")), None)
    assert primary_header, f"expected session cookie {primary_cookie_name}"
    assert "HttpOnly" in primary_header
    assert "Path=/" in primary_header
    assert "Domain=" not in primary_header

    if primary_cookie_name.startswith("__Host-"):
        assert "Secure" in primary_header
    else:
        assert "Secure" not in primary_header

    if len(expected_names) > 1:
        legacy_cookie_name = expected_names[-1]
        legacy_header = next((c for c in set_cookies if c.startswith(f"{legacy_cookie_name}=")), None)
        assert legacy_header, f"expected legacy cookie {legacy_cookie_name} for migration"
        assert "Domain=.instainstru.com" in legacy_header
        assert "Max-Age=0" in legacy_header or "expires=" in legacy_header.lower()
        assert "Secure" in legacy_header


def test_preview_token_rejected_in_prod(client, db, test_password, monkeypatch):
    # Seed an admin user
    email = "preview-token-check@example.com"
    db.query(User).filter(User.email == email).delete()
    db.commit()

    user = User(
        email=email,
        first_name="Preview",
        last_name="Token",
        phone="+12125550000",
        zip_code="10001",
        hashed_password=get_password_hash(test_password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    PermissionService(db).assign_role(user.id, RoleName.ADMIN)

    # Issue token under preview SITE_MODE
    monkeypatch.setenv("SITE_MODE", "preview")
    preview_login = client.post(
        "/auth/login",
        data={"username": email, "password": test_password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert preview_login.status_code == 200
    token = preview_login.json()["access_token"]

    # Switch to prod and ensure the preview token is rejected (aud/iss mismatch)
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(settings, "is_testing", False, raising=False)
    client.cookies.clear()
    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 401
