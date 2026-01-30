"""Round 4 coverage tests for ReferralService."""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
import ulid

from app.core.exceptions import RepositoryException, ServiceException
from app.models.referrals import RewardSide, RewardStatus
import app.services.referral_service as referral_service_module
from app.services.referral_service import ReferralService


@pytest.fixture
def referral_service(db):
    service = ReferralService(db)
    service.referral_code_repo = Mock()
    service.referral_click_repo = Mock()
    service.referral_attribution_repo = Mock()
    service.referral_reward_repo = Mock()
    service.booking_repo = Mock()
    service.instructor_profile_repo = Mock()
    service.config_service = Mock()
    service.referral_limit_repo = Mock()

    def _tx():
        return contextlib.nullcontext()

    service.transaction = _tx
    return service


def test_coerce_user_uuid_falls_back_to_uuid():
    raw = "123e4567-e89b-12d3-a456-426614174000"
    result = ReferralService._coerce_user_uuid(raw)
    assert isinstance(result, UUID)
    assert str(result) == raw


def test_coerce_user_uuid_ulid_success():
    ulid_str = str(ulid.ULID())
    result = ReferralService._coerce_user_uuid(ulid_str)
    assert isinstance(result, UUID)


def test_ensure_code_for_user_repository_error(referral_service, monkeypatch):
    monkeypatch.setattr(referral_service_module, "resolve_referrals_step", lambda: 2)
    referral_service.referral_code_repo.get_active_for_user.return_value = None
    referral_service.referral_code_repo.get_or_create_for_user.side_effect = RepositoryException(
        "boom"
    )

    with pytest.raises(ServiceException) as exc:
        referral_service.ensure_code_for_user("user_1")

    assert exc.value.code == "REFERRAL_CODE_ISSUANCE_TIMEOUT"


def test_resolve_code_prefers_slug(referral_service):
    code_row = Mock(code="CODE")
    referral_service.referral_code_repo.get_by_slug.return_value = code_row

    result = referral_service.resolve_code("slug")

    assert result is code_row
    referral_service.referral_code_repo.get_by_code.assert_not_called()


def test_ensure_code_for_user_step_disabled(referral_service, monkeypatch):
    monkeypatch.setattr(referral_service_module, "resolve_referrals_step", lambda: 1)
    referral_service.referral_code_repo.get_active_for_user.return_value = None

    assert referral_service.ensure_code_for_user("user_1") is None
    referral_service.referral_code_repo.get_or_create_for_user.assert_not_called()


def test_has_attribution_delegates_to_repo(referral_service):
    referral_service.referral_attribution_repo.exists_for_user.return_value = True

    assert referral_service.has_attribution("user_1") is True


def test_record_click_ignores_inactive_code(referral_service):
    referral_service.referral_code_repo.get_by_code.return_value = None

    referral_service.record_click(code="MISSING")

    referral_service.referral_click_repo.create.assert_not_called()


def test_attribute_signup_existing_attribution(referral_service):
    referral_service._assert_enabled = Mock(return_value={"enabled": True})
    referral_service.referral_attribution_repo.exists_for_user.return_value = True

    assert (
        referral_service.attribute_signup(
            referred_user_id="user_1",
            code="CODE",
            source="test",
            ts=datetime.now(timezone.utc),
        )
        is False
    )


def test_attribute_signup_missing_code(referral_service):
    referral_service._assert_enabled = Mock(return_value={"enabled": True})
    referral_service.referral_attribution_repo.exists_for_user.return_value = False
    referral_service.referral_code_repo.get_by_code.return_value = None

    assert (
        referral_service.attribute_signup(
            referred_user_id="user_1",
            code="CODE",
            source="test",
            ts=datetime.now(timezone.utc),
        )
        is False
    )


def test_attribute_signup_create_if_absent_false(referral_service):
    referral_service._assert_enabled = Mock(return_value={"enabled": True})
    referral_service.referral_attribution_repo.exists_for_user.return_value = False
    referral_service.referral_code_repo.get_by_code.return_value = Mock(id="code-1")
    referral_service.referral_attribution_repo.create_if_absent.return_value = False

    assert (
        referral_service.attribute_signup(
            referred_user_id="user_1",
            code="CODE",
            source="test",
            ts=datetime.now(timezone.utc),
        )
        is False
    )


