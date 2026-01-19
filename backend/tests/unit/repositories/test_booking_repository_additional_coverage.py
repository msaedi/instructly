"""Additional unit coverage for BookingRepository error branches."""

from __future__ import annotations

from datetime import date, time
from unittest.mock import MagicMock

import pytest

from app.core.enums import RoleName
from app.core.exceptions import NotFoundException, RepositoryException
from app.models.booking import BookingStatus
from app.repositories.booking_repository import BookingRepository


def _make_repo() -> tuple[BookingRepository, MagicMock]:
    mock_db = MagicMock()
    repo = BookingRepository(mock_db)
    repo._cache_enabled = False
    repo._cache_service = None
    return repo, mock_db


def test_find_booking_opportunities_breaks_when_slot_too_short() -> None:
    repo, _ = _make_repo()
    repo.get_bookings_by_time_range = MagicMock(return_value=[])

    opportunities = repo.find_booking_opportunities(
        instructor_id="inst",
        target_date=date(2024, 1, 1),
        available_slots=[{"start_time": time(9, 0), "end_time": time(9, 30)}],
        duration_minutes=60,
    )

    assert opportunities == []


def test_find_booking_opportunities_raises_repository_exception() -> None:
    repo, _ = _make_repo()
    repo.get_bookings_by_time_range = MagicMock(side_effect=RuntimeError("boom"))

    with pytest.raises(RepositoryException):
        repo.find_booking_opportunities(
            instructor_id="inst",
            target_date=date(2024, 1, 1),
            available_slots=[{"start_time": time(9, 0), "end_time": time(12, 0)}],
            duration_minutes=60,
        )


def test_get_student_bookings_exception() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.get_student_bookings(student_id="student-1")


def test_count_bookings_by_status_skips_none_rows() -> None:
    repo, mock_db = _make_repo()
    row_with_none = MagicMock(status=None, count=5)
    row_with_status = MagicMock(status=BookingStatus.COMPLETED.value, count=2)
    query = MagicMock()
    query.filter.return_value.group_by.return_value.all.return_value = [
        row_with_none,
        row_with_status,
    ]
    mock_db.query.return_value = query

    counts = repo.count_bookings_by_status(user_id="user-1", user_role=RoleName.STUDENT)

    assert counts[BookingStatus.COMPLETED.value] == 2


def test_complete_booking_not_found() -> None:
    repo, _ = _make_repo()
    repo.get_by_id = MagicMock(return_value=None)

    with pytest.raises(NotFoundException):
        repo.complete_booking("booking-1")


def test_cancel_booking_not_found() -> None:
    repo, _ = _make_repo()
    repo.get_by_id = MagicMock(return_value=None)

    with pytest.raises(NotFoundException):
        repo.cancel_booking("booking-1", cancelled_by_id="admin")


def test_mark_no_show_not_found() -> None:
    repo, _ = _make_repo()
    repo.get_by_id = MagicMock(return_value=None)

    with pytest.raises(NotFoundException):
        repo.mark_no_show("booking-1")


def test_get_bookings_by_date_and_status_returns_empty_on_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    assert repo.get_bookings_by_date_and_status(date(2024, 1, 1), "CONFIRMED") == []


def test_get_bookings_for_payment_authorization_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.get_bookings_for_payment_authorization()


def test_get_bookings_for_payment_retry_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.get_bookings_for_payment_retry()


def test_get_bookings_for_payment_capture_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.get_bookings_for_payment_capture()


def test_get_bookings_for_auto_completion_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.get_bookings_for_auto_completion()


def test_get_bookings_with_expired_auth_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.get_bookings_with_expired_auth()


def test_count_overdue_authorizations_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.count_overdue_authorizations(date(2024, 1, 1))


def test_count_completed_lessons_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.count_completed_lessons(
            instructor_user_id="inst",
            window_start=MagicMock(),
            window_end=MagicMock(),
        )


def test_count_instructor_total_completed_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.count_instructor_total_completed("inst")


def test_count_student_completed_lifetime_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.count_student_completed_lifetime("student")


def test_get_student_most_recent_completed_at_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.get_student_most_recent_completed_at("student")


def test_filter_owned_booking_ids_returns_empty_on_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    assert repo.filter_owned_booking_ids(["booking-1"], "student") == []


def test_find_upcoming_for_pair_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    with pytest.raises(RepositoryException):
        repo.find_upcoming_for_pair("student", "inst")


def test_batch_find_upcoming_for_pairs_returns_empty_on_error() -> None:
    repo, mock_db = _make_repo()
    mock_db.query.side_effect = RuntimeError("boom")

    pairs = [("student", "inst")]
    assert repo.batch_find_upcoming_for_pairs(pairs, user_id="student") == {pairs[0]: []}
