from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.dependencies.auth import get_current_active_user, get_current_user
from app.auth import get_password_hash
from app.core.enums import RoleName
from app.models.instructor import InstructorProfile
from app.models.rbac import Role
from app.models.user import User
from app.services.permission_service import PermissionService
from app.services.stripe_service import StripeService

CSRF_COOKIE = "csrftoken"
CSRF_HEADER = "X-CSRFToken"
CSRF_ORIGIN = "https://preview.instainstru.com"


def _csrf_headers(client):
    token = "testtoken"
    client.cookies.set(CSRF_COOKIE, token)
    return {
        CSRF_HEADER: token,
        "Origin": CSRF_ORIGIN,
        "Referer": f"{CSRF_ORIGIN}/dashboard",
        "Content-Type": "application/json",
    }


def _ensure_role(db, role_name: RoleName) -> Role:
    role = db.query(Role).filter_by(name=role_name).first()
    if role:
        return role
    role = Role(name=role_name, description=f"Auto-created role {role_name}")
    db.add(role)
    db.flush()
    return role


def _create_instructor(db, *, bgc_status: str) -> tuple[User, InstructorProfile]:
    _ensure_role(db, RoleName.INSTRUCTOR)
    user = User(
        email=f"go-live-{bgc_status}@example.com",
        hashed_password=get_password_hash("Passw0rd!"),
        first_name="Go",
        last_name="Live",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()

    PermissionService(db).assign_role(user.id, RoleName.INSTRUCTOR)

    profile = InstructorProfile(
        user_id=user.id,
        bio="Ready to teach",
        years_experience=3,
        min_advance_booking_hours=2,
        buffer_time_minutes=15,
        skills_configured=True,
        identity_verified_at=datetime.now(timezone.utc),
        bgc_status=bgc_status,
    )
    db.add(profile)
    db.flush()
    db.commit()
    db.refresh(user)
    db.refresh(profile)
    return user, profile


@pytest.fixture(autouse=True)
def stripe_check_completed(monkeypatch):
    def _complete(self, profile_id: str):  # noqa: ANN001
        return {"has_account": True, "onboarding_completed": True}

    monkeypatch.setattr(StripeService, "check_account_status", _complete)


def test_go_live_blocked_when_bgc_not_passed(client, db):
    user, _ = _create_instructor(db, bgc_status="review")
    app = client.app
    try:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

        headers = _csrf_headers(client)
        response = client.post("/api/v1/instructors/me/go-live", headers=headers, json={})
        assert response.status_code == 400
        payload = response.json()
        missing = []
        if isinstance(payload, dict):
            missing = payload.get("missing", [])
            if not missing:
                missing = payload.get("errors", {}).get("missing", [])
        assert "background_check" in missing
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_active_user, None)


def test_go_live_succeeds_with_passed_bgc(client, db):
    user, profile = _create_instructor(db, bgc_status="passed")
    profile.bgc_completed_at = datetime.now(timezone.utc)
    db.add(profile)
    db.commit()
    app = client.app
    try:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

        headers = _csrf_headers(client)
        response = client.post("/api/v1/instructors/me/go-live", headers=headers, json={})
        assert response.status_code == 200
        payload = response.json()
        assert payload["is_live"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_active_user, None)