def test_attribute_signup_success_creates_click(referral_service, monkeypatch):
    referral_service._assert_enabled = Mock(return_value={"enabled": True})
    referral_service.referral_attribution_repo.exists_for_user.return_value = False
    referral_service.referral_code_repo.get_by_code.return_value = Mock(id="code-1", code="REF")
    referral_service.referral_attribution_repo.create_if_absent.return_value = True
    monkeypatch.setattr(referral_service_module, "emit_referred_signup", Mock())

    assert (
        referral_service.attribute_signup(
            referred_user_id="user_1",
            code="REF",
            source="test",
            ts=datetime.now(timezone.utc),
            device_fp_hash="device",
        )
        is True
    )
    referral_service.referral_click_repo.create.assert_called_once()


def _setup_first_booking(referral_service, monkeypatch, *, self_referral: bool, velocity: bool):
    config = {
        "hold_days": 1,
        "expiry_months": 1,
        "student_amount_cents": 2000,
        "student_global_cap": 10,
    }
    referral_service._assert_enabled = Mock(return_value=config)
    attribution = Mock(code_id="code-1", ts=datetime.now(timezone.utc))
    referral_service.referral_attribution_repo.get_by_referred_user_id.return_value = attribution
    referral_service.referral_code_repo.get_by_id.return_value = Mock(
        referrer_user_id="referrer"
    )
    referral_service._beyond_student_cap = Mock(return_value=False)
    referral_service.referral_click_repo.get_fingerprint_snapshot.return_value = {
        "click_device": "device",
        "click_ip": "ip",
        "signup_device": "device",
        "signup_ip": "ip",
    }
    student_reward = SimpleNamespace(
        id="reward-1",
        status=RewardStatus.PENDING,
        side=RewardSide.STUDENT,
        referrer_user_id="referrer",
        referred_user_id="student",
        amount_cents=2000,
        unlock_ts=None,
    )
    referrer_reward = SimpleNamespace(
        id="reward-2",
        status=RewardStatus.PENDING,
        side=RewardSide.INSTRUCTOR,
        referrer_user_id="referrer",
        referred_user_id="student",
        amount_cents=2000,
        unlock_ts=None,
    )
    referral_service.referral_reward_repo.create_student_pair.return_value = (
        student_reward,
        referrer_reward,
    )
    monkeypatch.setattr(
        referral_service_module.referral_fraud,
        "is_self_referral",
        lambda **_kwargs: self_referral,
    )
    referral_service._is_velocity_abuse = Mock(return_value=velocity)
    return student_reward, referrer_reward


def test_on_first_booking_completed_emits_pending(referral_service, monkeypatch):
    monkeypatch.setattr(referral_service_module, "emit_reward_pending", Mock())
    _setup_first_booking(referral_service, monkeypatch, self_referral=False, velocity=False)

    referral_service.on_first_booking_completed(
        user_id="student",
        booking_id="booking",
        amount_cents=5000,
        completed_at=datetime.now(timezone.utc),
    )

    assert referral_service.referral_reward_repo.create_student_pair.called
    assert referral_service_module.emit_reward_pending.call_count == 2


def test_on_first_booking_completed_self_referral_voids(referral_service, monkeypatch):
    monkeypatch.setattr(referral_service_module, "emit_reward_pending", Mock())
    _setup_first_booking(referral_service, monkeypatch, self_referral=True, velocity=False)
    referral_service._void_rewards = Mock()

    referral_service.on_first_booking_completed(
        user_id="student",
        booking_id="booking",
        amount_cents=5000,
        completed_at=datetime.now(timezone.utc),
    )

    referral_service._void_rewards.assert_called_once()


def test_on_first_booking_completed_velocity_voids(referral_service, monkeypatch):
    monkeypatch.setattr(referral_service_module, "emit_reward_pending", Mock())
    _setup_first_booking(referral_service, monkeypatch, self_referral=False, velocity=True)
    referral_service._void_rewards = Mock()

    referral_service.on_first_booking_completed(
        user_id="student",
        booking_id="booking",
        amount_cents=5000,
        completed_at=datetime.now(timezone.utc),
    )

    referral_service._void_rewards.assert_called_once()


