"""Shared eager-loading option sets for booking repository queries."""

from __future__ import annotations

from sqlalchemy.orm import joinedload, selectinload

from ...models.booking import Booking


def standard_booking_options() -> tuple[object, ...]:
    """Return the common relationship loading used by booking list/detail queries."""
    return (
        joinedload(Booking.student),
        joinedload(Booking.instructor),
        joinedload(Booking.instructor_service),
        selectinload(Booking.payment_detail),
        selectinload(Booking.no_show_detail),
        selectinload(Booking.lock_detail),
        selectinload(Booking.reschedule_detail),
        selectinload(Booking.dispute),
        selectinload(Booking.transfer),
        selectinload(Booking.video_session),
    )


def detailed_booking_options() -> tuple[object, ...]:
    """Return the standard booking loading plus detail-only relationships."""
    return standard_booking_options() + (
        joinedload(Booking.rescheduled_from),
        joinedload(Booking.cancelled_by),
    )
