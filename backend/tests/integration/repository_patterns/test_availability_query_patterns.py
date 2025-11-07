# backend/tests/integration/repository_patterns/test_availability_query_patterns.py
"""
Document all query patterns used in AvailabilityService.

UPDATED FOR WORK STREAM #10: Bitmap-only availability design.
AvailabilitySlot model removed - bitmap storage in AvailabilityDay.

UPDATED FOR WORK STREAM #9: Layer independence.
Booking no longer has availability_slot_id attribute.

This serves as the specification for the AvailabilityRepository
that will be implemented in the repository pattern.
"""

from datetime import date, time, timedelta

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.availability import BlackoutDate
from app.models.availability_day import AvailabilityDay
from app.models.booking import Booking, BookingStatus
from app.models.user import User
from app.utils.bitset import windows_from_bits


class TestAvailabilityQueryPatterns:
    """Document every query pattern that needs repository implementation."""

    def test_query_pattern_get_week_availability(self, db: Session, test_instructor_with_availability: User):
        """Document the query for getting a week's availability (bitmap)."""
        instructor_id = test_instructor_with_availability.id
        # Monday of this week
        start_date = date.today() - timedelta(days=date.today().weekday())
        end_date = start_date + timedelta(days=6)

        # Bitmap-era: query AvailabilityDay rows for the week
        rows = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date >= start_date,
                AvailabilityDay.day_date <= end_date,
            )
            .order_by(AvailabilityDay.day_date)
            .all()
        )

        # Optional: convert bits to windows for assertions similar to slot rows
        windows_by_day = {r.day_date: windows_from_bits(r.bits or b"") for r in rows}

        # Repository method signature should be:
        # def get_week_availability(self, instructor_id: str, start_date: date, end_date: date) -> Dict[date, bytes]
        # Or via service: -> Dict[str, List[Dict[str, str]]] (windows)

        # Verify row-level invariants (replacing slot-era fields)
        assert all(r.instructor_id == instructor_id for r in rows)
        assert all(start_date <= r.day_date <= end_date for r in rows)

        # If the original test asserted time ranges, check windows too
        for d, wins in windows_by_day.items():
            # wins is a list of ('HH:MM:SS','HH:MM:SS') tuples
            for start_str, end_str in wins:
                assert len(start_str) == 8 and len(end_str) == 8  # 'HH:MM:SS'

    def test_query_pattern_get_slots_by_date(self, db: Session, test_instructor_with_availability: User):
        """Document query for single date availability (bitmap)."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()

        # Bitmap-era: query AvailabilityDay for the specific date
        row = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == target_date,
            )
            .first()
        )

        # Repository method:
        # def get_day_bits(self, instructor_id: str, date: date) -> Optional[bytes]
        # Or via service: -> List[Dict[str, str]] (windows)

        if row:
            assert row.instructor_id == instructor_id
            assert row.day_date == target_date
            # Convert bits to windows for time-based assertions
            windows = windows_from_bits(row.bits or b"")
            # Windows are sorted by start time
            for start_str, end_str in windows:
                assert len(start_str) == 8 and len(end_str) == 8  # 'HH:MM:SS'

    def test_query_pattern_get_booked_slots_in_range(self, db: Session, test_booking):
        """Document query for finding booked slots in date range."""
        instructor_id = test_booking.instructor_id
        start_date = test_booking.booking_date
        end_date = start_date + timedelta(days=6)

        # Document the simplified query - bookings are now time-based
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
        """Document query for getting booked time ranges for a specific date."""
        instructor_id = test_booking.instructor_id
        target_date = test_booking.booking_date

        # Per Work Stream #9, bookings don't have slot IDs - query by time instead
        query = db.query(Booking.start_time, Booking.end_time).filter(
            and_(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
        )

        time_ranges = query.all()

        # Repository method:
        # def get_booked_time_ranges(self, instructor_id: int, date: date) -> List[Tuple[time, time]]

        assert len(time_ranges) >= 1

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

    def test_query_pattern_get_availability_day_with_details(
        self, db: Session, test_instructor_with_availability: User
    ):
        """Document query for getting an availability day with details (bitmap)."""
        # Get a real availability day first
        day_row = (
            db.query(AvailabilityDay)
            .filter(AvailabilityDay.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if day_row:
            day_date = day_row.day_date
            instructor_id = day_row.instructor_id

            # Query with instructor relationship (if needed)
            result = (
                db.query(AvailabilityDay)
                .filter(
                    AvailabilityDay.instructor_id == instructor_id,
                    AvailabilityDay.day_date == day_date,
                )
                .first()
            )

            # Repository method:
            # def get_day_bits(self, instructor_id: str, date: date) -> Optional[bytes]

            assert result is not None
            assert result.day_date == day_date
            assert result.instructor_id == instructor_id

    def test_query_pattern_window_exists(self, db: Session, test_instructor_with_availability: User):
        """Document query for checking if a window exists (bitmap)."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        start_time = time(9, 0)
        end_time = time(10, 0)

        # Bitmap-era: check if day exists and window is in bits
        day_row = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == target_date,
            )
            .first()
        )

        exists = False
        if day_row and day_row.bits:
            windows = windows_from_bits(day_row.bits)
            start_str = start_time.strftime("%H:%M:%S")
            end_str = end_time.strftime("%H:%M:%S")
            exists = (start_str, end_str) in windows

        # Repository method:
        # def window_exists(self, instructor_id: str, date: date, start_time: time, end_time: time) -> bool
        # Or use AvailabilityService.get_week_availability and check windows

        assert isinstance(exists, bool)

    def test_query_pattern_find_overlapping_windows(self, db: Session, test_instructor_with_availability: User):
        """Document query for finding overlapping windows (bitmap)."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        check_start = time(10, 0)
        check_end = time(11, 0)

        # Bitmap-era: get day row and check windows for overlap
        day_row = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == target_date,
            )
            .first()
        )

        overlapping_windows = []
        if day_row and day_row.bits:
            windows = windows_from_bits(day_row.bits)
            check_start_str = check_start.strftime("%H:%M:%S")
            check_end_str = check_end.strftime("%H:%M:%S")

            for win_start_str, win_end_str in windows:
                # Check for overlap
                if (
                    (win_start_str < check_end_str and win_end_str > check_start_str)
                ):
                    overlapping_windows.append((win_start_str, win_end_str))

        # Repository method:
        # def find_overlapping_windows(self, instructor_id: str, date: date, start_time: time, end_time: time) -> List[Tuple[str, str]]
        # Or use AvailabilityService.get_week_availability and filter windows

        # Verify all windows are on the target date
        assert all(
            day_row.instructor_id == instructor_id and day_row.day_date == target_date
            for _ in overlapping_windows
        ) if day_row else True

    def test_query_pattern_delete_day(self, db: Session, test_instructor_with_availability: User):
        """Document pattern for deleting availability day (bitmap).

        Note: In bitmap world, we delete entire days, not individual windows.
        To remove specific windows, use AvailabilityService.save_week_bits with updated bits.
        """
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()

        # Bitmap-era: delete the entire day row
        delete_count = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == target_date,
            )
            .delete(synchronize_session=False)
        )

        # Repository method:
        # def delete_day(self, instructor_id: str, date: date) -> int

        assert isinstance(delete_count, int)

    def test_query_pattern_bulk_create_windows(self, db: Session, test_instructor_with_availability: User):
        """Document pattern for bulk creating windows (bitmap).

        In bitmap world, use AvailabilityService.save_week_bits to create/update windows.
        """
        from app.utils.bitset import bits_from_windows

        instructor_id = test_instructor_with_availability.id
        target_date = date.today() + timedelta(days=7)

        # Bitmap-era: create windows via service
        # Use non-adjacent windows to ensure they don't merge
        windows = [
            (time(9, 0).strftime("%H:%M:%S"), time(10, 0).strftime("%H:%M:%S")),
            (time(14, 0).strftime("%H:%M:%S"), time(15, 0).strftime("%H:%M:%S")),
        ]
        bits = bits_from_windows(windows)

        # Create or update the day row
        day_row = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == target_date,
            )
            .first()
        )

        if day_row:
            day_row.bits = bits
        else:
            day_row = AvailabilityDay(
                instructor_id=instructor_id,
                day_date=target_date,
                bits=bits,
            )
            db.add(day_row)

        db.flush()

        # Repository method:
        # def save_day_bits(self, instructor_id: str, date: date, bits: bytes) -> None
        # Or use AvailabilityService.save_week_bits for week-level operations

        # Verify day was created/updated
        created_day = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == target_date,
            )
            .first()
        )
        assert created_day is not None
        assert len(windows_from_bits(created_day.bits or b"")) >= 2

    def test_query_pattern_count_available_days(self, db: Session, test_instructor_with_availability: User):
        """Document query for counting available days in a range (bitmap)."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = start_date + timedelta(days=6)

        # Bitmap-era: count days with availability
        count = (
            db.query(func.count(AvailabilityDay.day_date))
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date >= start_date,
                AvailabilityDay.day_date <= end_date,
            )
            .scalar()
        )

        # Repository method:
        # def count_available_days(self, instructor_id: str, start_date: date, end_date: date) -> int
        # For window counts, use AvailabilityService.get_week_availability and count windows

        assert isinstance(count, int)

    def test_query_pattern_get_availability_summary(self, db: Session, test_instructor_with_availability: User):
        """Document query for getting availability summary (bitmap)."""
        from app.services.availability_service import AvailabilityService

        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = start_date + timedelta(days=6)
        week_start = start_date - timedelta(days=start_date.weekday())

        # Bitmap-era: get summary via service or count days
        available_days_count = (
            db.query(func.count(func.distinct(AvailabilityDay.day_date)))
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date >= start_date,
                AvailabilityDay.day_date <= end_date,
            )
            .scalar()
        )

        # For window counts, use service
        svc = AvailabilityService(db=db)
        week_map = svc.get_week_availability(instructor_id, week_start, use_cache=False)
        total_windows = sum(len(windows) for windows in week_map.values())

        # Repository method:
        # def get_availability_summary(self, instructor_id: str, start_date: date, end_date: date) -> Dict[str, int]
        # Returns: {"available_days": int, "total_windows": int}

        assert available_days_count >= 0
        assert total_windows >= 0

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
        blackout_id = generate_ulid()
        instructor_id = generate_ulid()

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
        """Document query for finding time conflicts (bitmap)."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        start_time = time(9, 30)
        end_time = time(10, 30)

        # Bitmap-era: get day row and check windows for overlap
        day_row = (
            db.query(AvailabilityDay)
            .filter(
                AvailabilityDay.instructor_id == instructor_id,
                AvailabilityDay.day_date == target_date,
            )
            .first()
        )

        availability_conflicts = []
        if day_row and day_row.bits:
            windows = windows_from_bits(day_row.bits)
            start_str = start_time.strftime("%H:%M:%S")
            end_str = end_time.strftime("%H:%M:%S")

            for win_start_str, win_end_str in windows:
                # Check for overlap
                if win_start_str < end_str and win_end_str > start_str:
                    availability_conflicts.append((win_start_str, win_end_str))

        # Repository method:
        # def find_time_conflicts(self, instructor_id: str, date: date, start_time: time, end_time: time) -> List[Tuple[str, str]]
        # Or use ConflictChecker service for booking conflicts

        # Verify conflict detection
        assert isinstance(availability_conflicts, list)

    def test_query_pattern_create_day_atomic(self, db: Session, test_instructor: User):
        """Document atomic day creation pattern (bitmap)."""
        from app.utils.bitset import bits_from_windows

        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=10)

        # Bitmap-era: create day with windows
        windows = [(time(14, 0).strftime("%H:%M:%S"), time(15, 0).strftime("%H:%M:%S"))]
        bits = bits_from_windows(windows)

        day_row = AvailabilityDay(
            instructor_id=instructor_id,
            day_date=target_date,
            bits=bits,
        )
        db.add(day_row)
        db.flush()

        # Repository method:
        # def save_day_bits(self, instructor_id: str, date: date, bits: bytes) -> None
        # Or use AvailabilityService.save_week_bits for week-level operations

        assert day_row.instructor_id == instructor_id
        assert day_row.day_date == target_date
        assert day_row.bits is not None