def test_on_first_booking_completed_no_attribution(referral_service):
    referral_service._assert_enabled = Mock(
        return_value={
            "hold_days": 1,
            "expiry_months": 1,
            "student_amount_cents": 2000,
            "student_global_cap": 10,
        }
    )
    referral_service.referral_attribution_repo.get_by_referred_user_id.return_value = None

    referral_service.on_first_booking_completed(
        user_id="student_1",
        booking_id="booking_1",
        amount_cents=5000,
        completed_at=datetime.now(timezone.utc),
    )

    referral_service.referral_reward_repo.create_student_pair.assert_not_called()


def test_on_first_booking_completed_dangling_code(referral_service):
    referral_service._assert_enabled = Mock(
        return_value={
            "hold_days": 1,
            "expiry_months": 1,
            "student_amount_cents": 2000,
            "student_global_cap": 10,
        }
    )
    attribution = Mock(code_id="code-1", ts=datetime.now(timezone.utc))
    referral_service.referral_attribution_repo.get_by_referred_user_id.return_value = attribution
    referral_service.referral_code_repo.get_by_id.return_value = None

    referral_service.on_first_booking_completed(
        user_id="student_1",
        booking_id="booking_1",
        amount_cents=5000,
        completed_at=datetime.now(timezone.utc),
    )

    referral_service.referral_reward_repo.create_student_pair.assert_not_called()


def test_instructor_referral_disabled_config(referral_service):
    referral_service._get_config = Mock(return_value={"enabled": False})

    assert (
        referral_service.on_instructor_lesson_completed(
            instructor_user_id="inst_1",
            booking_id="booking_1",
            completed_at=datetime.now(timezone.utc),
        )
        is None
    )


def test_instructor_referral_missing_booking_id(referral_service):
    referral_service._get_config = Mock(return_value={"enabled": True})

    assert (
        referral_service.on_instructor_lesson_completed(
            instructor_user_id="inst_1",
            booking_id=None,
            lesson_id=None,
            completed_at=datetime.now(timezone.utc),
        )
        is None
    )


def test_instructor_referral_mismatched_booking_id(referral_service):
    referral_service._get_config = Mock(return_value={"enabled": True})
    referral_service.booking_repo.count_instructor_total_completed.return_value = 0

    assert (
        referral_service.on_instructor_lesson_completed(
            instructor_user_id="inst_1",
            booking_id="booking_1",
            lesson_id="lesson_2",
            completed_at=datetime.now(timezone.utc),
        )
        is None
    )


def test_instructor_referral_dangling_code(referral_service):
    referral_service._get_config = Mock(return_value={"enabled": True})
    referral_service.booking_repo.count_instructor_total_completed.return_value = 1
    referral_service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
        code_id="code-1"
    )
    referral_service.referral_code_repo.get_by_id.return_value = None

    assert (
        referral_service.on_instructor_lesson_completed(
            instructor_user_id="inst_1",
            booking_id="booking_1",
            completed_at=datetime.now(timezone.utc),
        )
        is None
    )


def test_instructor_referral_bad_cap_parsing(referral_service):
    referral_service._get_config = Mock(
        return_value={
            "enabled": True,
            "instructor_founding_bonus_cents": 7500,
            "instructor_standard_bonus_cents": 5000,
        }
    )
    referral_service.booking_repo.count_instructor_total_completed.return_value = 1
    referral_service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
        code_id="code-1"
    )
    referral_service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="ref")
    referral_service.instructor_profile_repo.get_by_user_id.return_value = Mock(
        stripe_connected_account=Mock()
    )
    referral_service.config_service.get_pricing_config.return_value = (
        {"founding_instructor_cap": "bad"},
        None,
    )
    referral_service.instructor_profile_repo.count_founding_instructors.return_value = 0
    referral_service.referral_reward_repo.create_instructor_referral_payout.return_value = None

    assert (
        referral_service.on_instructor_lesson_completed(
            instructor_user_id="inst_1",
            booking_id="booking_1",
            completed_at=datetime.now(timezone.utc),
        )
        is None
    )


