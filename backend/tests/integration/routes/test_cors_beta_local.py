from __future__ import annotations

import os

import pytest

from app.core.config import settings


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "http://beta-local.instainstru.com:3000",
    ],
)
@pytest.mark.parametrize(
    "cors_env",
    [None, "ALLOWED_ORIGINS", "CORS_ALLOW_ORIGINS", "CORS_ALLOWED_ORIGINS"],
)
def test_dev_beta_aliases_receive_cors_headers(client, db, test_password, origin, cors_env, monkeypatch):
    """Ensure local multi-origin frontends pass CORS reflection checks."""

    # Default SITE_MODE should be local, but ensure tests don't inherit preview/prod state.
    monkeypatch.delenv("SITE_MODE", raising=False)
    os.environ.setdefault("SITE_MODE", "local")

    # Ensure legacy env names are cleared before setting per-param values.
    for key in ("ALLOWED_ORIGINS", "CORS_ALLOW_ORIGINS", "CORS_ALLOWED_ORIGINS"):
        monkeypatch.delenv(key, raising=False)

    hosts_csv = "http://localhost:3000,http://beta-local.instainstru.com:3000"
    if cors_env:
        monkeypatch.setenv(cors_env, hosts_csv)

    # Seed a loginable user for credentialed POST checks.
    from app.auth import get_password_hash
    from app.models.user import User

    email = (
        "cors-test-"
        + origin.split("//")[-1].replace(":", "_").replace(".", "_")
        + (f"-{cors_env.lower()}" if cors_env else "-default")
        + "@example.com"
    )

    db.query(User).filter(User.email == email).delete()
    db.commit()

    user = User(
        email=email,
        first_name="Cors",
        last_name="Tester",
        phone="+12125550000",
        zip_code="10001",
        is_active=True,
        hashed_password=get_password_hash(test_password),
    )
    db.add(user)
    db.commit()

    # Preflight (OPTIONS) request should reflect the origin and allow credentials/methods.
    preflight = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == origin
    assert preflight.headers.get("access-control-allow-credentials") == "true"
    allow_methods = preflight.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods

    # Credentialed POST should also reflect the origin headers.
    response = client.post(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        content=f"username={email}&password={test_password}",
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"
    # Ensure session cookie is issued (proof credentials were accepted).
    assert f"{settings.session_cookie_name}=" in (response.headers.get("set-cookie") or "")

    # Sanity-check fallback GET continues to emit headers.
    health = client.get("/health", headers={"Origin": origin})
    assert health.status_code == 200
    assert health.headers.get("access-control-allow-origin") == origin
    assert health.headers.get("access-control-allow-credentials") == "true"
