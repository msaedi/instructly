from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import RepositoryException
from app.models.booking import BookingStatus
from app.repositories.booking_repository import BookingRepository


def _make_repo() -> tuple[BookingRepository, MagicMock]:
    mock_db = MagicMock()
    repo = BookingRepository.__new__(BookingRepository)
    repo.db = mock_db
    repo.model = MagicMock()
    repo.logger = MagicMock()
    repo.invalidate_entity_cache = MagicMock()
    return repo, mock_db


_SATELLITE_GETTERS = (
    ("get_dispute_by_booking_id", "Failed to get booking dispute"),
    ("get_transfer_by_booking_id", "Failed to get booking transfer"),
    ("get_no_show_by_booking_id", "Failed to get booking no-show"),
    ("get_lock_by_booking_id", "Failed to get booking lock"),
    ("get_reschedule_by_booking_id", "Failed to get booking reschedule"),
    ("get_payment_by_booking_id", "Failed to get booking payment"),
)

_SATELLITE_ENSURE_METHODS = (
    "ensure_dispute",
    "ensure_transfer",
    "ensure_no_show",
    "ensure_lock",
    "ensure_reschedule",
    "ensure_payment",
)

_SATELLITE_RETRY_MESSAGES = (
    ("ensure_dispute", "Failed to ensure booking dispute after retry"),
    ("ensure_transfer", "Failed to ensure booking transfer after retry"),
    ("ensure_no_show", "Failed to ensure booking no-show after retry"),
    ("ensure_lock", "Failed to ensure booking lock after retry"),
    ("ensure_reschedule", "Failed to ensure booking reschedule after retry"),
    ("ensure_payment", "Failed to ensure booking payment after retry"),
)


@pytest.mark.parametrize(("getter_name", "error_message"), _SATELLITE_GETTERS)
def test_satellite_getters_wrap_query_errors(getter_name: str, error_message: str) -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("db unavailable")

    with pytest.raises(RepositoryException, match=error_message):
        getattr(repo, getter_name)("bk_1")


@pytest.mark.parametrize(
    ("getter_name", "ensure_name"),
    (
        ("get_dispute_by_booking_id", "ensure_dispute"),
        ("get_transfer_by_booking_id", "ensure_transfer"),
        ("get_no_show_by_booking_id", "ensure_no_show"),
        ("get_lock_by_booking_id", "ensure_lock"),
        ("get_reschedule_by_booking_id", "ensure_reschedule"),
        ("get_payment_by_booking_id", "ensure_payment"),
    ),
)
def test_ensure_satellite_returns_existing_without_writing(
    getter_name: str, ensure_name: str
) -> None:
    repo, mock_db = _make_repo()
    existing = SimpleNamespace(booking_id="bk_1")
    setattr(repo, getter_name, MagicMock(return_value=existing))

    result = getattr(repo, ensure_name)("bk_1")

    assert result is existing
    mock_db.begin_nested.assert_not_called()
    mock_db.flush.assert_not_called()


@pytest.mark.parametrize("ensure_name", _SATELLITE_ENSURE_METHODS)
def test_ensure_satellite_retries_after_integrity_error(ensure_name: str) -> None:
    repo, mock_db = _make_repo()
    mock_db.query.return_value.filter.return_value.one_or_none.side_effect = [
        None,
        SimpleNamespace(booking_id="bk_1"),
    ]
    nested = MagicMock()
    mock_db.begin_nested.return_value = nested
    mock_db.flush.side_effect = IntegrityError("dup", {}, None)

    result = getattr(repo, ensure_name)("bk_1")

    assert result.booking_id == "bk_1"
    nested.rollback.assert_called_once()