def test_instructor_referral_task_queue_failure(referral_service, monkeypatch):
    referral_service._get_config = Mock(
        return_value={
            "enabled": True,
            "instructor_founding_bonus_cents": 7500,
            "instructor_standard_bonus_cents": 5000,
        }
    )
    referral_service.booking_repo.count_instructor_total_completed.return_value = 1
    referral_service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
        code_id="code-1"
    )
    referral_service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="ref")
    referral_service.instructor_profile_repo.get_by_user_id.return_value = Mock(
        stripe_connected_account=Mock()
    )
    referral_service.config_service.get_pricing_config.return_value = (
        {"founding_instructor_cap": 100},
        None,
    )
    referral_service.instructor_profile_repo.count_founding_instructors.return_value = 0
    referral_service.referral_reward_repo.create_instructor_referral_payout.return_value = Mock(
        id="payout-1"
    )

    class FailingTask:
        def delay(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.tasks.referral_tasks.process_instructor_referral_payout", FailingTask()
    )

    result = referral_service.on_instructor_lesson_completed(
        instructor_user_id="inst_1",
        booking_id="booking_1",
        completed_at=datetime.now(timezone.utc),
    )

    assert result == "payout-1"


def test_instructor_referral_task_queue_success(referral_service, monkeypatch):
    referral_service._get_config = Mock(
        return_value={
            "enabled": True,
            "instructor_founding_bonus_cents": 7500,
            "instructor_standard_bonus_cents": 5000,
        }
    )
    referral_service.booking_repo.count_instructor_total_completed.return_value = 1
    referral_service.referral_attribution_repo.get_by_referred_user_id.return_value = Mock(
        code_id="code-1"
    )
    referral_service.referral_code_repo.get_by_id.return_value = Mock(referrer_user_id="ref")
    referral_service.instructor_profile_repo.get_by_user_id.return_value = Mock(
        stripe_connected_account=Mock()
    )
    referral_service.config_service.get_pricing_config.return_value = (
        {"founding_instructor_cap": 100},
        None,
    )
    referral_service.instructor_profile_repo.count_founding_instructors.return_value = 0
    referral_service.referral_reward_repo.create_instructor_referral_payout.return_value = Mock(
        id="payout-2"
    )

    class HealthyTask:
        def delay(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.tasks.referral_tasks.process_instructor_referral_payout", HealthyTask()
    )

    result = referral_service.on_instructor_lesson_completed(
        instructor_user_id="inst_2",
        booking_id="booking_2",
        completed_at=datetime.now(timezone.utc),
    )

    assert result == "payout-2"


def test_get_rewards_by_status_returns_mapping(referral_service):
    referral_service.referral_reward_repo.list_by_user_and_status.return_value = []

    result = referral_service.get_rewards_by_status(user_id="user_1", limit=5)

    assert RewardStatus.PENDING in result
    assert RewardStatus.UNLOCKED in result
    assert RewardStatus.REDEEMED in result


def test_get_admin_config_uses_effective_config(referral_service):
    referral_service._get_config = Mock(
        return_value={
            "student_amount_cents": 2000,
            "instructor_amount_cents": 5000,
            "min_basket_cents": 1000,
            "hold_days": 7,
            "expiry_months": 3,
            "student_global_cap": 100,
            "version": 1,
            "source": "db",
            "enabled": True,
        }
    )

    config = referral_service.get_admin_config()

    assert config.student_amount_cents == 2000
    assert config.flags["enabled"] is True


def test_get_admin_summary_cap_utilization_and_top_referrers(referral_service):
    referral_service.referral_reward_repo.counts_by_status.return_value = {}
    referral_service._get_config = Mock(return_value={"student_global_cap": 100})
    referral_service.referral_reward_repo.total_student_rewards.return_value = 50
    referral_service.referral_reward_repo.top_referrers.return_value = [
        ("123e4567-e89b-12d3-a456-426614174000", 2, "CODE"),
    ]
    referral_service.referral_click_repo.clicks_since.return_value = 0
    referral_service.referral_attribution_repo.attributions_since.return_value = 0

    summary = referral_service.get_admin_summary()

    assert summary.cap_utilization_percent == 50.0
    assert summary.top_referrers


