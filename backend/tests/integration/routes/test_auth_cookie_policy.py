from __future__ import annotations

import pytest

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import RoleName
from app.models.user import User
from app.services.permission_service import PermissionService


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

    expected_cookie = (
        "sid_preview"
        if site_mode == "preview"
        else "sid_prod"
        if site_mode in {"prod", "production", "live"}
        else "access_token"
    )

    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie", "")
    assert expected_cookie in set_cookie


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
