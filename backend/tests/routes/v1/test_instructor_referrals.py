"""Additional coverage for instructor referral routes and helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
import pytest

from app.constants.pricing_defaults import PRICING_DEFAULTS
from app.core.exceptions import ServiceException
from app.models.instructor import InstructorProfile
from app.models.referrals import ReferralAttribution, ReferralCode, ReferralCodeStatus
from app.repositories.instructor_profile_repository import InstructorProfileRepository
from app.repositories.user_repository import UserRepository
from app.routes.v1.instructor_referrals import (
    _determine_payout_status,
    _require_referral_code,
    _resolve_founding_info,
)
from app.services.config_service import ConfigService


def _create_user(db, email: str, first_name: str = "Test", last_name: str = "User"):
    repo = UserRepository(db)
    user = repo.create(
        email=email,
        hashed_password="hashed",
        first_name=first_name,
        last_name=last_name,
        zip_code="11215",
        is_active=True,
    )
    db.commit()
    return user


def _create_instructor_profile(db, user_id: str, *, is_live: bool = False) -> InstructorProfile:
    profile = InstructorProfile(user_id=user_id, is_live=is_live)
    db.add(profile)
    db.flush()
    return profile


@pytest.mark.parametrize(
    "is_live, first_lesson_completed_at, payout_status, expected",
    [
        (False, None, None, "pending_live"),
        (True, None, None, "pending_lesson"),
        (True, datetime.now(timezone.utc), "completed", "paid"),
        (True, datetime.now(timezone.utc), "failed", "failed"),
        (True, datetime.now(timezone.utc), "pending", "pending_transfer"),
    ],
)
def test_determine_payout_status_variants(
    is_live, first_lesson_completed_at, payout_status, expected
):
    assert (
        _determine_payout_status(
            is_live=is_live,
            first_lesson_completed_at=first_lesson_completed_at,
            payout_status=payout_status,
        )
        == expected
    )


def test_resolve_founding_info_invalid_cap_uses_default(db, monkeypatch):
    def _pricing(self):
        return ({"founding_instructor_cap": "not-a-number"}, None)

    def _count(self):
        return 5

    monkeypatch.setattr(ConfigService, "get_pricing_config", _pricing)
    monkeypatch.setattr(InstructorProfileRepository, "count_founding_instructors", _count)

    cap, count, is_founding = _resolve_founding_info(db)

    assert cap == int(PRICING_DEFAULTS["founding_instructor_cap"])
    assert count == 5
    assert is_founding is (count < cap)


@pytest.mark.anyio
async def test_require_referral_code_timeout_error():
    class StubService:
        def ensure_code_for_user(self, user_id: str):
            raise ServiceException("timeout", code="REFERRAL_CODE_ISSUANCE_TIMEOUT")

    with pytest.raises(HTTPException) as exc_info:
        await _require_referral_code(StubService(), "user-1")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.anyio
async def test_require_referral_code_other_service_error():
    class StubService:
        def ensure_code_for_user(self, user_id: str):
            raise ServiceException("boom", code="REFERRAL_GENERIC")

    with pytest.raises(HTTPException) as exc_info:
        await _require_referral_code(StubService(), "user-1")

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.anyio
async def test_require_referral_code_none_returns_503():
    class StubService:
        def ensure_code_for_user(self, user_id: str):
            return None

    with pytest.raises(HTTPException) as exc_info:
        await _require_referral_code(StubService(), "user-1")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail["code"] == "REFERRAL_CODES_DISABLED"


def test_get_referred_instructors_paginates_and_formats_last_initial(
    db, client, auth_headers_instructor, test_instructor
):
    referrer = test_instructor
    referred = _create_user(db, "referred_instructor@example.com", first_name="Ada", last_name="Lovelace")
    _create_instructor_profile(db, referred.id)

    code = ReferralCode(
        code="REF-CODE-1",
        referrer_user_id=referrer.id,
        status=ReferralCodeStatus.ACTIVE,
    )
    db.add(code)
    db.flush()

    attribution = ReferralAttribution(
        code_id=code.id,
        referred_user_id=referred.id,
        source="test",
        ts=datetime.now(timezone.utc),
    )
    db.add(attribution)
    db.commit()

    response = client.get(
        "/api/v1/instructor-referrals/referred",
        headers=auth_headers_instructor,
        params={"limit": 1, "offset": 0},
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["total_count"] == 1
    assert len(payload["instructors"]) == 1
    instructor = payload["instructors"][0]
    assert instructor["first_name"] == "Ada"
    assert instructor["last_initial"] == "L"
    assert instructor["payout_status"] in {"pending_live", "pending_lesson", "pending_transfer"}
