"""Additional coverage for referral routes and helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException, Request, Response, status
import pytest

from app.core.exceptions import ServiceException
from app.models.referrals import ReferralClick
from app.repositories.referral_repository import ReferralClickRepository
from app.repositories.user_repository import UserRepository
from app.routes.v1.referrals import (
    _accepts_json,
    _hash_value,
    _normalize_referral_landing_url,
    resolve_referral_slug,
)
from app.services.referral_service import ReferralService


def _create_user(db, email: str):
    repo = UserRepository(db)
    user = repo.create(
        email=email,
        hashed_password="hashed",
        first_name="Test",
        last_name="User",
        zip_code="11215",
        is_active=True,
    )
    db.commit()
    return user


@pytest.mark.parametrize(
    "accept_header, expected",
    [
        (None, False),
        ("text/html,application/json", False),
        ("application/json,text/html", True),
        ("application/json", True),
    ],
)
def test_accepts_json_respects_header_precedence(accept_header, expected):
    assert _accepts_json(accept_header) is expected


@pytest.mark.parametrize(
    "raw_url, expected",
    [
        ("", "/referral"),
        ("https://example.com/referrals", "https://example.com/referral"),
        ("https://example.com/foo", "https://example.com/foo/referral"),
        ("referral", "/referral/referral"),
    ],
)
def test_normalize_referral_landing_url_variants(raw_url, expected):
    assert _normalize_referral_landing_url(raw_url) == expected


@pytest.mark.parametrize("code", ["INVALID", "bad-code", " "])
def test_claim_invalid_code_returns_not_found(client, code):
    response = client.post("/api/v1/referrals/claim", json={"code": code})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["reason"] == "not_found"


def test_resolve_slug_invalid_returns_html(client):
    response = client.get("/api/v1/r/does-not-exist", headers={"accept": "text/html"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Invalid referral link" in response.text


def test_resolve_slug_records_request_client_ip(db, client):
    referrer = _create_user(db, "referrer_ip@example.com")
    referral_service = ReferralService(db)
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    response = client.get(
        f"/api/v1/r/{code.code}",
        headers={"accept": "application/json", "x-forwarded-for": "203.0.113.9"},
        follow_redirects=False,
    )

    assert response.status_code == status.HTTP_200_OK

    click_repo = ReferralClickRepository(db)
    assert click_repo.count_since(datetime.now(timezone.utc) - timedelta(minutes=5)) == 1
    click = db.query(ReferralClick).first()
    assert click is not None
    assert click.ip_hash == _hash_value("203.0.113.9")


@pytest.mark.anyio
async def test_resolve_slug_uses_request_client_when_no_forwarded_for():
    recorded = {}

    class StubReferralService:
        def resolve_code(self, slug: str):
            return SimpleNamespace(code="CODE123")

        def record_click(self, **kwargs):
            recorded.update(kwargs)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/r/CODE123",
        "headers": [],
        "query_string": b"",
        "client": ("203.0.113.42", 1234),
        "server": ("testserver", 80),
    }
    request = Request(scope)
    response = Response()

    resolved = await resolve_referral_slug(
        "CODE123",
        request,
        response,
        referral_service=StubReferralService(),
    )

    assert resolved.status_code in {200, 302}
    assert recorded.get("ip_hash") == _hash_value("203.0.113.42")


def test_referral_ledger_service_exception_returns_500(
    client, auth_headers_student, monkeypatch
):
    def _raise(self, user_id: str):
        raise ServiceException("boom", code="REFERRAL_CODE_ERROR")

    monkeypatch.setattr(ReferralService, "ensure_code_for_user", _raise)

    response = client.get("/api/v1/referrals/me", headers=auth_headers_student)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["code"] == "REFERRAL_CODE_ERROR"


def test_referral_ledger_rewards_error_returns_500(
    db, client, auth_headers_student, test_student, monkeypatch
):
    referral_service = ReferralService(db)
    code = referral_service.issue_code(referrer_user_id=test_student.id)

    def _return_code(self, user_id: str):
        return code

    def _raise_rewards(self, *, user_id: str):
        raise ServiceException("rewards failed", code="REWARDS_DOWN")

    monkeypatch.setattr(ReferralService, "ensure_code_for_user", _return_code)
    monkeypatch.setattr(ReferralService, "get_rewards_by_status", _raise_rewards)

    response = client.get("/api/v1/referrals/me", headers=auth_headers_student)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["code"] == "REWARDS_DOWN"


def test_referral_ledger_adds_unexpected_header_on_503(client, auth_headers_student, monkeypatch):
    def _raise(self, user_id: str):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "oops"})

    monkeypatch.setattr(ReferralService, "ensure_code_for_user", _raise)

    response = client.get("/api/v1/referrals/me", headers=auth_headers_student)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers.get("X-Referrals-Reason") == "unexpected"


def test_admin_referral_endpoints_require_admin(client, auth_headers_student):
    for path in (
        "/api/v1/admin/referrals/config",
        "/api/v1/admin/referrals/summary",
        "/api/v1/admin/referrals/health",
    ):
        response = client.get(path, headers=auth_headers_student)
        assert response.status_code == status.HTTP_403_FORBIDDEN
