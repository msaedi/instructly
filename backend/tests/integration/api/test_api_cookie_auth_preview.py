from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.core.config import settings
from app.models.user import User
from app.services.stripe_service import StripeService


def _configure_preview_env(monkeypatch) -> None:
    monkeypatch.setenv("SITE_MODE", "preview", prepend=False)
    monkeypatch.setattr(settings, "session_cookie_name", "__Host-sid", raising=False)
    monkeypatch.setattr(settings, "session_cookie_secure", True, raising=False)
    monkeypatch.setattr(settings, "session_cookie_samesite", "lax", raising=False)
    monkeypatch.setattr(settings, "session_cookie_domain", None, raising=False)
    monkeypatch.setattr(settings, "preview_frontend_domain", "preview.instainstru.com", raising=False)


def _set_session_cookie(client: TestClient, user: User) -> str:
    token = create_access_token({"sub": user.email})
    client.cookies.set(settings.session_cookie_name, token)
    return token


def test_preview_session_cookie_powers_api_routes(
    client: TestClient,
    db: Session,
    test_student: User,
    test_instructor: User,
    monkeypatch,
):
    _configure_preview_env(monkeypatch)

    # Student-scoped endpoints
    client.cookies.clear()
    _set_session_cookie(client, test_student)

    addresses = client.get("/api/v1/addresses/me")
    assert addresses.status_code == 200

    referrals = client.get("/api/referrals/me")
    assert referrals.status_code == 200

    fake_created = datetime.now(timezone.utc)
    monkeypatch.setattr(
        StripeService,
        "get_user_payment_methods",
        lambda self, user_id: [
            SimpleNamespace(
                stripe_payment_method_id="pm_cookie",
                last4="4242",
                brand="visa",
                is_default=True,
                created_at=fake_created,
            )
        ],
    )
    payment_methods = client.get("/api/payments/methods")
    assert payment_methods.status_code == 200
    assert payment_methods.json()

    # Instructor-scoped endpoints
    client.cookies.clear()
    _set_session_cookie(client, test_instructor)
    start_date = "2024-01-01"

    week = client.get(f"/instructors/availability/week?start_date={start_date}")
    assert week.status_code == 200

    booked = client.get(f"/instructors/availability/week/booked-slots?start_date={start_date}")
    assert booked.status_code == 200

    payload = {
        "week_start": start_date,
        "clear_existing": True,
        "schedule": [
            {
                "date": start_date,
                "start_time": "09:00",
                "end_time": "10:00",
            }
        ],
    }
    csrf_headers = {
        "Origin": "https://preview.instainstru.com",
        "Referer": "https://preview.instainstru.com/instructors/dashboard",
    }
    save_resp = client.post(
        "/instructors/availability/week",
        json=payload,
        headers=csrf_headers,
    )
    assert save_resp.status_code == 200
