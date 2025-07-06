# backend/tests/integration/test_bulk_operation_query_patterns.py
"""
Query pattern tests for BulkOperationService.
Documents all database queries that will become repository methods.

UPDATED FOR WORK STREAM #10: Single-table availability design.
FIXED: Updated for Work Stream #9 - Removed availability_slot relationship access.
"""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.user import User


class TestBulkOperationQueryPatterns:
    """Document query patterns that will become BulkOperationRepository methods."""

    def test_query_slots_by_ids(self, db: Session, test_instructor_with_availability: User):
        """
        Repository method: get_slots_by_ids(slot_ids: List[int])
        Used for remove operations to look up slot dates for cache invalidation.
        """
        # Get some slot IDs
        slots = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.instructor_id == test_instructor_with_availability.id)
            .limit(3)
            .all()
        )
        slot_ids = [s.id for s in slots]

        # Document the query pattern - FIXED: No join needed in single-table design
        result = (
            db.query(AvailabilitySlot.id, AvailabilitySlot.date, AvailabilitySlot.start_time, AvailabilitySlot.end_time)
            .filter(AvailabilitySlot.id.in_(slot_ids))
            .all()
        )

        assert len(result) == len(slot_ids)
        for row in result:
            assert row.id in slot_ids
            assert isinstance(row.date, date)

    def test_query_slots_for_date(self, db: Session, test_instructor_with_availability: User):
        """
        Repository method: get_slots_by_date(instructor_id: int, date: date)
        Used for date-based operations.
        """
        target_date = date.today() + timedelta(days=1)

        # Document the query pattern - FIXED: Direct query without join
        slots = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.date == target_date,
            )
            .all()
        )

        assert all(slot.instructor_id == test_instructor_with_availability.id for slot in slots)
        assert all(slot.date == target_date for slot in slots)

    def test_query_slots_with_bookings_for_date(self, db: Session, test_booking: Booking):
        """
        Repository method: has_bookings_on_date(instructor_id: int, date: date)
        Used to check if date has bookings.
        """
        # FIXED: Direct query by instructor and date
        booking_date = test_booking.booking_date
        instructor_id = test_booking.instructor_id

        # Document the query pattern - check if any bookings exist on this date
        count = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == booking_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .count()
        )

        assert count > 0

    def test_query_week_slots_for_validation(self, db: Session, test_instructor_with_availability: User):
        """
        Repository method: get_week_slots(instructor_id: int, week_start: date, week_end: date)
        Used for week validation to get existing slots.
        """
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_end = week_start + timedelta(days=6)

        # Document the query pattern - FIXED: No join needed
        slots = (
            db.query(AvailabilitySlot.id, AvailabilitySlot.date, AvailabilitySlot.start_time, AvailabilitySlot.end_time)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.date >= week_start,
                AvailabilitySlot.date <= week_end,
            )
            .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
            .all()
        )

        assert len(slots) > 0
        for slot in slots:
            assert week_start <= slot.date <= week_end

    def test_query_slot_with_instructor_check(self, db: Session, test_instructor_with_availability: User):
        """
        Repository method: get_slot_for_instructor(slot_id: int, instructor_id: int)
        Used for update/remove operations to verify ownership.
        """
        # Get a slot
        slot = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        # Document the query pattern - FIXED: Direct query without join
        result = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.id == slot.id,
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
            )
            .first()
        )

        assert result is not None
        assert result.id == slot.id

    def test_query_slot_booking_status(self, db: Session, test_booking: Booking):
        """
        Repository method: slot_has_active_booking(slot_id: int)
        Used to check if slot can be removed/updated.
        """
        slot_id = test_booking.availability_slot_id

        # Document the query pattern
        booking = (
            db.query(Booking)
            .filter(
                Booking.availability_slot_id == slot_id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .first()
        )

        assert booking is not None
        assert booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

    def test_query_remaining_slots_count(self, db: Session, test_instructor_with_availability: User):
        """
        Repository method: count_slots_for_date(instructor_id: int, date: date)
        Used to check if there are slots on a date.
        """
        # Get a date with slots
        slot = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.instructor_id == test_instructor_with_availability.id)
            .first()
        )
        target_date = slot.date

        # Document the query pattern - FIXED: Direct count without join
        count = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.date == target_date,
            )
            .count()
        )

        assert count >= 1

    def test_query_affected_dates_for_cache(self, db: Session, test_instructor_with_availability: User):
        """
        Repository method: get_unique_dates_from_operations(instructor_id: int, operation_dates: List[date])
        Used to determine which cache entries to invalidate.
        """
        # Get some dates
        slots = (
            db.query(AvailabilitySlot.date)
            .filter(AvailabilitySlot.instructor_id == test_instructor_with_availability.id)
            .distinct()
            .limit(3)
            .all()
        )
        dates = [s.date for s in slots]

        # Document the query pattern
        result = (
            db.query(AvailabilitySlot.date)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.date.in_(dates),
            )
            .distinct()
            .all()
        )

        assert len(result) == len(dates)

    def test_query_duplicate_slot_check(self, db: Session, test_instructor_with_availability: User):
        """
        Repository method: slot_exists(instructor_id: int, date: date, start_time: time, end_time: time)
        Used to prevent duplicate slots.
        """
        # Get an existing slot
        slot = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        # Document the query pattern - FIXED: Check by instructor_id and date
        exists = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == slot.instructor_id,
                AvailabilitySlot.date == slot.date,
                AvailabilitySlot.start_time == slot.start_time,
                AvailabilitySlot.end_time == slot.end_time,
            )
            .first()
        ) is not None

        assert exists is True

    def test_query_instructor_profile_for_validation(self, db: Session, test_instructor: User):
        """
        Repository method: get_instructor_profile(instructor_id: int)
        Used for various validation checks.
        """
        # Document the query pattern
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        assert profile is not None
        assert profile.user_id == test_instructor.id

    def test_batch_create_slots(self, db: Session, test_instructor: User):
        """
        Repository method: bulk_create_slots(slots: List[Dict])
        Used for efficient bulk insertion.
        """
        # Document batch insert pattern - FIXED: Create slots directly
        new_slots = [
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                date=date.today() + timedelta(days=10),
                start_time=time(10, 0),
                end_time=time(11, 0),
            ),
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                date=date.today() + timedelta(days=10),
                start_time=time(11, 0),
                end_time=time(12, 0),
            ),
        ]

        db.bulk_save_objects(new_slots)
        db.flush()

        # Verify
        count = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor.id,
                AvailabilitySlot.date == date.today() + timedelta(days=10),
            )
            .count()
        )
        assert count >= 2

    def test_transaction_rollback_pattern(self, db: Session, test_instructor: User):
        """
        Repository method: Should support transaction context manager
        Used for all-or-nothing bulk operations.
        """
        # Document transaction pattern - use a valid instructor
        with db.begin_nested():  # Savepoint for testing
            # Simulate operations with a valid instructor
            slot = AvailabilitySlot(
                instructor_id=test_instructor.id,
                date=date.today() + timedelta(days=20),
                start_time=time(9, 0),
                end_time=time(10, 0),
            )
            db.add(slot)
            db.flush()

            # Rollback
            db.rollback()

        # Verify rollback worked
        count = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor.id,
                AvailabilitySlot.date == date.today() + timedelta(days=20),
            )
            .count()
        )
        assert count == 0
