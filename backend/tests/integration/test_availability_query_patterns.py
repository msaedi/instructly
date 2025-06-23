# backend/tests/integration/test_availability_query_patterns.py
"""
Document all query patterns used in AvailabilityService.

This serves as the specification for the AvailabilityRepository
that will be implemented in the repository pattern.
"""

from datetime import date, time, timedelta

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session, joinedload

from app.models.availability import AvailabilitySlot, BlackoutDate, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.user import User


class TestAvailabilityQueryPatterns:
    """Document every query pattern that needs repository implementation."""

    def test_query_pattern_get_week_availability(self, db: Session, test_instructor_with_availability: User):
        """Document the query for getting a week's availability."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today() - timedelta(days=date.today().weekday())
        end_date = start_date + timedelta(days=6)

        # Document the exact query pattern
        query = (
            db.query(InstructorAvailability)
            .options(joinedload(InstructorAvailability.time_slots))
            .filter(
                and_(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date >= start_date,
                    InstructorAvailability.date <= end_date,
                )
            )
            .order_by(InstructorAvailability.date)
        )

        results = query.all()

        # Repository method signature should be:
        # def get_week_availability(self, instructor_id: int, start_date: date, end_date: date) -> List[InstructorAvailability]

        # Verify query returns expected data
        assert all(r.instructor_id == instructor_id for r in results)
        assert all(start_date <= r.date <= end_date for r in results)

    def test_query_pattern_get_availability_by_date(self, db: Session, test_instructor_with_availability: User):
        """Document query for single date availability."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()

        # Document the query pattern
        query = (
            db.query(InstructorAvailability)
            .options(joinedload(InstructorAvailability.time_slots))
            .filter(
                and_(InstructorAvailability.instructor_id == instructor_id, InstructorAvailability.date == target_date)
            )
        )

        result = query.first()

        # Repository method:
        # def get_availability_by_date(self, instructor_id: int, date: date) -> Optional[InstructorAvailability]

        if result:
            assert result.instructor_id == instructor_id
            assert result.date == target_date

    def test_query_pattern_find_booked_slots_in_range(self, db: Session, test_booking):
        """Document query for finding booked slots in date range."""
        instructor_id = test_booking.instructor_id
        start_date = test_booking.booking_date
        end_date = start_date + timedelta(days=6)

        # Document the complex join query
        query = (
            db.query(Booking)
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
            .filter(
                and_(
                    Booking.instructor_id == instructor_id,
                    Booking.booking_date >= start_date,
                    Booking.booking_date <= end_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
        )

        results = query.all()

        # Repository method:
        # def get_booked_slots_in_range(self, instructor_id: int, start_date: date, end_date: date) -> List[Booking]

        assert len(results) >= 1
        assert all(r.instructor_id == instructor_id for r in results)

    def test_query_pattern_delete_slots_except_booked(self, db: Session, test_instructor_with_availability: User):
        """Document pattern for deleting slots while preserving booked ones."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()

        # First, get booked slot IDs
        booked_slots_query = (
            db.query(AvailabilitySlot.id)
            .join(InstructorAvailability)
            .join(Booking, Booking.availability_slot_id == AvailabilitySlot.id)
            .filter(
                and_(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
            )
        )

        booked_slot_ids = [id[0] for id in booked_slots_query.all()]

        # Then delete query
        delete_query = (
            db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                and_(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
                    ~AvailabilitySlot.id.in_(booked_slot_ids) if booked_slot_ids else True,
                )
            )
        )

        # Repository methods needed:
        # def get_booked_slot_ids(self, instructor_id: int, date: date) -> List[int]
        # def delete_slots_except(self, instructor_id: int, date: date, except_ids: List[int]) -> int

    def test_query_pattern_bulk_create_availability(self, db: Session, test_instructor: User):
        """Document pattern for bulk creating availability records."""
        instructor_id = test_instructor.id
        dates = [date.today() + timedelta(days=i) for i in range(7, 14)]

        # Bulk create pattern
        availability_records = []
        for target_date in dates:
            # Check if exists
            exists = (
                db.query(InstructorAvailability)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                    )
                )
                .first()
            )

            if not exists:
                availability = InstructorAvailability(instructor_id=instructor_id, date=target_date, is_cleared=False)
                availability_records.append(availability)

        # Bulk insert
        if availability_records:
            db.bulk_save_objects(availability_records)
            db.flush()

        # Repository method:
        # def bulk_create_availability(self, instructor_id: int, dates: List[date]) -> List[InstructorAvailability]

    def test_query_pattern_get_blackout_dates(self, db: Session, test_instructor: User):
        """Document blackout date query patterns."""
        instructor_id = test_instructor.id

        # Add test blackout date
        blackout = BlackoutDate(instructor_id=instructor_id, date=date.today() + timedelta(days=30), reason="Vacation")
        db.add(blackout)
        db.commit()

        # Query pattern for future blackout dates
        query = (
            db.query(BlackoutDate)
            .filter(and_(BlackoutDate.instructor_id == instructor_id, BlackoutDate.date >= date.today()))
            .order_by(BlackoutDate.date)
        )

        results = query.all()

        # Repository method:
        # def get_future_blackout_dates(self, instructor_id: int) -> List[BlackoutDate]

        assert len(results) >= 1
        assert all(r.date >= date.today() for r in results)

    def test_query_pattern_check_slot_overlap(self, db: Session, test_instructor_with_availability: User):
        """Document query for checking time slot overlaps."""
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        # Check for overlapping slots
        new_start = time(10, 0)
        new_end = time(12, 0)

        overlap_query = db.query(AvailabilitySlot).filter(
            and_(
                AvailabilitySlot.availability_id == availability.id,
                or_(
                    # New slot starts during existing slot
                    and_(AvailabilitySlot.start_time <= new_start, AvailabilitySlot.end_time > new_start),
                    # New slot ends during existing slot
                    and_(AvailabilitySlot.start_time < new_end, AvailabilitySlot.end_time >= new_end),
                    # New slot completely contains existing slot
                    and_(AvailabilitySlot.start_time >= new_start, AvailabilitySlot.end_time <= new_end),
                ),
            )
        )

        overlap_query.all()

        # Repository method:
        # def find_overlapping_slots(self, availability_id: int, start_time: time, end_time: time) -> List[AvailabilitySlot]

    def test_query_pattern_update_cleared_status(self, db: Session, test_instructor_with_availability: User):
        """Document pattern for updating cleared status."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()

        # Update query
        update_query = db.query(InstructorAvailability).filter(
            and_(InstructorAvailability.instructor_id == instructor_id, InstructorAvailability.date == target_date)
        )

        availability = update_query.first()
        if availability:
            availability.is_cleared = True
            db.flush()

        # Repository method:
        # def update_cleared_status(self, instructor_id: int, date: date, is_cleared: bool) -> bool

    def test_query_pattern_count_slots_in_range(self, db: Session, test_instructor_with_availability: User):
        """Document query for counting slots in date range."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = date.today() + timedelta(days=7)

        # Count query with join
        count_query = (
            db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                and_(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date >= start_date,
                    InstructorAvailability.date <= end_date,
                    InstructorAvailability.is_cleared == False,
                )
            )
        )

        slot_count = count_query.count()

        # Repository method:
        # def count_available_slots(self, instructor_id: int, start_date: date, end_date: date) -> int

        assert slot_count >= 0

    def test_query_pattern_get_availability_summary(self, db: Session, test_instructor_with_availability: User):
        """Document query pattern for availability summary (used in calendar views)."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = date.today() + timedelta(days=30)

        # Raw SQL query for performance (as used in AvailabilityService)
        query = text(
            """
            SELECT
                ia.date,
                COUNT(aslot.id) as slot_count
            FROM instructor_availability ia
            LEFT JOIN availability_slots aslot ON ia.id = aslot.availability_id
            WHERE
                ia.instructor_id = :instructor_id
                AND ia.date BETWEEN :start_date AND :end_date
                AND ia.is_cleared = false
            GROUP BY ia.date
            ORDER BY ia.date
        """
        )

        result = db.execute(
            query,
            {
                "instructor_id": instructor_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )

        summary = {row.date.isoformat(): row.slot_count for row in result}

        # Repository method:
        # def get_availability_summary(self, instructor_id: int, start_date: date, end_date: date) -> Dict[str, int]

        assert isinstance(summary, dict)

    def test_query_pattern_find_conflicts_with_time_range(self, db: Session, test_instructor_with_availability: User):
        """Document query for finding time conflicts with new slots."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        new_start = time(9, 30)
        new_end = time(11, 30)

        # Complex time overlap query
        conflict_query = (
            db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                and_(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date == target_date,
                    or_(
                        # Existing slot overlaps with new slot
                        and_(AvailabilitySlot.start_time < new_end, AvailabilitySlot.end_time > new_start)
                    ),
                )
            )
        )

        conflict_query.all()

        # Repository method:
        # def find_time_conflicts(self, instructor_id: int, date: date, start_time: time, end_time: time) -> List[AvailabilitySlot]

    def test_query_pattern_get_slots_by_availability_id(self, db: Session, test_instructor_with_availability: User):
        """Document query for getting all slots for an availability record."""
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        # Simple slot query
        slots_query = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.availability_id == availability.id)
            .order_by(AvailabilitySlot.start_time)
        )

        slots = slots_query.all()

        # Repository method:
        # def get_slots_by_availability_id(self, availability_id: int) -> List[AvailabilitySlot]

        assert all(slot.availability_id == availability.id for slot in slots)


class TestAvailabilityTransactionPatterns:
    """Document transaction patterns for repository."""

    def test_transaction_pattern_save_week(self, db: Session, test_instructor: User):
        """Document transaction pattern for saving a week."""
        instructor_id = test_instructor.id
        monday = date.today() + timedelta(days=14)

        # Transaction should include:
        # 1. Create/update availability records
        # 2. Delete old slots (except booked)
        # 3. Create new slots
        # 4. All in one transaction

        try:
            # Start transaction (handled by SQLAlchemy session)

            # Step 1: Ensure availability records exist
            for i in range(7):
                target_date = monday + timedelta(days=i)
                availability = (
                    db.query(InstructorAvailability)
                    .filter(
                        and_(
                            InstructorAvailability.instructor_id == instructor_id,
                            InstructorAvailability.date == target_date,
                        )
                    )
                    .first()
                )

                if not availability:
                    availability = InstructorAvailability(
                        instructor_id=instructor_id, date=target_date, is_cleared=False
                    )
                    db.add(availability)

            db.flush()

            # Step 2: Delete existing slots
            # (would check for booked slots first in real implementation)

            # Step 3: Create new slots
            # (would create based on schedule in real implementation)

            # Commit transaction
            db.commit()

        except Exception:
            # Rollback on any error
            db.rollback()
            raise

        # Repository should handle this entire transaction

    def test_transaction_pattern_atomic_slot_creation(self, db: Session, test_instructor: User):
        """Document atomic slot creation pattern."""
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=7)

        # Atomic operation: create availability + slots together
        try:
            # Create availability if not exists
            availability = (
                db.query(InstructorAvailability)
                .filter(
                    and_(
                        InstructorAvailability.instructor_id == instructor_id,
                        InstructorAvailability.date == target_date,
                    )
                )
                .first()
            )

            if not availability:
                availability = InstructorAvailability(instructor_id=instructor_id, date=target_date, is_cleared=False)
                db.add(availability)
                db.flush()

            # Create slots
            slots = [
                AvailabilitySlot(availability_id=availability.id, start_time=time(9, 0), end_time=time(12, 0)),
                AvailabilitySlot(availability_id=availability.id, start_time=time(14, 0), end_time=time(17, 0)),
            ]

            for slot in slots:
                db.add(slot)

            db.commit()

        except Exception:
            db.rollback()
            raise

        # Repository methods:
        # def create_availability_with_slots(self, instructor_id: int, date: date, slots: List[SlotData]) -> InstructorAvailability


class TestAvailabilityComplexQueryPatterns:
    """Document the most complex query patterns that repositories must handle."""

    def test_complex_pattern_week_with_booking_status(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Document query that gets week availability with booking status for each slot."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today() - timedelta(days=date.today().weekday())
        end_date = start_date + timedelta(days=6)

        # Complex query that joins availability, slots, and bookings
        query = (
            db.query(
                InstructorAvailability.date,
                AvailabilitySlot.id.label("slot_id"),
                AvailabilitySlot.start_time,
                AvailabilitySlot.end_time,
                Booking.status.label("booking_status"),
                Booking.id.label("booking_id"),
            )
            .outerjoin(AvailabilitySlot, InstructorAvailability.id == AvailabilitySlot.availability_id)
            .outerjoin(
                Booking,
                and_(
                    AvailabilitySlot.id == Booking.availability_slot_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                ),
            )
            .filter(
                and_(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.date >= start_date,
                    InstructorAvailability.date <= end_date,
                    InstructorAvailability.is_cleared == False,
                )
            )
            .order_by(InstructorAvailability.date, AvailabilitySlot.start_time)
        )

        results = query.all()

        # Repository method:
        # def get_week_with_booking_status(self, instructor_id: int, start_date: date, end_date: date) -> List[WeekSlotWithStatus]

        # Verify we get the expected structure
        for row in results:
            assert hasattr(row, "date")
            assert hasattr(row, "slot_id")
            assert hasattr(row, "start_time")
            assert hasattr(row, "end_time")

    def test_complex_pattern_instructor_stats_query(self, db: Session, test_instructor_with_availability: User):
        """Document complex aggregation query for instructor statistics."""
        instructor_id = test_instructor_with_availability.id

        # Stats query with multiple aggregations
        stats_query = (
            db.query(
                func.count(AvailabilitySlot.id).label("total_slots"),
                func.count(Booking.id).label("booked_slots"),
                func.min(InstructorAvailability.date).label("earliest_availability"),
                func.max(InstructorAvailability.date).label("latest_availability"),
            )
            .select_from(InstructorAvailability)
            .outerjoin(AvailabilitySlot, InstructorAvailability.id == AvailabilitySlot.availability_id)
            .outerjoin(
                Booking,
                and_(
                    AvailabilitySlot.id == Booking.availability_slot_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                ),
            )
            .filter(
                and_(
                    InstructorAvailability.instructor_id == instructor_id,
                    InstructorAvailability.is_cleared == False,
                    InstructorAvailability.date >= date.today(),
                )
            )
        )

        stats = stats_query.first()

        # Repository method:
        # def get_instructor_availability_stats(self, instructor_id: int) -> AvailabilityStats

        assert hasattr(stats, "total_slots")
        assert hasattr(stats, "booked_slots")
