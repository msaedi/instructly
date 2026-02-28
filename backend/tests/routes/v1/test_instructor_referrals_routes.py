"""Tests for instructor referral API endpoints."""

from app.core.config import settings


def test_get_referral_stats_returns_stats(client, auth_headers_instructor):
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


def test_get_referral_stats_creates_code(client, auth_headers_instructor):
    response = client.get(
        "/api/v1/instructor-referrals/stats",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["referral_code"]
    assert "/r/" in data["referral_link"]
    frontend_is_localhost = settings.frontend_url.startswith("http://localhost") or settings.frontend_url.startswith("https://localhost")
    expected_base = (
        settings.local_beta_frontend_origin
        if settings.local_beta_frontend_origin
        and (settings.site_mode == "local" or (settings.site_mode != "prod" and frontend_is_localhost))
        else settings.frontend_url
    )
    if expected_base:
        assert expected_base.rstrip("/") in data["referral_link"]


def test_get_referral_stats_requires_instructor(client, auth_headers_student):
    response = client.get(
        "/api/v1/instructor-referrals/stats",
        headers=auth_headers_student,
    )
    assert response.status_code == 403


def test_get_referral_stats_requires_authentication(client):
    response = client.get("/api/v1/instructor-referrals/stats")
    assert response.status_code in (401, 403)


def test_get_referred_instructors_returns_empty_list(client, auth_headers_instructor):
    response = client.get(
        "/api/v1/instructor-referrals/referred",
        headers=auth_headers_instructor,
    )

    assert response.status_code == 200
    data = response.json()
    assert "instructors" in data
    assert "total_count" in data
    assert isinstance(data["instructors"], list)


def test_get_referred_instructors_requires_instructor(client, auth_headers_student):
    response = client.get(
        "/api/v1/instructor-referrals/referred",
        headers=auth_headers_student,
    )
    assert response.status_code == 403


def test_get_popup_data_returns_payload(client, auth_headers_instructor):
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


def test_get_popup_data_requires_instructor(client, auth_headers_student):
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
