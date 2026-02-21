"""Additional cancellation/no-show coverage for booking_service."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.integrations.hundredms_client import HundredMsError
from app.models.booking import BookingStatus, PaymentStatus
from app.services.booking_service import BookingService


class _BadStr:
    def __str__(self) -> str:  # pragma: no cover - invoked by Decimal conversion
        raise TypeError("bad")


def _transaction_cm() -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None
    return cm


def make_booking(**overrides: object) -> SimpleNamespace:
    pd = SimpleNamespace(
        payment_status=overrides.pop("payment_status", PaymentStatus.AUTHORIZED.value),
        payment_intent_id=overrides.pop("payment_intent_id", "pi_123"),
        payment_method_id=overrides.pop("payment_method_id", None),
        credits_reserved_cents=overrides.pop("credits_reserved_cents", 0),
        settlement_outcome=overrides.pop("settlement_outcome", None),
        instructor_payout_amount=overrides.pop("instructor_payout_amount", None),
        auth_last_error=overrides.pop("auth_last_error", None),
        capture_failed_at=overrides.pop("capture_failed_at", None),
        capture_retry_count=overrides.pop("capture_retry_count", 0),
    )
    booking = SimpleNamespace(
        id=overrides.get("id", generate_ulid()),
        student_id=overrides.get("student_id", generate_ulid()),
        instructor_id=overrides.get("instructor_id", generate_ulid()),
        status=overrides.get("status", BookingStatus.CONFIRMED),
        hourly_rate=overrides.get("hourly_rate", 100),
        duration_minutes=overrides.get("duration_minutes", 60),
        booking_date=overrides.get("booking_date", date(2030, 1, 1)),
        start_time=overrides.get("start_time", time(10, 0)),
        end_time=overrides.get("end_time", time(11, 0)),
        no_show_reported_at=overrides.get(
            "no_show_reported_at", datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)
        ),
        no_show_resolved_at=overrides.get("no_show_resolved_at", None),
        no_show_type=overrides.get("no_show_type", "instructor"),
        has_locked_funds=overrides.get("has_locked_funds", False),
        rescheduled_from_booking_id=overrides.get("rescheduled_from_booking_id", None),
        payment_detail=pd,
    )
    for key, value in overrides.items():
        setattr(booking, key, value)
    return booking


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_repository() -> MagicMock:
    repo = MagicMock()
    repo.get_booking_with_details.return_value = None
    repo.ensure_transfer.return_value = SimpleNamespace(
        refund_id=None,
        refund_failed_at=None,
        refund_error=None,
        refund_retry_count=0,
    )
    repo.get_transfer_by_booking_id.return_value = repo.ensure_transfer.return_value
    repo.ensure_payment.return_value = SimpleNamespace(
        payment_status=None,
        payment_intent_id=None,
        payment_method_id=None,
        credits_reserved_cents=0,
        settlement_outcome=None,
        instructor_payout_amount=None,
        auth_last_error=None,
        capture_failed_at=None,
        capture_retry_count=0,
    )
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
    service.audit_repository = MagicMock()
    service.cache_service = MagicMock()
    return service


def test_refund_for_instructor_no_show_missing_payment_intent(
    booking_service: BookingService,
) -> None:
    result = booking_service._refund_for_instructor_no_show(
        stripe_service=MagicMock(),
        booking_id="bk_1",
        payment_intent_id=None,
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    assert result["error"] == "missing_payment_intent"
    assert result["refund_success"] is False
    assert result["cancel_success"] is False


def test_refund_for_instructor_no_show_refund_failure(booking_service: BookingService) -> None:
    stripe_service = MagicMock()
    stripe_service.refund_payment.side_effect = Exception("boom")

    result = booking_service._refund_for_instructor_no_show(
        stripe_service=stripe_service,
        booking_id="bk_2",
        payment_intent_id="pi_123",
        payment_status=PaymentStatus.SETTLED.value,
    )

    assert result["refund_success"] is False
    assert result["error"] == "boom"


def test_refund_for_instructor_no_show_cancel_failure(booking_service: BookingService) -> None:
    stripe_service = MagicMock()
    stripe_service.cancel_payment_intent.side_effect = Exception("cancel failed")

    result = booking_service._refund_for_instructor_no_show(
        stripe_service=stripe_service,
        booking_id="bk_3",
        payment_intent_id="pi_456",
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    assert result["cancel_success"] is False
    assert result["error"] == "cancel failed"


def test_payout_for_student_no_show_already_captured(booking_service: BookingService) -> None:
    result = booking_service._payout_for_student_no_show(
        stripe_service=MagicMock(),
        booking_id="bk_4",
        payment_intent_id="pi_789",
        payment_status=PaymentStatus.SETTLED.value,
    )

    assert result["already_captured"] is True
    assert result["capture_success"] is False


def test_payout_for_student_no_show_missing_payment_intent(booking_service: BookingService) -> None:
    result = booking_service._payout_for_student_no_show(
        stripe_service=MagicMock(),
        booking_id="bk_5",
        payment_intent_id=None,
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    assert result["error"] == "missing_payment_intent"


def test_payout_for_student_no_show_capture_failure(booking_service: BookingService) -> None:
    stripe_service = MagicMock()
    stripe_service.capture_payment_intent.side_effect = Exception("capture failed")

    result = booking_service._payout_for_student_no_show(
        stripe_service=stripe_service,
        booking_id="bk_6",
        payment_intent_id="pi_999",
        payment_status=PaymentStatus.AUTHORIZED.value,
    )

    assert result["capture_success"] is False
    assert result["error"] == "capture failed"


def test_finalize_instructor_no_show_locked_skipped(booking_service: BookingService) -> None:
    booking = make_booking()
    credit_service = MagicMock()

    booking_service._finalize_instructor_no_show(
        booking=booking,
        stripe_result={"skipped": True},
        credit_service=credit_service,
        refunded_cents=500,
        locked_booking_id="lock_1",
    )

    bp = booking_service.repository.ensure_payment.return_value
    assert bp.payment_status == PaymentStatus.SETTLED.value
    assert booking.refunded_to_card_amount == 0
    assert bp.settlement_outcome == "instructor_no_show_full_refund"


def test_finalize_instructor_no_show_refund_success_parses_amount(
    booking_service: BookingService,
) -> None:
    booking = make_booking()
    credit_service = MagicMock()

    booking_service._finalize_instructor_no_show(
        booking=booking,
        stripe_result={"refund_success": True, "refund_data": {"refund_id": "rf_1", "amount_refunded": "1200"}},
        credit_service=credit_service,
        refunded_cents=1200,
        locked_booking_id=None,
    )

    bp = booking_service.repository.ensure_payment.return_value
    assert bp.payment_status == PaymentStatus.SETTLED.value
    transfer_record = booking_service.repository.ensure_transfer.return_value
    assert transfer_record.refund_id == "rf_1"
    assert booking.refunded_to_card_amount == 1200


def test_finalize_instructor_no_show_refund_failed(booking_service: BookingService) -> None:
    booking = make_booking()
    credit_service = MagicMock()

    booking_service._finalize_instructor_no_show(
        booking=booking,
        stripe_result={"refund_success": False, "cancel_success": False, "error": "refund_failed"},
        credit_service=credit_service,
        refunded_cents=0,
        locked_booking_id=None,
    )

    bp = booking_service.repository.ensure_payment.return_value
    assert bp.payment_status == PaymentStatus.MANUAL_REVIEW.value
    transfer_record = booking_service.repository.ensure_transfer.return_value
    assert transfer_record.refund_failed_at is not None


def test_finalize_student_no_show_locked_manual_review(booking_service: BookingService) -> None:
    booking = make_booking()
    credit_service = MagicMock()

    booking_service._finalize_student_no_show(
        booking=booking,
        stripe_result={"success": False},
        credit_service=credit_service,
        payout_cents=800,
        locked_booking_id="lock_2",
    )

    bp = booking_service.repository.ensure_payment.return_value
    assert bp.payment_status == PaymentStatus.MANUAL_REVIEW.value
    assert bp.instructor_payout_amount == 0


def test_finalize_student_no_show_capture_failed(booking_service: BookingService) -> None:
    booking = make_booking()
    credit_service = MagicMock()

    booking_service._finalize_student_no_show(
        booking=booking,
        stripe_result={"capture_success": False, "error": "capture_failed"},
        credit_service=credit_service,
        payout_cents=800,
        locked_booking_id=None,
    )

    bp = booking_service.repository.ensure_payment.return_value
    assert bp.payment_status == PaymentStatus.PAYMENT_METHOD_REQUIRED.value
    assert bp.capture_failed_at is not None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("succeeded", PaymentStatus.SETTLED.value),
        ("requires_capture", PaymentStatus.AUTHORIZED.value),
        ("authorized", PaymentStatus.AUTHORIZED.value),
        ("other", PaymentStatus.PAYMENT_METHOD_REQUIRED.value),
    ],
)
def test_cancel_no_show_report_status_mapping(
    booking_service: BookingService, status: str, expected: str
) -> None:
    booking = make_booking(payment_intent_id="pi_789")
    payment_record = SimpleNamespace(status=status)
    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.return_value = payment_record

    with patch("app.repositories.payment_repository.PaymentRepository", return_value=payment_repo):
        booking_service._cancel_no_show_report(booking)

    bp = booking_service.repository.ensure_payment.return_value
    assert bp.payment_status == expected


def test_cancel_no_show_report_no_payment_record(booking_service: BookingService) -> None:
    booking = make_booking(payment_intent_id=None)
    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.return_value = None

    with patch("app.repositories.payment_repository.PaymentRepository", return_value=payment_repo):
        booking_service._cancel_no_show_report(booking)

    bp = booking_service.repository.ensure_payment.return_value
    assert bp.payment_status is None


def test_resolve_no_show_cancelled_calculates_from_base_price(
    booking_service: BookingService, mock_repository: MagicMock
) -> None:
    booking = make_booking(payment_status=PaymentStatus.MANUAL_REVIEW.value)
    payment_record = SimpleNamespace(
        status="succeeded",
        amount=None,
        instructor_payout_cents=None,
        application_fee=None,
        base_price_cents=10000,
        instructor_tier_pct="0.2",
    )
    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.return_value = payment_record
    payment_repo.create_payment_event = Mock()

    mock_repository.get_booking_with_details.side_effect = [booking, booking]
    mock_repository.get_no_show_by_booking_id.return_value = SimpleNamespace(
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=1),
        no_show_resolved_at=None,
        no_show_type="instructor",
        no_show_disputed=False,
        no_show_disputed_at=None,
        no_show_dispute_reason=None,
        no_show_resolution=None,
    )
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service._write_booking_audit = Mock()
    booking_service._invalidate_booking_caches = Mock()
    booking_service._cancel_no_show_report = Mock()

    with patch("app.repositories.payment_repository.PaymentRepository", return_value=payment_repo), patch(
        "app.services.credit_service.CreditService"
    ):
        result = booking_service.resolve_no_show(
            booking_id=booking.id,
            resolution="cancelled",
            resolved_by=None,
        )

    assert result["success"] is True
    booking_service._cancel_no_show_report.assert_called_once_with(booking)


def test_resolve_no_show_default_tier_and_student_fee_fallback(
    booking_service: BookingService, mock_repository: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking = make_booking(payment_status=PaymentStatus.AUTHORIZED.value)
    payment_repo = MagicMock()
    payment_repo.get_payment_by_booking_id.return_value = None
    payment_repo.create_payment_event = Mock()

    mock_repository.get_booking_with_details.side_effect = [booking, booking]
    mock_repository.get_no_show_by_booking_id.return_value = SimpleNamespace(
        no_show_reported_at=datetime.now(timezone.utc) - timedelta(hours=1),
        no_show_resolved_at=None,
        no_show_type="instructor",
        no_show_disputed=False,
        no_show_disputed_at=None,
        no_show_dispute_reason=None,
        no_show_resolution=None,
    )
    booking_service._snapshot_booking = Mock(return_value={})
    booking_service._write_booking_audit = Mock()
    booking_service._invalidate_booking_caches = Mock()
    booking_service._cancel_no_show_report = Mock()

    monkeypatch.setattr(
        "app.services.booking_service.PRICING_DEFAULTS",
        {"instructor_tiers": [], "student_fee_pct": _BadStr()},
    )

    with patch("app.repositories.payment_repository.PaymentRepository", return_value=payment_repo), patch(
        "app.services.credit_service.CreditService"
    ):
        result = booking_service.resolve_no_show(
            booking_id=booking.id,
            resolution="cancelled",
            resolved_by=None,
        )

    assert result["success"] is True
    booking_service._cancel_no_show_report.assert_called_once_with(booking)


def test_mark_video_session_terminal_on_cancellation_backfills_duration(
    booking_service: BookingService,
) -> None:
    started_at = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)
    cancelled_at = datetime(2030, 1, 1, 10, 30, tzinfo=timezone.utc)
    video_session = SimpleNamespace(
        session_started_at=started_at,
        session_ended_at=None,
        session_duration_seconds=None,
    )
    booking = make_booking(
        cancelled_at=cancelled_at,
        video_session=video_session,
    )

    booking_service._mark_video_session_terminal_on_cancellation(booking)

    assert video_session.session_ended_at == cancelled_at
    assert video_session.session_duration_seconds == 5400


def test_disable_video_room_after_cancellation_is_best_effort_on_hundredms_error(
    booking_service: BookingService, caplog: pytest.LogCaptureFixture
) -> None:
    booking = make_booking(
        id="bk_cleanup",
        video_session=SimpleNamespace(room_id="room_cleanup"),
    )
    mock_client = MagicMock()
    mock_client.disable_room.side_effect = HundredMsError("api down", status_code=502)
    booking_service._build_hundredms_client_for_cleanup = MagicMock(return_value=mock_client)

    booking_service._disable_video_room_after_cancellation(booking)

    mock_client.disable_room.assert_called_once_with("room_cleanup")
    assert "Best-effort 100ms room disable failed" in caplog.text


def test_disable_video_room_after_cancellation_no_video_session_is_noop(
    booking_service: BookingService,
) -> None:
    booking = make_booking(video_session=None)
    booking_service._build_hundredms_client_for_cleanup = MagicMock()

    booking_service._disable_video_room_after_cancellation(booking)

    booking_service._build_hundredms_client_for_cleanup.assert_not_called()


def test_disable_video_room_after_cancellation_skips_when_feature_disabled(
    booking_service: BookingService,
) -> None:
    booking = make_booking(video_session=SimpleNamespace(room_id="room_disabled"))
    booking_service._build_hundredms_client_for_cleanup = MagicMock(return_value=None)

    booking_service._disable_video_room_after_cancellation(booking)

    booking_service._build_hundredms_client_for_cleanup.assert_called_once()


def test_build_hundredms_client_for_cleanup_builds_from_settings(
    booking_service: BookingService,
) -> None:
    with patch("app.services.booking_service.settings") as mock_settings:
        mock_settings.hundredms_enabled = True
        mock_settings.hundredms_access_key = "ak_test"
        secret = MagicMock()
        secret.get_secret_value.return_value = "as_test"
        mock_settings.hundredms_app_secret = secret
        mock_settings.hundredms_base_url = "https://api.100ms.live/v2"
        mock_settings.hundredms_template_id = "tmpl_123"

        client = booking_service._build_hundredms_client_for_cleanup()

    assert client is not None
    assert client._access_key == "ak_test"
    assert client._app_secret == "as_test"
    assert client._base_url == "https://api.100ms.live/v2"
    assert client._template_id == "tmpl_123"


def test_build_hundredms_client_for_cleanup_returns_none_when_disabled(
    booking_service: BookingService,
) -> None:
    with patch("app.services.booking_service.settings") as mock_settings:
        mock_settings.hundredms_enabled = False
        mock_settings.hundredms_access_key = "ak_test"
        mock_settings.hundredms_app_secret = "as_test"
        mock_settings.hundredms_template_id = "tmpl_123"

        client = booking_service._build_hundredms_client_for_cleanup()

    assert client is None


def test_build_hundredms_client_for_cleanup_raises_in_prod_when_secret_missing(
    booking_service: BookingService,
) -> None:
    with patch("app.services.booking_service.settings") as mock_settings:
        mock_settings.hundredms_enabled = True
        mock_settings.site_mode = "prod"
        mock_settings.hundredms_access_key = "ak_test"
        mock_settings.hundredms_app_secret = None
        mock_settings.hundredms_base_url = "https://api.100ms.live/v2"
        mock_settings.hundredms_template_id = "tmpl_123"

        with pytest.raises(RuntimeError, match="HUNDREDMS_APP_SECRET is required in production"):
            booking_service._build_hundredms_client_for_cleanup()


def test_build_hundredms_client_for_cleanup_missing_secret_allowed_non_prod(
    booking_service: BookingService,
) -> None:
    with patch("app.services.booking_service.settings") as mock_settings:
        mock_settings.hundredms_enabled = True
        mock_settings.site_mode = "local"
        mock_settings.hundredms_access_key = "ak_test"
        mock_settings.hundredms_app_secret = None
        mock_settings.hundredms_base_url = "https://api.100ms.live/v2"
        mock_settings.hundredms_template_id = "tmpl_123"

        client = booking_service._build_hundredms_client_for_cleanup()

    assert client is None
