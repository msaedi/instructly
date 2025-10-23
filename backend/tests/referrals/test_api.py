"""API tests for referral endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:  # pragma: no cover - pytest may run from backend/ directory
    from backend.tests.helpers.assertions import sort_by_dict_key
except ModuleNotFoundError:  # pragma: no cover
    from tests.helpers.assertions import sort_by_dict_key
from fastapi import status
import pytest

from app.api.dependencies.services import get_referral_checkout_service
from app.auth import create_access_token
from app.core.config import settings
from app.main import app as fastapi_app
from app.models.referrals import RewardStatus
from app.models.user import User
from app.repositories.referral_repository import (
    ReferralAttributionRepository,
    ReferralClickRepository,
    ReferralRewardRepository,
)
from app.repositories.user_repository import UserRepository
from app.routes.referrals import _normalize_referral_landing_url
from app.schemas.referrals import AdminReferralsHealthOut, CheckoutApplyRequest
from app.services.referral_checkout_service import ReferralCheckoutError
from app.services.referral_service import ReferralService
from app.services.wallet_service import WalletService


@pytest.fixture
def referral_service(db):
    return ReferralService(db)


def _create_user(db, email: str) -> Any:
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


def test_referral_redirect_records_click(db, client, referral_service):
    referrer = _create_user(db, "referrer_click@example.com")
    code = referral_service.issue_code(referrer_user_id=referrer.id)
    code.vanity_slug = "p-slope"
    db.commit()

    response = client.get(f"/r/{code.vanity_slug}", follow_redirects=False)

    assert response.status_code == status.HTTP_302_FOUND
    expected_url = _normalize_referral_landing_url(settings.frontend_referral_landing_url)
    assert response.headers["location"] == expected_url
    assert response.cookies.get("instainstru_ref") == code.code

    click_repo = ReferralClickRepository(db)
    assert click_repo.count_since(datetime.now(timezone.utc) - timedelta(minutes=5)) == 1


def test_referral_redirect_json_mode(db, client, referral_service):
    referrer = _create_user(db, "referrer_json@example.com")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    response = client.get(f"/r/{code.code}", headers={"accept": "application/json"}, follow_redirects=False)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["ok"] is True
    assert payload["code"] == code.code
    expected_url = _normalize_referral_landing_url(settings.frontend_referral_landing_url)
    assert payload["redirect"] == expected_url
    assert response.cookies.get("instainstru_ref") == code.code


def test_claim_anonymous_sets_cookie(db, client, referral_service):
    referrer = _create_user(db, "referrer_claim@example.com")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    response = client.post("/api/referrals/claim", json={"code": code.code})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"attributed": False, "reason": "anonymous"}
    assert response.cookies.get("instainstru_ref") == code.code


def test_claim_authenticated_user(db, client, referral_service):
    referrer = _create_user(db, "referrer_auth@example.com")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    user = _create_user(db, "student_claim@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/referrals/claim", json={"code": code.code}, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"attributed": True, "reason": None}

    attribution_repo = ReferralAttributionRepository(db)
    assert attribution_repo.exists_for_user(user.id)

    response_conflict = client.post("/api/referrals/claim", json={"code": code.code}, headers=headers)
    assert response_conflict.status_code == status.HTTP_409_CONFLICT
    assert response_conflict.json()["reason"] == "already_attributed"


def test_slug_redirects_to_referral_landing_html(db, client, referral_service, monkeypatch):
    referrer = _create_user(db, "referrer_html@example.com")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    monkeypatch.setattr(
        settings,
        "frontend_referral_landing_url",
        "https://preview.instainstru.com/referrals/",
    )

    response = client.get(f"/r/{code.code}", follow_redirects=False)

    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "https://preview.instainstru.com/referral"
    assert "instainstru_ref" in (response.headers.get("set-cookie") or "")


def test_slug_redirects_to_referral_landing_json(db, client, referral_service, monkeypatch):
    referrer = _create_user(db, "referrer_json_redirect@example.com")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    monkeypatch.setattr(
        settings,
        "frontend_referral_landing_url",
        "https://preview.instainstru.com/referrals",
    )

    response = client.get(
        f"/r/{code.code}",
        headers={"accept": "application/json"},
        follow_redirects=False,
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["redirect"] == "https://preview.instainstru.com/referral"
    assert payload["code"] == code.code
    assert "instainstru_ref" in (response.headers.get("set-cookie") or "")


def test_get_my_referral_ledger(db, client, referral_service):
    user = _create_user(db, "ledger_user@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    code = referral_service.ensure_code_for_user(user.id)

    reward_repo = ReferralRewardRepository(db)
    unlock_ts = datetime.now(timezone.utc) + timedelta(days=7)
    expire_ts = unlock_ts + timedelta(days=180)

    inviter_pending = _create_user(db, "inviter_pending@example.com")
    pending, _ = reward_repo.create_student_pair(
        student_user_id=user.id,
        inviter_user_id=inviter_pending.id,
        amount_cents=settings.referrals_student_amount_cents,
        unlock_ts=unlock_ts,
        expire_ts=expire_ts,
        rule_version_student="S1-ledger",
        rule_version_referrer="S2-ledger",
    )
    pending.status = RewardStatus.PENDING

    inviter_unlocked = _create_user(db, "inviter_unlocked@example.com")
    unlocked, _ = reward_repo.create_student_pair(
        student_user_id=user.id,
        inviter_user_id=inviter_unlocked.id,
        amount_cents=settings.referrals_student_amount_cents,
        unlock_ts=datetime.now(timezone.utc) - timedelta(days=1),
        expire_ts=expire_ts,
        rule_version_student="S1-unlocked",
        rule_version_referrer="S2-unlocked",
    )
    unlocked.status = RewardStatus.UNLOCKED

    inviter_redeemed = _create_user(db, "inviter_redeemed@example.com")
    redeemed, _ = reward_repo.create_student_pair(
        student_user_id=user.id,
        inviter_user_id=inviter_redeemed.id,
        amount_cents=settings.referrals_student_amount_cents,
        unlock_ts=datetime.now(timezone.utc) - timedelta(days=10),
        expire_ts=expire_ts,
        rule_version_student="S1-redeemed",
        rule_version_referrer="S2-redeemed",
    )
    redeemed.status = RewardStatus.REDEEMED
    db.commit()

    response = client.get("/api/referrals/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["code"] == code.code
    assert payload["share_url"].endswith((code.vanity_slug or code.code))
    assert len(payload["pending"]) == 1
    assert len(payload["unlocked"]) == 1
    assert len(payload["redeemed"]) == 1
    assert payload["expiry_notice_days"] == [14, 3]

    pending_payload = sort_by_dict_key(payload["pending"], "id")
    unlocked_payload = sort_by_dict_key(payload["unlocked"], "id")
    redeemed_payload = sort_by_dict_key(payload["redeemed"], "id")

    assert pending_payload[0]["id"] == str(pending.id)
    assert unlocked_payload[0]["id"] == str(unlocked.id)
    assert redeemed_payload[0]["id"] == str(redeemed.id)


def _stub_checkout_service(
    monkeypatch,
    *,
    wallet_service: WalletService | None = None,
    error: ReferralCheckoutError | None = None,
    app_instance=fastapi_app,
) -> None:
    class StubService:
        def __init__(self) -> None:
            self._wallet_service = wallet_service

        def apply_student_credit(self, *, user_id: str, order_id: str) -> int:
            if error:
                raise error
            if self._wallet_service is None:
                return settings.referrals_student_amount_cents

            txn = self._wallet_service.consume_student_credit(
                user_id=user_id,
                order_id=order_id,
                amount_cents=settings.referrals_student_amount_cents,
            )
            if not txn:
                raise ReferralCheckoutError("no_unlocked_credit")
            return txn.amount_cents

    monkeypatch.setitem(
        app_instance.dependency_overrides,
        get_referral_checkout_service,
        lambda: StubService(),
    )


def test_checkout_apply_success(db, client, referral_service, monkeypatch):
    user = _create_user(db, "checkout_success@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    reward_repo = ReferralRewardRepository(db)
    inviter = _create_user(db, "checkout_referrer@example.com")
    reward, _ = reward_repo.create_student_pair(
        student_user_id=user.id,
        inviter_user_id=inviter.id,
        amount_cents=settings.referrals_student_amount_cents,
        unlock_ts=datetime.now(timezone.utc) - timedelta(days=1),
        expire_ts=datetime.now(timezone.utc) + timedelta(days=180),
        rule_version_student="S1-checkout",
        rule_version_referrer="S2-checkout",
    )
    reward.status = RewardStatus.UNLOCKED
    db.flush()

    wallet_service = WalletService(db)
    _stub_checkout_service(monkeypatch, wallet_service=wallet_service, app_instance=client.app)

    response = client.post(
        "/api/referrals/checkout/apply-referral",
        json=CheckoutApplyRequest(order_id="order-1").model_dump(),
        headers=headers,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["applied_cents"] == settings.referrals_student_amount_cents

    db.refresh(reward)
    assert reward.status == RewardStatus.REDEEMED


def test_checkout_apply_conflicts(db, client, referral_service, monkeypatch):
    user = _create_user(db, "checkout_conflict@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    for reason in ("promo_conflict", "below_min_basket"):
        _stub_checkout_service(
            monkeypatch,
            error=ReferralCheckoutError(reason),
            app_instance=client.app,
        )

        response = client.post(
            "/api/referrals/checkout/apply-referral",
            json={"order_id": "order-err"},
            headers=headers,
        )
        assert response.status_code == status.HTTP_409_CONFLICT, response.text
        assert response.json()["reason"] == reason


def test_checkout_apply_no_credit(db, client, referral_service, monkeypatch):
    user = _create_user(db, "checkout_nocredit@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    wallet_service = WalletService(db)
    _stub_checkout_service(monkeypatch, wallet_service=wallet_service, app_instance=client.app)

    response = client.post(
        "/api/referrals/checkout/apply-referral",
        json={"order_id": "order-nocredit"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_409_CONFLICT, response.text
    assert response.json()["reason"] == "no_unlocked_credit"


def test_admin_referral_config(db, client, referral_service, monkeypatch):
    admin = _create_user(db, "admin_config@example.com")
    monkeypatch.setattr(User, "is_admin", property(lambda self: True))

    token = create_access_token(data={"sub": admin.email})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/admin/referrals/config", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert {
        "student_amount_cents",
        "instructor_amount_cents",
        "min_basket_cents",
        "hold_days",
        "expiry_months",
        "global_cap",
        "version",
        "source",
        "flags",
    } == set(payload.keys())
    assert isinstance(payload["flags"], dict)
    assert payload["flags"].get("enabled") == bool(settings.referrals_enabled)
    assert payload["source"] in {"defaults", "db"}
    if payload["source"] == "defaults":
        assert payload["version"] is None


def test_admin_referral_summary(db, client, referral_service, monkeypatch):
    admin = _create_user(db, "admin_summary@example.com")
    monkeypatch.setattr(User, "is_admin", property(lambda self: True))

    token = create_access_token(data={"sub": admin.email})
    headers = {"Authorization": f"Bearer {token}"}

    referrer = _create_user(db, "summary_referrer@example.com")
    referred = _create_user(db, "summary_referred@example.com")
    code = referral_service.ensure_code_for_user(referrer.id)

    reward_repo = ReferralRewardRepository(db)
    student_reward, inviter_reward = reward_repo.create_student_pair(
        student_user_id=referred.id,
        inviter_user_id=referrer.id,
        amount_cents=settings.referrals_student_amount_cents,
        unlock_ts=datetime.now(timezone.utc) - timedelta(days=2),
        expire_ts=datetime.now(timezone.utc) + timedelta(days=180),
        rule_version_student="S1-summary",
        rule_version_referrer="S2-summary",
    )
    student_reward.status = RewardStatus.UNLOCKED
    inviter_reward.status = RewardStatus.UNLOCKED
    db.commit()

    referral_service.record_click(
        code=code.code,
        device_fp_hash=None,
        ip_hash=None,
        ua_hash=None,
        channel="test",
        ts=datetime.now(timezone.utc),
    )
    referral_service.attribute_signup(
        referred_user_id=referred.id,
        code=code.code,
        source="admin_summary",
        ts=datetime.now(timezone.utc),
    )

    response = client.get("/api/admin/referrals/summary", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    summary = response.json()
    assert {
        "counts_by_status",
        "cap_utilization_percent",
        "top_referrers",
        "clicks_24h",
        "attributions_24h",
    } == set(summary.keys())
    counts = summary["counts_by_status"]
    for key in ("pending", "unlocked", "redeemed", "void"):
        assert key in counts
        assert isinstance(counts[key], int)
    assert isinstance(summary["cap_utilization_percent"], float)
    assert summary["clicks_24h"] >= 0
    assert summary["attributions_24h"] >= 0
    top_referrers = summary["top_referrers"]
    if top_referrers:
        entry = top_referrers[0]
        assert {"user_id", "count", "code"} <= set(entry.keys())


def test_admin_referral_health_endpoint(db, client, monkeypatch):
    admin = _create_user(db, "admin_health@example.com")
    monkeypatch.setattr(User, "is_admin", property(lambda self: True))

    token = create_access_token(data={"sub": admin.email})
    headers = {"Authorization": f"Bearer {token}"}

    health_payload = AdminReferralsHealthOut(
        workers_alive=1,
        workers=["celery@worker-1"],
        backlog_pending_due=2,
        pending_total=5,
        unlocked_total=3,
        void_total=1,
        last_run_age_s=120,
    )

    monkeypatch.setattr(ReferralService, "get_admin_health", lambda self: health_payload)

    response = client.get("/api/admin/referrals/health", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == health_payload.model_dump()
