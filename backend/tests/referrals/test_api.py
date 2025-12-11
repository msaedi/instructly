"""API tests for referral endpoints."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import time
from typing import Any

try:  # pragma: no cover - pytest may run from backend/ directory
    from backend.tests.helpers.assertions import sort_by_dict_key
except ModuleNotFoundError:  # pragma: no cover
    from tests.helpers.assertions import sort_by_dict_key
from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.api.dependencies.database import get_db as deps_get_db
from app.api.dependencies.services import get_referral_checkout_service
from app.auth import create_access_token
from app.core.config import settings
from app.core.exceptions import ServiceException
from app.database import get_db
from app.main import fastapi_app
from app.models.referrals import RewardStatus
from app.models.user import User
from app.repositories.referral_repository import (
    ReferralAttributionRepository,
    ReferralClickRepository,
    ReferralRewardRepository,
)
from app.repositories.user_repository import UserRepository
from app.routes.v1.referrals import _normalize_referral_landing_url
from app.schemas.referrals import AdminReferralsHealthOut, CheckoutApplyRequest
from app.services.referral_checkout_service import ReferralCheckoutError
from app.services.referral_service import ReferralService
from app.services.wallet_service import WalletService

try:  # pragma: no cover - pytest may run from backend/ directory
    from backend.tests.conftest import TestSessionLocal
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import TestSessionLocal


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

    response = client.post("/api/v1/referrals/claim", json={"code": code.code})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"attributed": False, "reason": "anonymous"}
    assert response.cookies.get("instainstru_ref") == code.code


def test_claim_authenticated_user(db, client, referral_service):
    referrer = _create_user(db, "referrer_auth@example.com")
    code = referral_service.issue_code(referrer_user_id=referrer.id)

    user = _create_user(db, "student_claim@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/referrals/claim", json={"code": code.code}, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"attributed": True, "reason": None}

    attribution_repo = ReferralAttributionRepository(db)
    assert attribution_repo.exists_for_user(user.id)

    response_conflict = client.post("/api/v1/referrals/claim", json={"code": code.code}, headers=headers)
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


def test_get_my_referral_ledger(db, client, referral_service, monkeypatch):
    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "4")
    user = _create_user(db, "ledger_user@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    code = referral_service.ensure_code_for_user(user.id)
    assert code is not None

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

    response = client.get("/api/v1/referrals/me", headers=headers)
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


def test_referral_ledger_returns_code_when_step_enabled(db, client, monkeypatch):
    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "4")
    user = _create_user(db, "ledger_enabled@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/referrals/me", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["code"]


def test_referral_ledger_reads_existing_code_when_step_disabled(
    db, client, referral_service, monkeypatch
):
    user = _create_user(db, "ledger_existing@example.com")
    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "4")
    code = referral_service.ensure_code_for_user(user.id)
    assert code is not None

    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "1")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/referrals/me", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["code"] == code.code


def test_referral_ledger_returns_503_when_issuance_disabled(db, client, monkeypatch):
    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "1")
    user = _create_user(db, "ledger_disabled@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/referrals/me", headers=headers)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers["X-Referrals-Reason"] == "issuance_disabled(step=1)"
    payload = response.json()
    assert payload["code"] == "REFERRAL_CODES_DISABLED"


def test_referral_ledger_reports_db_timeout_reason(db, client, monkeypatch):
    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "4")
    user = _create_user(db, "ledger_timeout@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    def _raise_timeout(self, user_id: str):
        raise ServiceException(
            "Referral code issuance is temporarily unavailable",
            code="REFERRAL_CODE_ISSUANCE_TIMEOUT",
        )

    monkeypatch.setattr(ReferralService, "ensure_code_for_user", _raise_timeout)

    response = client.get("/api/v1/referrals/me", headers=headers)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert (
        response.headers["X-Referrals-Reason"] == "db_timeout(lock_timeout/statement_timeout)"
    )


def test_referral_ledger_concurrent_requests(db, monkeypatch):
    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "4")

    user = _create_user(db, "concurrent_user@example.com")
    token = create_access_token(data={"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    previous_overrides = dict(fastapi_app.dependency_overrides)

    def _override_get_db():
        session = TestSessionLocal()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    fastapi_app.dependency_overrides[deps_get_db] = _override_get_db

    with TestClient(fastapi_app) as thread_safe_client:
        def _fetch():
            return thread_safe_client.get("/api/v1/referrals/me", headers=headers)

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(_fetch)
            second = executor.submit(_fetch)
            response_one = first.result(timeout=2)
            response_two = second.result(timeout=2)

        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"requests took too long ({elapsed:.3f}s)"
        assert response_one.status_code == status.HTTP_200_OK
        assert response_two.status_code == status.HTTP_200_OK

        payload_one = response_one.json()
        payload_two = response_two.json()

        assert payload_one["code"]
        assert payload_one["code"] == payload_two["code"]

    fastapi_app.dependency_overrides = previous_overrides


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
        "/api/v1/referrals/checkout/apply-referral",
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
            "/api/v1/referrals/checkout/apply-referral",
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
        "/api/v1/referrals/checkout/apply-referral",
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

    response = client.get("/api/v1/admin/referrals/config", headers=headers)
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
    monkeypatch.setenv("REFERRALS_UNSAFE_STEP", "4")

    token = create_access_token(data={"sub": admin.email})
    headers = {"Authorization": f"Bearer {token}"}

    referrer = _create_user(db, "summary_referrer@example.com")
    referred = _create_user(db, "summary_referred@example.com")
    code = referral_service.ensure_code_for_user(referrer.id)
    assert code is not None

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

    response = client.get("/api/v1/admin/referrals/summary", headers=headers)
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

    response = client.get("/api/v1/admin/referrals/health", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == health_payload.model_dump()
