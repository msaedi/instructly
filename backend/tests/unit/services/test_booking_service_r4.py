"""Round 4 deep coverage for booking_service.py."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.core.enums import RoleName
from app.core.exceptions import (
    BusinessRuleException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.core.ulid_helper import generate_ulid
from app.models.booking import BookingStatus, PaymentStatus
from app.services.booking_service import BookingService

REAL_DATETIME = datetime


def _transaction_cm() -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None
    return cm


def _freeze_time(monkeypatch: pytest.MonkeyPatch, target: datetime) -> None:
    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return target.astimezone(tz)
            if target.tzinfo:
                return target.replace(tzinfo=None)
            return target

        @classmethod
        def combine(cls, *args, **kwargs):
            return REAL_DATETIME.combine(*args, **kwargs)

    monkeypatch.setattr("app.services.booking_service.datetime", _FixedDateTime)


def make_booking(**overrides: object) -> SimpleNamespace:
    booking = SimpleNamespace(
        id=overrides.get("id", generate_ulid()),
        student_id=overrides.get("student_id", generate_ulid()),
        instructor_id=overrides.get("instructor_id", generate_ulid()),
        status=overrides.get("status", BookingStatus.CONFIRMED),
        payment_status=overrides.get("payment_status", PaymentStatus.AUTHORIZED.value),
        booking_date=overrides.get("booking_date", date(2030, 1, 1)),
        start_time=overrides.get("start_time", time(10, 0)),
        end_time=overrides.get("end_time", time(11, 0)),
        duration_minutes=overrides.get("duration_minutes", 60),
        hourly_rate=overrides.get("hourly_rate", 100),
        total_price=overrides.get("total_price", 100),
        payment_intent_id=overrides.get("payment_intent_id", "pi_123"),
        locked_amount_cents=overrides.get("locked_amount_cents", 0),
        credits_reserved_cents=overrides.get("credits_reserved_cents", 0),
        is_cancellable=overrides.get("is_cancellable", True),
        has_locked_funds=overrides.get("has_locked_funds", False),
        rescheduled_from_booking_id=overrides.get("rescheduled_from_booking_id", None),
        lock_resolved_at=overrides.get("lock_resolved_at", None),
        no_show_reported_at=overrides.get("no_show_reported_at", None),
        no_show_resolved_at=overrides.get("no_show_resolved_at", None),
        no_show_disputed=overrides.get("no_show_disputed", False),
        no_show_type=overrides.get("no_show_type", None),
        created_at=overrides.get("created_at", datetime(2030, 1, 1, 8, 0, tzinfo=timezone.utc)),
        updated_at=overrides.get("updated_at", None),
        confirmed_at=overrides.get("confirmed_at", None),
        completed_at=overrides.get("completed_at", None),
        instructor_service=overrides.get("instructor_service", None),
        settlement_outcome=overrides.get("settlement_outcome", None),
        cancelled_at=overrides.get("cancelled_at", None),
    )
    for key, value in overrides.items():
        setattr(booking, key, value)
    booking.to_dict = lambda: {"status": booking.status}
    booking.cancel = Mock()
    booking.mark_no_show = Mock()
    return booking


def make_user(role: RoleName, **overrides: object) -> SimpleNamespace:
    user = SimpleNamespace(
        id=overrides.get("id", generate_ulid()),
        roles=[SimpleNamespace(name=role)],
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.transaction.return_value = _transaction_cm()
    return repo


@pytest.fixture
def booking_service(mock_db: MagicMock, mock_repository: MagicMock) -> BookingService:
    service = BookingService(
        mock_db,
        notification_service=MagicMock(),
        event_publisher=MagicMock(),
        repository=mock_repository,
        conflict_checker_repository=MagicMock(),
        system_message_service=MagicMock(),
    )
    service.transaction = MagicMock(return_value=_transaction_cm())
    return service


# --- Group 1: early validation paths ---


def test_create_booking_operational_error_non_deadlock_propagates(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT)
    booking_data = SimpleNamespace(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=None,
    )
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._is_deadlock_error = Mock(return_value=False)

    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("boom"))
    )

    with pytest.raises(OperationalError):
        booking_service.create_booking(student, booking_data, selected_duration=60)


def test_create_booking_with_payment_setup_operational_error_non_deadlock_propagates(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT)
    booking_data = SimpleNamespace(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=None,
    )
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._is_deadlock_error = Mock(return_value=False)

    mock_repository.transaction.return_value = _transaction_cm()
    booking_service._create_booking_record = Mock(
        side_effect=OperationalError("stmt", "params", Exception("boom"))
    )

    with pytest.raises(OperationalError):
        booking_service.create_booking_with_payment_setup(student, booking_data, selected_duration=60)


def test_create_booking_with_payment_setup_reschedule_linkage_exception_suppressed(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    student = make_user(RoleName.STUDENT)
    booking_data = SimpleNamespace(
        instructor_id=generate_ulid(),
        booking_date=date(2030, 1, 1),
        start_time=time(10, 0),
        end_time=None,
    )
    service = SimpleNamespace(duration_options=[60])
    instructor_profile = SimpleNamespace()
    booking = make_booking(total_price=120)
    reschedule_id = generate_ulid()

    booking_service._validate_booking_prerequisites = Mock(return_value=(service, instructor_profile))
    booking_service._calculate_and_validate_end_time = Mock(return_value=time(11, 0))
    booking_service._validate_against_availability_bits = Mock()
    booking_service._check_conflicts_and_rules = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()
    booking_service._write_booking_audit = Mock()
    booking_service._create_booking_record = Mock(return_value=booking)
    booking_service._snapshot_booking = Mock(return_value={})
    mock_repository.transaction.return_value = _transaction_cm()

    def _get_by_id(booking_id: str):
        if booking_id == reschedule_id:
            raise Exception("boom")
        return booking

    mock_repository.get_by_id.side_effect = _get_by_id

    with patch("app.services.booking_service.StripeService") as stripe_cls, patch(
        "app.services.booking_service.stripe.SetupIntent.create",
        return_value=SimpleNamespace(id="seti_1", client_secret="secret", status="requires_payment_method"),
    ), patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
        stripe_cls.return_value.get_or_create_customer.return_value = SimpleNamespace(
            stripe_customer_id="cus_123"
        )
        payment_repo.return_value.create_payment_event = Mock()

        result = booking_service.create_booking_with_payment_setup(
            student,
            booking_data,
            selected_duration=60,
            rescheduled_from_booking_id=reschedule_id,
        )

    assert result.status == BookingStatus.PENDING
    assert result.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value


# --- Group 4: reschedule lock paths ---


def test_activate_lock_for_reschedule_not_found_after_auth(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(payment_status=PaymentStatus.SCHEDULED.value)
    booking_service._get_booking_start_utc = Mock(
        return_value=datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)
    )
    mock_repository.get_by_id_for_update.return_value = booking
    mock_repository.get_booking_with_details.return_value = None

    with patch(
        "app.tasks.payment_tasks._process_authorization_for_booking",
        return_value={"success": True},
    ):
        with pytest.raises(NotFoundException):
            booking_service.activate_lock_for_reschedule(booking.id)


def test_activate_lock_for_reschedule_locked_amount_parse_and_credit_forfeit_error(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value, credits_reserved_cents=25)
    mock_repository.get_by_id_for_update.return_value = booking
    mock_repository.get_booking_with_details.return_value = booking

    with patch("app.services.stripe_service.StripeService") as stripe_cls, patch(
        "app.repositories.payment_repository.PaymentRepository"
    ) as payment_repo, patch("app.services.credit_service.CreditService") as credit_cls:
        stripe_service = stripe_cls.return_value
        stripe_service.capture_payment_intent.return_value = {
            "amount_received": "not-an-int",
            "transfer_id": "tr_123",
            "transfer_amount": 100,
        }
        stripe_service.reverse_transfer.return_value = {"reversal": {"id": "rv_123"}}
        payment_repo.return_value.create_payment_event = Mock()
        credit_cls.return_value.forfeit_credits_for_booking.side_effect = Exception("boom")

        result = booking_service.activate_lock_for_reschedule(booking.id)

    assert result["locked"] is True
    assert result["locked_amount_cents"] is None
    assert booking.payment_status == PaymentStatus.LOCKED.value
    assert booking.credits_reserved_cents == 0


def test_resolve_lock_for_booking_refund_error_and_missing_account(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    locked_booking = make_booking(
        payment_status=PaymentStatus.LOCKED.value,
        lock_resolved_at=None,
        hourly_rate=100,
        duration_minutes=60,
        payment_intent_id="pi_123",
    )
    mock_repository.get_by_id_for_update.return_value = locked_booking

    booking_service.conflict_checker_repository.get_instructor_profile.side_effect = Exception(
        "boom"
    )

    with patch("app.services.booking_service.PricingService") as pricing_cls, patch(
        "app.services.booking_service.StripeService"
    ) as stripe_cls, patch(
        "app.repositories.payment_repository.PaymentRepository"
    ) as payment_repo, patch("app.services.credit_service.CreditService") as credit_cls:
        pricing_cls.return_value.compute_booking_pricing.return_value = {
            "target_instructor_payout_cents": 500
        }
        stripe_cls.return_value.refund_payment.side_effect = Exception("refund failed")
        payment_repo.return_value.get_payment_by_booking_id.side_effect = Exception("boom")
        payment_repo.return_value.get_credits_issued_for_source.return_value = []
        payment_repo.return_value.create_payment_event = Mock()
        credit_cls.return_value.issue_credit = Mock()

        result = booking_service.resolve_lock_for_booking(locked_booking.id, "instructor_cancelled")

    assert result["success"] is True
    assert result["resolution"] == "instructor_cancelled"


# --- Group 5/6: finalize cancellation branches ---


def test_finalize_cancellation_over_24h_regular_release_credit_error(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "over_24h_regular",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "hours_until": 30.0,
        "lesson_price_cents": 1200,
    }
    stripe_results = {"cancel_pi_success": True}
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.release_credits_for_booking.side_effect = Exception("boom")
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value


def test_finalize_cancellation_over_24h_gaming_credit_issue_error(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "over_24h_gaming",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "student_id": booking.student_id,
        "hours_until": 30.0,
        "hours_from_original": 10.0,
        "lesson_price_cents": 1500,
        "rescheduled_from_booking_id": None,
        "original_lesson_datetime": None,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_failed": False,
        "capture_data": {"transfer_id": "tr_123"},
    }
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.forfeit_credits_for_booking.side_effect = Exception("boom")
        credit_cls.return_value.issue_credit.side_effect = Exception("boom")
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value
    assert booking.settlement_outcome == "student_cancel_12_24_full_credit"


def test_finalize_cancellation_under_12h_payout_amount_cast_error_and_credit_forfeit_error(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "under_12h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "student_id": booking.student_id,
        "lesson_price_cents": 1000,
    }
    stripe_results = {
        "capture_success": True,
        "reverse_success": True,
        "payout_success": True,
        "payout_amount_cents": "not-int",
        "capture_data": {"amount_received": 1000, "transfer_id": "tr_1", "transfer_amount": 800},
    }
    payment_repo = MagicMock()
    payment_repo.get_credits_issued_for_source.return_value = []

    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.forfeit_credits_for_booking.side_effect = Exception("boom")
        credit_cls.return_value.issue_credit = Mock()
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.SETTLED.value
    assert booking.instructor_payout_amount == 0


def test_finalize_cancellation_under_12h_capture_failed(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "under_12h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "student_id": booking.student_id,
        "lesson_price_cents": 1000,
    }
    stripe_results = {"capture_success": False, "error": "boom"}
    payment_repo = MagicMock()

    with patch("app.services.credit_service.CreditService"):
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert booking.capture_retry_count == 1


def test_finalize_cancellation_under_12h_no_pi_release_error(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.PAYMENT_METHOD_REQUIRED.value)
    ctx = {
        "scenario": "under_12h_no_pi",
        "booking_id": booking.id,
        "payment_intent_id": None,
        "student_id": booking.student_id,
        "lesson_price_cents": 1000,
    }
    stripe_results: dict[str, object] = {}
    payment_repo = MagicMock()

    with patch("app.services.credit_service.CreditService") as credit_cls:
        credit_cls.return_value.release_credits_for_booking.side_effect = Exception("boom")
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.payment_status == PaymentStatus.MANUAL_REVIEW.value
    assert booking.auth_last_error == "missing_payment_intent"


def test_finalize_cancellation_instructor_cancel_refund_amount_invalid(
    booking_service: BookingService,
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    ctx = {
        "scenario": "instructor_cancel_over_24h",
        "booking_id": booking.id,
        "payment_intent_id": "pi_123",
        "hours_until": 30.0,
        "lesson_price_cents": 1000,
    }
    stripe_results = {
        "refund_success": True,
        "refund_data": {"refund_id": "re_1", "amount_refunded": "bad"},
    }
    payment_repo = MagicMock()

    with patch("app.services.credit_service.CreditService"):
        booking_service._finalize_cancellation(booking, ctx, stripe_results, payment_repo)

    assert booking.refunded_to_card_amount == 0


# --- Group 6: completion flow branches ---


def test_complete_booking_missing_after_complete(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    booking = make_booking(status=BookingStatus.CONFIRMED, instructor_id=instructor.id)

    mock_repository.get_booking_with_details.return_value = booking
    mock_repository.complete_booking.return_value = None

    with pytest.raises(NotFoundException):
        booking_service.complete_booking(booking.id, instructor)


def test_complete_booking_logs_credit_and_message_errors(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    booking = make_booking(status=BookingStatus.CONFIRMED, instructor_id=instructor.id)
    mock_repository.get_booking_with_details.side_effect = [booking, booking]
    mock_repository.complete_booking.return_value = booking

    booking_service._invalidate_booking_caches = Mock()

    with patch("app.services.booking_service.StudentCreditService") as credit_cls:
        credit_cls.return_value.maybe_issue_milestone_credit.side_effect = Exception("boom")
        booking_service.system_message_service.create_booking_completed_message.side_effect = (
            Exception("boom")
        )
        with patch("app.services.referral_service.ReferralService") as referral_cls:
            referral_cls.return_value.on_instructor_lesson_completed.side_effect = Exception("boom")
            booking_service.complete_booking(booking.id, instructor)

    assert booking_service._invalidate_booking_caches.called


def test_instructor_mark_complete_category_attribute_error(
    booking_service: BookingService, mock_repository: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    booking = make_booking(
        status=BookingStatus.CONFIRMED,
        instructor_id=instructor.id,
        instructor_service=SimpleNamespace(),
    )
    mock_repository.get_by_id.side_effect = [booking, booking]

    fixed_now = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
    _freeze_time(monkeypatch, fixed_now)
    booking_service._get_booking_end_utc = Mock(return_value=fixed_now - timedelta(minutes=30))

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo, patch(
        "app.services.badge_award_service.BadgeAwardService"
    ) as badge_cls, patch("app.services.referral_service.ReferralService") as referral_cls:
        payment_repo.return_value.create_payment_event = Mock()
        badge_cls.return_value.check_and_award_on_lesson_completed = Mock()
        referral_cls.return_value.on_instructor_lesson_completed = Mock()

        booking_service.instructor_mark_complete(booking.id, instructor, notes="done")

    _, kwargs = badge_cls.return_value.check_and_award_on_lesson_completed.call_args
    assert kwargs["category_slug"] is None


def test_instructor_mark_complete_refresh_missing(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    booking = make_booking(status=BookingStatus.CONFIRMED, instructor_id=instructor.id)
    mock_repository.get_by_id.side_effect = [booking, None]
    booking_service._get_booking_end_utc = Mock(
        return_value=datetime.now(timezone.utc) - timedelta(hours=1)
    )

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo, patch(
        "app.services.badge_award_service.BadgeAwardService"
    ) as badge_cls:
        payment_repo.return_value.create_payment_event = Mock()
        badge_cls.return_value.check_and_award_on_lesson_completed = Mock()

        with pytest.raises(NotFoundException):
            booking_service.instructor_mark_complete(booking.id, instructor)


# --- Group 7: dispute & no-show flows ---


def test_instructor_dispute_completion_not_found(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    mock_repository.get_by_id.return_value = None

    with pytest.raises(NotFoundException):
        booking_service.instructor_dispute_completion(booking_id=generate_ulid(), instructor=instructor, reason="x")


def test_instructor_dispute_completion_wrong_instructor(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    booking = make_booking(instructor_id=generate_ulid())
    mock_repository.get_by_id.return_value = booking

    with pytest.raises(ValidationException):
        booking_service.instructor_dispute_completion(booking.id, instructor, reason="x")


def test_instructor_dispute_completion_refresh_missing(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    booking = make_booking(instructor_id=instructor.id)
    mock_repository.get_by_id.side_effect = [booking, None]

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
        payment_repo.return_value.create_payment_event = Mock()
        with pytest.raises(NotFoundException):
            booking_service.instructor_dispute_completion(booking.id, instructor, reason="x")


def test_report_no_show_invalid_reporter_for_instructor_no_show(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(status=BookingStatus.CONFIRMED)
    reporter = make_user(RoleName.INSTRUCTOR)
    mock_repository.get_booking_with_details.return_value = booking

    booking_service._get_booking_start_utc = Mock(return_value=datetime.now(timezone.utc) - timedelta(hours=1))
    booking_service._get_booking_end_utc = Mock(return_value=datetime.now(timezone.utc) - timedelta(minutes=30))

    with pytest.raises(ForbiddenException):
        booking_service.report_no_show(
            booking_id=booking.id,
            reporter=reporter,
            no_show_type="instructor",
            reason=None,
        )


def test_report_no_show_invalid_no_show_type(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(status=BookingStatus.CONFIRMED)
    reporter = make_user(RoleName.ADMIN)
    mock_repository.get_booking_with_details.return_value = booking

    booking_service._get_booking_start_utc = Mock(return_value=datetime.now(timezone.utc) - timedelta(hours=1))
    booking_service._get_booking_end_utc = Mock(return_value=datetime.now(timezone.utc) - timedelta(minutes=30))

    with pytest.raises(ValidationException):
        booking_service.report_no_show(
            booking_id=booking.id,
            reporter=reporter,
            no_show_type="other",
            reason=None,
        )


def test_report_no_show_already_reported(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        status=BookingStatus.CONFIRMED,
        no_show_reported_at=datetime.now(timezone.utc),
    )
    reporter = make_user(RoleName.STUDENT, id=booking.student_id)
    mock_repository.get_booking_with_details.return_value = booking

    booking_service._get_booking_start_utc = Mock(return_value=datetime.now(timezone.utc) - timedelta(hours=1))
    booking_service._get_booking_end_utc = Mock(return_value=datetime.now(timezone.utc) - timedelta(minutes=30))
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service._write_booking_audit = Mock()

    with pytest.raises(BusinessRuleException):
        booking_service.report_no_show(
            booking_id=booking.id,
            reporter=reporter,
            no_show_type="instructor",
            reason=None,
        )


def test_dispute_no_show_already_resolved(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=1),
        no_show_resolved_at=datetime.now(timezone.utc),
        no_show_type="instructor",
    )
    disputer = make_user(RoleName.INSTRUCTOR, id=booking.instructor_id)
    mock_repository.get_booking_with_details.return_value = booking

    with pytest.raises(BusinessRuleException):
        booking_service.dispute_no_show(booking_id=booking.id, disputer=disputer, reason="x")


def test_dispute_no_show_invalid_type(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=1),
        no_show_type="other",
    )
    disputer = make_user(RoleName.INSTRUCTOR, id=booking.instructor_id)
    mock_repository.get_booking_with_details.return_value = booking

    with pytest.raises(BusinessRuleException):
        booking_service.dispute_no_show(booking_id=booking.id, disputer=disputer, reason="x")


def test_dispute_no_show_naive_reported_at_success(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime(2030, 1, 1, 10, 0, 0),
        no_show_type="instructor",
    )
    disputer = make_user(RoleName.INSTRUCTOR, id=booking.instructor_id)
    mock_repository.get_booking_with_details.return_value = booking
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service._write_booking_audit = Mock()
    booking_service._invalidate_booking_caches = Mock()

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
        payment_repo.return_value.create_payment_event = Mock()
        result = booking_service.dispute_no_show(
            booking_id=booking.id,
            disputer=disputer,
            reason="dispute",
        )

    assert result["disputed"] is True


def test_resolve_no_show_not_found(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    mock_repository.get_booking_with_details.return_value = None

    with pytest.raises(NotFoundException):
        booking_service.resolve_no_show(
            booking_id=generate_ulid(),
            resolution="confirmed_no_dispute",
            resolved_by=None,
        )


def test_resolve_no_show_missing_report(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(no_show_reported_at=None)
    mock_repository.get_booking_with_details.return_value = booking

    with pytest.raises(BusinessRuleException):
        booking_service.resolve_no_show(
            booking_id=booking.id,
            resolution="confirmed_no_dispute",
            resolved_by=None,
        )


def test_resolve_no_show_already_resolved(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc),
        no_show_resolved_at=datetime.now(timezone.utc),
    )
    mock_repository.get_booking_with_details.return_value = booking

    with pytest.raises(BusinessRuleException):
        booking_service.resolve_no_show(
            booking_id=booking.id,
            resolution="confirmed_no_dispute",
            resolved_by=None,
        )


def test_resolve_no_show_invalid_type_in_resolution(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc),
        no_show_type="other",
    )
    mock_repository.get_booking_with_details.return_value = booking

    with pytest.raises(BusinessRuleException):
        booking_service.resolve_no_show(
            booking_id=booking.id,
            resolution="confirmed_no_dispute",
            resolved_by=None,
        )


def test_resolve_no_show_invalid_resolution(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc),
        no_show_type="instructor",
    )
    mock_repository.get_booking_with_details.return_value = booking

    with pytest.raises(ValidationException):
        booking_service.resolve_no_show(
            booking_id=booking.id,
            resolution="bogus",
            resolved_by=None,
        )


def test_resolve_no_show_parse_errors_and_missing_after_resolution(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc),
        no_show_type="instructor",
        payment_status=PaymentStatus.MANUAL_REVIEW.value,
        has_locked_funds=True,
        rescheduled_from_booking_id="lock_1",
    )

    payment_record = SimpleNamespace(
        amount="bad",
        instructor_payout_cents="bad",
        application_fee="bad",
        base_price_cents="bad",
        instructor_tier_pct="bad",
        status="requires_capture",
    )

    mock_repository.get_booking_with_details.side_effect = [booking, None]
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service.resolve_lock_for_booking = Mock(return_value={"success": True})

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
        payment_repo.return_value.get_payment_by_booking_id.return_value = payment_record
        with pytest.raises(NotFoundException):
            booking_service.resolve_no_show(
                booking_id=booking.id,
                resolution="confirmed_no_dispute",
                resolved_by=None,
            )

    booking_service.resolve_lock_for_booking.assert_called_once_with("lock_1", "instructor_cancelled")


def test_resolve_no_show_student_locked_path(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(
        no_show_reported_at=datetime.now(timezone.utc),
        no_show_type="student",
        payment_status=PaymentStatus.AUTHORIZED.value,
        has_locked_funds=True,
        rescheduled_from_booking_id="lock_2",
    )
    mock_repository.get_booking_with_details.side_effect = [booking, booking]
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service.resolve_lock_for_booking = Mock(return_value={"success": True})
    booking_service._finalize_student_no_show = Mock()

    with patch("app.repositories.payment_repository.PaymentRepository") as payment_repo:
        payment_repo.return_value.get_payment_by_booking_id.return_value = None
        payment_repo.return_value.create_payment_event = Mock()
        result = booking_service.resolve_no_show(
            booking_id=booking.id,
            resolution="confirmed_no_dispute",
            resolved_by=None,
        )

    assert result["success"] is True
    booking_service.resolve_lock_for_booking.assert_called_once_with("lock_2", "new_lesson_completed")


def test_refund_for_instructor_no_show_cancel_success(
    booking_service: BookingService,
) -> None:
    stripe_service = Mock()
    stripe_service.cancel_payment_intent.return_value = None

    result = booking_service._refund_for_instructor_no_show(
        stripe_service=stripe_service,
        booking_id=generate_ulid(),
        payment_intent_id="pi_123",
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    assert result["cancel_success"] is True


def test_finalize_instructor_no_show_refund_amount_cast_error(
    booking_service: BookingService,
) -> None:
    booking = make_booking()
    credit_service = Mock()
    stripe_result = {"refund_success": True, "refund_data": {"amount_refunded": "bad"}}

    booking_service._finalize_instructor_no_show(
        booking=booking,
        stripe_result=stripe_result,
        credit_service=credit_service,
        refunded_cents=999,
        locked_booking_id=None,
    )

    assert booking.refunded_to_card_amount == 999


def test_mark_no_show_refresh_missing(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    instructor = make_user(RoleName.INSTRUCTOR)
    booking = make_booking(status=BookingStatus.CONFIRMED, instructor_id=instructor.id)
    mock_repository.get_booking_with_details.side_effect = [booking, None]

    booking_service._snapshot_booking = Mock(return_value={})
    booking_service._write_booking_audit = Mock()
    booking_service._enqueue_booking_outbox_event = Mock()

    with pytest.raises(NotFoundException):
        booking_service.mark_no_show(booking.id, instructor)
