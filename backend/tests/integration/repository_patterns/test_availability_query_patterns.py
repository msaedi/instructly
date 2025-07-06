# backend/tests/integration/test_availability_query_patterns.py
"""
Document all query patterns used in AvailabilityService.

UPDATED FOR WORK STREAM #10: Single-table availability design.
All queries now work directly with AvailabilitySlot without InstructorAvailability.

This serves as the specification for the AvailabilityRepository
that will be implemented in the repository pattern.
"""

from datetime import date, time, timedelta

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.availability import AvailabilitySlot, BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.user import User


class TestAvailabilityQueryPatterns:
    """Document every query pattern that needs repository implementation."""

    def test_query_pattern_get_week_availability(self, db: Session, test_instructor_with_availability: User):
        """Document the query for getting a week's availability."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today() - timedelta(days=date.today().weekday())
        end_date = start_date + timedelta(days=6)

        # Document the exact query pattern - UPDATED for single table
        query = (
            db.query(AvailabilitySlot)
            .filter(
                and_(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date >= start_date,
                    AvailabilitySlot.date <= end_date,
                )
            )
            .order_by(AvailabilitySlot.date, AvailabilitySlot.start_time)
        )

        results = query.all()

        # Repository method signature should be:
        # def get_week_availability(self, instructor_id: int, start_date: date, end_date: date) -> List[AvailabilitySlot]

        # Verify query returns expected data
        assert all(r.instructor_id == instructor_id for r in results)
        assert all(start_date <= r.date <= end_date for r in results)

    def test_query_pattern_get_slots_by_date(self, db: Session, test_instructor_with_availability: User):
        """Document query for single date slots."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()

        # Document the query pattern - UPDATED for single table
        query = (
            db.query(AvailabilitySlot)
            .filter(and_(AvailabilitySlot.instructor_id == instructor_id, AvailabilitySlot.date == target_date))
            .order_by(AvailabilitySlot.start_time)
        )

        results = query.all()

        # Repository method:
        # def get_slots_by_date(self, instructor_id: int, date: date) -> List[AvailabilitySlot]

        for result in results:
            assert result.instructor_id == instructor_id
            assert result.date == target_date

    def test_query_pattern_find_booked_slots_in_range(self, db: Session, test_booking):
        """Document query for finding booked slots in date range."""
        instructor_id = test_booking.instructor_id
        start_date = test_booking.booking_date
        end_date = start_date + timedelta(days=6)

        # Document the simplified join query - UPDATED for single table
        query = db.query(Booking).filter(
            and_(
                Booking.instructor_id == instructor_id,
                Booking.booking_date >= start_date,
                Booking.booking_date <= end_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
        )

        results = query.all()

        # Repository method:
        # def get_booked_slots_in_range(self, instructor_id: int, start_date: date, end_date: date) -> List[Booking]

        assert len(results) >= 1

    def test_query_pattern_get_booked_slot_ids(self, db: Session, test_booking):
        """Document query for getting booked slot IDs for a specific date."""
        instructor_id = test_booking.instructor_id
        target_date = test_booking.booking_date

        # Simplified query - no complex joins needed
        query = db.query(Booking.availability_slot_id).filter(
            and_(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                Booking.availability_slot_id.isnot(None),
            )
        )

        slot_ids = [row[0] for row in query.all()]

        # Repository method:
        # def get_booked_slot_ids(self, instructor_id: int, date: date) -> List[int]

        assert len(slot_ids) >= 1

    def test_query_pattern_count_bookings_for_date(self, db: Session, test_booking):
        """Document query for counting bookings on a date."""
        instructor_id = test_booking.instructor_id
        target_date = test_booking.booking_date

        # Direct count query
        count = (
            db.query(func.count(Booking.id))
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date == target_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
            .scalar()
        )

        # Repository method:
        # def count_bookings_for_date(self, instructor_id: int, date: date) -> int

        assert count >= 1

    def test_query_pattern_get_availability_slot_with_details(self, db: Session, test_booking):
        """Document query for getting a slot with details."""
        slot_id = test_booking.availability_slot_id

        # Simple query with relationship loading
        query = (
            db.query(AvailabilitySlot)
            .options(joinedload(AvailabilitySlot.instructor))
            .filter(AvailabilitySlot.id == slot_id)
        )

        result = query.first()

        # Repository method:
        # def get_availability_slot_with_details(self, slot_id: int) -> Optional[AvailabilitySlot]

        assert result is not None
        assert result.id == slot_id

    def test_query_pattern_slot_exists(self, db: Session, test_instructor_with_availability: User):
        """Document query for checking if a slot exists."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        start_time = time(9, 0)
        end_time = time(10, 0)

        # Direct existence check - UPDATED for single table
        exists = (
            db.query(AvailabilitySlot)
            .filter(
                and_(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                    AvailabilitySlot.start_time == start_time,
                    AvailabilitySlot.end_time == end_time,
                )
            )
            .first()
            is not None
        )

        # Repository method:
        # def slot_exists(self, instructor_id: int, date: date, start_time: time, end_time: time) -> bool

        assert isinstance(exists, bool)

    def test_query_pattern_find_overlapping_slots(self, db: Session, test_instructor_with_availability: User):
        """Document query for finding overlapping slots."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        check_start = time(10, 0)
        check_end = time(11, 0)

        # Find overlapping slots - UPDATED for single table
        query = db.query(AvailabilitySlot).filter(
            and_(
                AvailabilitySlot.instructor_id == instructor_id,
                AvailabilitySlot.date == target_date,
                or_(
                    # Slot starts within check range
                    and_(
                        AvailabilitySlot.start_time >= check_start,
                        AvailabilitySlot.start_time < check_end,
                    ),
                    # Slot ends within check range
                    and_(
                        AvailabilitySlot.end_time > check_start,
                        AvailabilitySlot.end_time <= check_end,
                    ),
                    # Slot contains check range
                    and_(
                        AvailabilitySlot.start_time <= check_start,
                        AvailabilitySlot.end_time >= check_end,
                    ),
                ),
            )
        )

        results = query.all()

        # Repository method:
        # def find_overlapping_slots(self, instructor_id: int, date: date, start_time: time, end_time: time) -> List[AvailabilitySlot]

        # Verify overlap logic
        for slot in results:
            assert slot.instructor_id == instructor_id
            assert slot.date == target_date

    def test_query_pattern_delete_slots_except(self, db: Session, test_instructor_with_availability: User):
        """Document pattern for deleting slots except specified IDs."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        except_ids = [1, 2, 3]  # Example IDs to keep

        # Document delete pattern - UPDATED for single table
        delete_count = (
            db.query(AvailabilitySlot)
            .filter(
                and_(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                    ~AvailabilitySlot.id.in_(except_ids),
                )
            )
            .delete(synchronize_session=False)
        )

        # Repository method:
        # def delete_slots_except(self, instructor_id: int, date: date, except_ids: List[int]) -> int

        assert isinstance(delete_count, int)

    def test_query_pattern_bulk_create_slots(self, db: Session, test_instructor_with_availability: User):
        """Document pattern for bulk creating slots."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today() + timedelta(days=7)

        # Create multiple slot objects
        slots = [
            AvailabilitySlot(
                instructor_id=instructor_id,
                date=target_date,
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
            AvailabilitySlot(
                instructor_id=instructor_id,
                date=target_date,
                start_time=time(10, 0),
                end_time=time(11, 0),
            ),
        ]

        # Bulk insert pattern
        db.bulk_save_objects(slots)
        db.flush()

        # Repository method:
        # def bulk_create_slots(self, instructor_id: int, slots_data: List[Dict]) -> List[AvailabilitySlot]

        # Verify slots were created
        created_count = (
            db.query(func.count(AvailabilitySlot.id))
            .filter(
                and_(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                )
            )
            .scalar()
        )
        assert created_count >= 2

    def test_query_pattern_count_available_slots(self, db: Session, test_instructor_with_availability: User):
        """Document query for counting available slots in a range."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = start_date + timedelta(days=6)

        # Count query - UPDATED for single table
        count = (
            db.query(func.count(AvailabilitySlot.id))
            .filter(
                and_(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date >= start_date,
                    AvailabilitySlot.date <= end_date,
                )
            )
            .scalar()
        )

        # Repository method:
        # def count_available_slots(self, instructor_id: int, start_date: date, end_date: date) -> int

        assert count > 0

    def test_query_pattern_get_availability_summary(self, db: Session, test_instructor_with_availability: User):
        """Document query for getting availability summary."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = start_date + timedelta(days=6)

        # Summary query - UPDATED for single table
        query = db.query(
            func.count(AvailabilitySlot.id).label("total_slots"),
            func.count(func.distinct(AvailabilitySlot.date)).label("available_days"),
        ).filter(
            and_(
                AvailabilitySlot.instructor_id == instructor_id,
                AvailabilitySlot.date >= start_date,
                AvailabilitySlot.date <= end_date,
            )
        )

        result = query.first()

        # Repository method:
        # def get_availability_summary(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, int]

        assert result.total_slots > 0
        assert result.available_days > 0

    def test_query_pattern_get_blackout_dates(self, db: Session, test_instructor_with_availability: User):
        """Document query for getting blackout dates."""
        instructor_id = test_instructor_with_availability.id

        # Simple blackout query
        query = (
            db.query(BlackoutDate)
            .filter(
                and_(
                    BlackoutDate.instructor_id == instructor_id,
                    BlackoutDate.date >= date.today(),
                )
            )
            .order_by(BlackoutDate.date)
        )

        results = query.all()

        # Repository method:
        # def get_future_blackout_dates(self, instructor_id: int) -> List[BlackoutDate]

        # Verify all are future dates
        for blackout in results:
            assert blackout.instructor_id == instructor_id
            assert blackout.date >= date.today()

    def test_query_pattern_create_blackout_date(self, db: Session, test_instructor: User):
        """Document pattern for creating blackout date."""
        instructor_id = test_instructor.id
        blackout_date = date.today() + timedelta(days=14)
        reason = "Vacation"

        # Create blackout
        blackout = BlackoutDate(
            instructor_id=instructor_id,
            date=blackout_date,
            reason=reason,
        )
        db.add(blackout)
        db.flush()

        # Repository method:
        # def create_blackout_date(self, instructor_id: int, date: date, reason: Optional[str]) -> BlackoutDate

        assert blackout.id is not None
        assert blackout.instructor_id == instructor_id

    def test_query_pattern_delete_blackout_date(self, db: Session):
        """Document pattern for deleting blackout date."""
        blackout_id = 1
        instructor_id = 1

        # Delete with instructor check
        deleted = (
            db.query(BlackoutDate)
            .filter(
                and_(
                    BlackoutDate.id == blackout_id,
                    BlackoutDate.instructor_id == instructor_id,
                )
            )
            .delete()
        )

        # Repository method:
        # def delete_blackout_date(self, blackout_id: int, instructor_id: int) -> bool

        assert isinstance(deleted, int)

    def test_query_pattern_find_time_conflicts(self, db: Session, test_instructor_with_availability: User):
        """Document query for finding time conflicts."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        start_time = time(9, 30)
        end_time = time(10, 30)

        # Find conflicting slots - both availability and bookings
        # First, find overlapping availability slots
        availability_conflicts = (
            db.query(AvailabilitySlot)
            .filter(
                and_(
                    AvailabilitySlot.instructor_id == instructor_id,
                    AvailabilitySlot.date == target_date,
                    or_(
                        # Check for any overlap
                        and_(
                            AvailabilitySlot.start_time < end_time,
                            AvailabilitySlot.end_time > start_time,
                        )
                    ),
                )
            )
            .all()
        )

        # Repository method:
        # def find_time_conflicts(self, instructor_id: int, date: date, start_time: time, end_time: time) -> List[AvailabilitySlot]

        # Verify conflict detection
        assert isinstance(availability_conflicts, list)

    def test_query_pattern_create_slot_atomic(self, db: Session, test_instructor: User):
        """Document atomic slot creation pattern."""
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=10)

        # Create slot directly - single table design
        slot = AvailabilitySlot(
            instructor_id=instructor_id,
            date=target_date,
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        db.add(slot)
        db.flush()

        # Repository method:
        # def create_slot(self, instructor_id: int, date: date, start_time: time, end_time: time) -> AvailabilitySlot

        assert slot.id is not None
        assert slot.instructor_id == instructor_id
        assert slot.date == target_date
