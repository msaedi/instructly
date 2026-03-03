"""Tests for instructor referral API endpoints."""

from types import SimpleNamespace

import pytest

import app.routes.v1.instructor_referrals as instructor_referrals_routes


def test_get_referral_stats_returns_stats(client, auth_headers_instructor, test_instructor):
    response = client.get(
        "/api/v1/instructor-referrals/stats",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()

    assert "referral_code" in data
    assert "referral_link" in data
    assert "total_referred" in data
    assert "pending_payouts" in data
    assert "completed_payouts" in data
    assert "total_earned_cents" in data
    assert "is_founding_phase" in data
    assert "founding_spots_remaining" in data
    assert "current_bonus_cents" in data


@pytest.mark.parametrize(
    "site_mode,frontend_url,local_beta_origin,expected_base",
    [
        ("local", "http://localhost:3000", "http://beta-local.instainstru.com:3000", "http://beta-local.instainstru.com:3000"),
        ("local", "http://localhost:3000", "", "http://localhost:3000"),
        ("beta-local", "https://beta-local.instainstru.com:3000", "http://beta-local.instainstru.com:3000", "http://beta-local.instainstru.com:3000"),
        ("beta", "https://beta.instainstru.com", "http://beta-local.instainstru.com:3000", "https://beta.instainstru.com"),
        ("preview", "https://preview.instainstru.com", "http://beta-local.instainstru.com:3000", "https://preview.instainstru.com"),
        ("prod", "https://www.instainstru.com", "http://beta-local.instainstru.com:3000", "https://www.instainstru.com"),
    ],
)
def test_get_referral_stats_creates_code(
    monkeypatch,
    site_mode,
    frontend_url,
    local_beta_origin,
    expected_base,
):
    monkeypatch.setattr(
        instructor_referrals_routes,
        "settings",
        SimpleNamespace(
            site_mode=site_mode,
            frontend_url=frontend_url,
            local_beta_frontend_origin=local_beta_origin,
        ),
    )

    referral_link = instructor_referrals_routes._get_referral_link("ABCD1234")
    assert referral_link.startswith(f"{expected_base.rstrip('/')}/r/")


def _mock_request(
    *,
    origin: str | None = None,
    referer: str | None = None,
    host: str | None = None,
    scheme: str = "http",
) -> SimpleNamespace:
    headers = {}
    if origin is not None:
        headers["origin"] = origin
    if referer is not None:
        headers["referer"] = referer
    if host is not None:
        headers["host"] = host
    return SimpleNamespace(headers=headers, url=SimpleNamespace(scheme=scheme))


def test_referral_link_prefers_request_origin_in_local_mode(monkeypatch):
    monkeypatch.setattr(
        instructor_referrals_routes,
        "settings",
        SimpleNamespace(
            site_mode="local",
            frontend_url="https://beta.instainstru.com",
            local_beta_frontend_origin="http://beta-local.instainstru.com:3000",
        ),
    )
    request = _mock_request(origin="http://localhost:3000")

    referral_link = instructor_referrals_routes._get_referral_link(
        "ABCD1234",
        request=request,
    )
    assert referral_link.startswith("http://localhost:3000/r/")


def test_referral_link_uses_referer_when_origin_missing(monkeypatch):
    monkeypatch.setattr(
        instructor_referrals_routes,
        "settings",
        SimpleNamespace(
            site_mode="local",
            frontend_url="https://beta.instainstru.com",
            local_beta_frontend_origin="http://beta-local.instainstru.com:3000",
        ),
    )
    request = _mock_request(referer="http://localhost:3000/instructor/dashboard?panel=referrals")

    referral_link = instructor_referrals_routes._get_referral_link(
        "ABCD1234",
        request=request,
    )
    assert referral_link.startswith("http://localhost:3000/r/")


def test_referral_link_ignores_request_origin_outside_local_modes(monkeypatch):
    monkeypatch.setattr(
        instructor_referrals_routes,
        "settings",
        SimpleNamespace(
            site_mode="preview",
            frontend_url="https://preview.instainstru.com",
            local_beta_frontend_origin="http://beta-local.instainstru.com:3000",
        ),
    )
    request = _mock_request(origin="http://localhost:3000")

    referral_link = instructor_referrals_routes._get_referral_link(
        "ABCD1234",
        request=request,
    )
    assert referral_link.startswith("https://preview.instainstru.com/r/")


def test_get_referral_stats_requires_instructor(client, auth_headers_student, test_student):
    response = client.get(
        "/api/v1/instructor-referrals/stats",
        headers=auth_headers_student,
    )
    assert response.status_code == 403


def test_get_referral_stats_requires_authentication(client):
    response = client.get("/api/v1/instructor-referrals/stats")
    assert response.status_code in (401, 403)


def test_get_referred_instructors_returns_empty_list(client, auth_headers_instructor, test_instructor):
    response = client.get(
        "/api/v1/instructor-referrals/referred",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()
    assert "instructors" in data
    assert "total_count" in data
    assert isinstance(data["instructors"], list)


def test_get_referred_instructors_requires_instructor(client, auth_headers_student, test_student):
    response = client.get(
        "/api/v1/instructor-referrals/referred",
        headers=auth_headers_student,
    )
    assert response.status_code == 403


def test_get_popup_data_returns_payload(client, auth_headers_instructor, test_instructor):
    response = client.get(
        "/api/v1/instructor-referrals/popup-data",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()

    assert "is_founding_phase" in data
    assert "bonus_amount_cents" in data
    assert "founding_spots_remaining" in data
    assert "referral_code" in data
    assert "referral_link" in data


def test_get_popup_data_requires_instructor(client, auth_headers_student, test_student):
    response = client.get(
        "/api/v1/instructor-referrals/popup-data",
        headers=auth_headers_student,
    )
    assert response.status_code == 403


def test_get_founding_status_public(client):
    response = client.get("/api/v1/instructor-referrals/founding-status")

    assert response.status_code == 200
    data = response.json()
    assert "is_founding_phase" in data
    assert "total_founding_spots" in data
    assert "spots_filled" in data
    assert "spots_remaining" in data
    assert data["spots_remaining"] == data["total_founding_spots"] - data["spots_filled"]
    assert data["spots_remaining"] >= 0
