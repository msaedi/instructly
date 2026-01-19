"""Additional unit coverage for PaymentRepository branches."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import RepositoryException
from app.repositories.payment_repository import PaymentRepository


def _build_query_chain(mock_db: MagicMock) -> MagicMock:
    query = MagicMock()
    mock_db.query.return_value = query
    query.join.return_value = query
    query.options.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.offset.return_value = query
    query.select_from.return_value = query
    query.group_by.return_value = query
    return query


def test_get_instructor_earnings_for_export_skips_missing_booking() -> None:
    mock_db = MagicMock()
    query = _build_query_chain(mock_db)
    payment = MagicMock()
    payment.booking = None
    query.all.return_value = [payment]

    repo = PaymentRepository(mock_db)

    assert repo.get_instructor_earnings_for_export("inst") == []


def test_bulk_create_payment_events_empty_list() -> None:
    repo = PaymentRepository(MagicMock())

    assert repo.bulk_create_payment_events([]) == []


def test_bulk_create_payment_events_error() -> None:
    mock_db = MagicMock()
    mock_db.bulk_save_objects.side_effect = RuntimeError("boom")
    repo = PaymentRepository(mock_db)

    with pytest.raises(RepositoryException):
        repo.bulk_create_payment_events([{"booking_id": "b1", "event_type": "x"}])


def test_list_payment_events_by_types_with_filters() -> None:
    mock_db = MagicMock()
    query = _build_query_chain(mock_db)
    query.all.return_value = []
    repo = PaymentRepository(mock_db)

    result = repo.list_payment_events_by_types(
        ["auth_scheduled"],
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, tzinfo=timezone.utc),
        limit=5,
        offset=2,
        desc=False,
    )

    assert result == []


def test_count_payment_events_by_types_with_filters() -> None:
    mock_db = MagicMock()
    query = _build_query_chain(mock_db)
    query.scalar.return_value = 3
    repo = PaymentRepository(mock_db)

    assert (
        repo.count_payment_events_by_types(
            ["auth_scheduled"],
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
        == 3
    )


def test_sum_application_fee_for_booking_date_range_error() -> None:
    mock_db = MagicMock()
    mock_db.query.side_effect = RuntimeError("boom")
    repo = PaymentRepository(mock_db)

    with pytest.raises(RepositoryException):
        repo.sum_application_fee_for_booking_date_range(date(2024, 1, 1), date(2024, 1, 2))


def test_apply_credits_for_booking_zero_amount() -> None:
    repo = PaymentRepository(MagicMock())

    result = repo.apply_credits_for_booking(user_id="user", booking_id="booking", amount_cents=0)

    assert result == {"applied_cents": 0, "used_credit_ids": [], "remainder_credit_id": None}


def test_apply_credits_for_booking_skips_zero_credit() -> None:
    repo = PaymentRepository(MagicMock())
    credit = SimpleNamespace(id="credit-1", amount_cents=0, source_booking_id=None)
    repo.get_available_credits = MagicMock(return_value=[credit])
    repo.create_payment_event = MagicMock()

    result = repo.apply_credits_for_booking(
        user_id="user",
        booking_id="booking",
        amount_cents=500,
    )

    assert result["applied_cents"] == 0
    repo.create_payment_event.assert_not_called()


def test_get_credits_used_by_booking_handles_invalid_amounts() -> None:
    mock_db = MagicMock()
    repo = PaymentRepository(mock_db)

    credit_bad = SimpleNamespace(id="credit-1", amount_cents="bad")
    credit_zero = SimpleNamespace(id="credit-2", amount_cents=0)

    credit_query = MagicMock()
    credit_query.filter.return_value.all.return_value = [credit_bad, credit_zero]
    event_query = MagicMock()
    event_query.filter.return_value.all.return_value = [
        SimpleNamespace(event_data={"credit_id": "credit-3", "used_cents": "5"})
    ]

    mock_db.query.side_effect = [credit_query, event_query]

    assert repo.get_credits_used_by_booking("booking") == [("credit-3", 5)]