@pytest.mark.parametrize(("ensure_name", "error_message"), _SATELLITE_RETRY_MESSAGES)
def test_ensure_satellite_raises_when_retry_lookup_still_missing(
    ensure_name: str, error_message: str
) -> None:
    repo, mock_db = _make_repo()
    mock_db.query.return_value.filter.return_value.one_or_none.return_value = None
    nested = MagicMock()
    mock_db.begin_nested.return_value = nested
    mock_db.flush.side_effect = IntegrityError("dup", {}, None)

    with pytest.raises(RepositoryException, match=error_message):
        getattr(repo, ensure_name)("bk_1")

    nested.rollback.assert_called_once()


@pytest.mark.parametrize("ensure_name", _SATELLITE_ENSURE_METHODS)
def test_ensure_satellite_rolls_back_and_reraises_non_integrity_error(ensure_name: str) -> None:
    repo, mock_db = _make_repo()
    mock_db.query.return_value.filter.return_value.one_or_none.return_value = None
    nested = MagicMock()
    mock_db.begin_nested.return_value = nested
    mock_db.flush.side_effect = RuntimeError("deadlock")

    with pytest.raises(RuntimeError, match="deadlock"):
        getattr(repo, ensure_name)("bk_1")

    nested.rollback.assert_called_once()


def test_apply_refund_updates_wraps_unexpected_errors() -> None:
    repo, _mock_db = _make_repo()
    repo.ensure_payment = MagicMock(side_effect=RuntimeError("payment relation missing"))
    booking = SimpleNamespace(
        id="bk_1",
        student_id="student_1",
        instructor_id="instructor_1",
        status=BookingStatus.CONFIRMED,
        cancelled_at=None,
        cancellation_reason=None,
        refunded_to_card_amount=None,
        student_credit_amount=None,
        updated_at=None,
    )
    now = datetime.now(timezone.utc)

    with pytest.raises(RepositoryException, match="Failed to apply refund updates"):
        repo.apply_refund_updates(
            booking,
            status=BookingStatus.CANCELLED,
            cancelled_at=now,
            cancellation_reason="admin_refund",
            settlement_outcome="admin_refund",
            refunded_to_card_amount=1000,
            student_credit_amount=0,
            instructor_payout_amount=0,
            updated_at=now,
        )


def test_apply_refund_updates_preserves_existing_settlement_outcome_when_none() -> None:
    repo, mock_db = _make_repo()
    payment = SimpleNamespace(settlement_outcome="existing", instructor_payout_amount=None)
    repo.ensure_payment = MagicMock(return_value=payment)
    booking = SimpleNamespace(
        id="bk_1",
        student_id="student_1",
        instructor_id="instructor_1",
        status=BookingStatus.CONFIRMED,
        cancelled_at=None,
        cancellation_reason=None,
        refunded_to_card_amount=None,
        student_credit_amount=None,
        updated_at=None,
    )
    now = datetime.now(timezone.utc)

    result = repo.apply_refund_updates(
        booking,
        status=BookingStatus.CANCELLED,
        cancelled_at=now,
        cancellation_reason="student_cancelled",
        settlement_outcome=None,
        refunded_to_card_amount=1200,
        student_credit_amount=300,
        instructor_payout_amount=0,
        updated_at=now,
    )

    assert result is booking
    assert payment.settlement_outcome == "existing"
    assert payment.instructor_payout_amount == 0
    mock_db.flush.assert_called_once()
    repo.invalidate_entity_cache.assert_any_call("bk_1")
    repo.invalidate_entity_cache.assert_any_call("student_1")
    repo.invalidate_entity_cache.assert_any_call("instructor_1")


@pytest.mark.parametrize(
    ("method_name", "args", "message"),
    (
        ("get_failed_capture_booking_ids", (), "Failed to get failed capture booking IDs"),
        ("count_student_bookings", ("student_1",), "Failed to count student bookings"),
        ("list_student_refund_bookings", ("student_1",), "Failed to load refund history"),
    ),
)
def test_repository_methods_wrap_database_errors(
    method_name: str, args: tuple[object, ...], message: str
) -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("database offline")

    with pytest.raises(RepositoryException, match=message):
        getattr(repo, method_name)(*args)
