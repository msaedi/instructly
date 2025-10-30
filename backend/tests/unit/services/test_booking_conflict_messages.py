from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.services.booking_service import (
    GENERIC_CONFLICT_MESSAGE,
    INSTRUCTOR_CONFLICT_MESSAGE,
    STUDENT_CONFLICT_MESSAGE,
    BookingService,
)


class _FakeDiag:
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


class _FakeOrig:
    def __init__(self, constraint_name: Optional[str], text: str = "") -> None:
        self.diag = _FakeDiag(constraint_name) if constraint_name else None
        self._text = text

    def __str__(self) -> str:
        return self._text


def _make_error(constraint: Optional[str], text: str = "") -> IntegrityError:
    return IntegrityError("stmt", params=None, orig=_FakeOrig(constraint, text=text))


def test_resolve_integrity_conflict_instructor() -> None:
    service = BookingService.__new__(BookingService)
    message, scope = service._resolve_integrity_conflict_message(  # type: ignore[attr-defined]
        _make_error("bookings_no_overlap_per_instructor")
    )
    assert message == INSTRUCTOR_CONFLICT_MESSAGE
    assert scope == "instructor"


def test_resolve_integrity_conflict_student() -> None:
    service = BookingService.__new__(BookingService)
    message, scope = service._resolve_integrity_conflict_message(  # type: ignore[attr-defined]
        _make_error("bookings_no_overlap_per_student")
    )
    assert message == STUDENT_CONFLICT_MESSAGE
    assert scope == "student"


def test_resolve_integrity_conflict_via_text_fallback() -> None:
    service = BookingService.__new__(BookingService)
    error = _make_error(
        None,
        text="violates constraint bookings_no_overlap_per_instructor on table bookings",
    )
    message, scope = service._resolve_integrity_conflict_message(  # type: ignore[attr-defined]
        error
    )
    assert message == INSTRUCTOR_CONFLICT_MESSAGE
    assert scope == "instructor"


def test_resolve_integrity_conflict_generic_message() -> None:
    service = BookingService.__new__(BookingService)
    message, scope = service._resolve_integrity_conflict_message(  # type: ignore[attr-defined]
        _make_error(None, text="some other constraint")
    )
    assert message == GENERIC_CONFLICT_MESSAGE
    assert scope is None