def test_get_admin_summary_skips_invalid_referrer_ids(referral_service):
    referral_service.referral_reward_repo.counts_by_status.return_value = {}
    referral_service._get_config = Mock(return_value={"student_global_cap": 0})
    referral_service.referral_reward_repo.total_student_rewards.return_value = 0
    referral_service.referral_reward_repo.top_referrers.return_value = [
        ("not-a-uuid", 2, "CODE"),
    ]
    referral_service.referral_click_repo.clicks_since.return_value = 0
    referral_service.referral_attribution_repo.attributions_since.return_value = 0

    summary = referral_service.get_admin_summary()

    assert summary.top_referrers == []


def test_get_admin_health_warns_on_stale_runs(referral_service, monkeypatch):
    referral_service.referral_reward_repo.counts_by_status.return_value = {
        "pending": 0,
        "unlocked": 0,
        "void": 0,
    }
    referral_service.referral_reward_repo.count_pending_due.return_value = 0

    stale = datetime.now(timezone.utc) - timedelta(seconds=1901)
    monkeypatch.setattr(referral_service_module, "get_last_success_timestamp", lambda: stale)

    class HealthyControl:
        def ping(self, timeout: int = 1):
            return []

    monkeypatch.setattr(
        referral_service_module,
        "celery_app",
        SimpleNamespace(control=HealthyControl()),
    )

    health = referral_service.get_admin_health()

    assert health.last_run_age_s is not None
    assert health.last_run_age_s > 1800


def test_assert_enabled_raises_when_disabled(referral_service, monkeypatch):
    monkeypatch.setattr(referral_service_module, "get_effective_config", lambda *_: {"enabled": False})

    with pytest.raises(RuntimeError):
        referral_service._assert_enabled()


def test_get_admin_health_recent_run_and_non_dict_response(referral_service, monkeypatch):
    referral_service.referral_reward_repo.counts_by_status.return_value = {
        "pending": 1,
        "unlocked": 0,
        "void": 0,
    }
    referral_service.referral_reward_repo.count_pending_due.return_value = 0
    recent = datetime.now(timezone.utc) - timedelta(seconds=60)
    monkeypatch.setattr(referral_service_module, "get_last_success_timestamp", lambda: recent)

    class MixedControl:
        def ping(self, timeout: int = 1):
            return ["ok", {"celery@worker-2": {"ok": "pong"}}]

    monkeypatch.setattr(
        referral_service_module,
        "celery_app",
        SimpleNamespace(control=MixedControl()),
    )

    health = referral_service.get_admin_health()

    assert health.workers == ["celery@worker-2"]
    assert health.last_run_age_s is not None


def test_add_months_and_days_in_month(referral_service):
    base = datetime(2024, 1, 31, tzinfo=timezone.utc)
    result = referral_service._add_months(base, 1)

    assert result.month == 2
    assert result.day == 29
    assert referral_service._days_in_month(2024, 2) == 29


def test_beyond_student_cap_uses_config(referral_service):
    referral_service.referral_reward_repo.count_student_rewards_for_cap.return_value = 5
    referral_service._get_config = Mock(return_value={"student_global_cap": 4})

    assert referral_service._beyond_student_cap("user_1") is True


def test_is_velocity_abuse_updates_limits(referral_service, monkeypatch):
    referral_service.referral_attribution_repo.velocity_counts.return_value = (5, 10)
    monkeypatch.setattr(
        referral_service_module.referral_fraud,
        "is_velocity_abuse",
        lambda **_kwargs: True,
    )
    referral_service._get_config = Mock(return_value={"student_global_cap": 10})

    assert referral_service._is_velocity_abuse("user_1") is True
    referral_service.referral_limit_repo.upsert.assert_called_once()


def test_void_rewards_emits_events(referral_service, monkeypatch):
    reward = SimpleNamespace(id="reward-1")
    monkeypatch.setattr(referral_service_module, "emit_reward_voided", Mock())

    referral_service._void_rewards([reward], reason="test")

    referral_service.referral_reward_repo.void_rewards.assert_called_once_with(["reward-1"])
    referral_service_module.emit_reward_voided.assert_called_once()
