# backend/tests/integration/repository_patterns/test_week_operation_query_patterns.py
"""
Document all database query patterns used in WeekOperationService.

This serves as the specification for the WeekOperationRepository
that has been implemented in the repository pattern.

UPDATED FOR WORK STREAM #10: Single-table availability design.
- No more InstructorAvailability queries
- Direct slot operations only
- Simplified query patterns

UPDATED FOR WORK STREAM #9: Layer independence
- Bookings no longer reference slots
- Time-based operations instead of slot-based
"""

from datetime import date, time, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.week_operation_repository import WeekOperationRepository
from app.services.availability_service import AvailabilityService
from app.services.conflict_checker import ConflictChecker
from app.services.week_operation_service import WeekOperationService
from app.utils.bitset import windows_from_bits


class TestWeekOperationQueryPatterns:
    """Document query patterns that need repository support."""

    @pytest.fixture
    def service(self, db: Session):
        """Create WeekOperationService with dependencies."""
        availability_service = Mock(spec=AvailabilityService)
        conflict_checker = Mock(spec=ConflictChecker)
        availability_repository = AvailabilityRepository(db)
        week_operation_repository = WeekOperationRepository(db)
        return WeekOperationService(
            db,
            availability_service,
            conflict_checker,
            repository=week_operation_repository,
            availability_repository=availability_repository,
        )

    @pytest.fixture
    def repository(self, db: Session):
        """Create WeekOperationRepository for testing."""
        return WeekOperationRepository(db)

    def test_get_week_availability_pattern(self, db: Session):
        """Document pattern for getting all availability in a week (bitmap).

        Repository method signature:
        def get_week_rows(instructor_id: str, week_start: date) -> List[AvailabilityDay]
        Or via service: def get_week_availability(instructor_id: str, start_date: date) -> Dict[str, List[Dict[str, str]]]

        NOTE: Bitmap-only storage now. Use AvailabilityDayRepository or AvailabilityService.
        """
        instructor_id = generate_ulid()
        week_start = date(2025, 6, 23)  # Monday
        week_end = week_start + timedelta(days=6)

        # Bitmap-era: query AvailabilityDay rows for the week
        day_repo = AvailabilityDayRepository(db)
        rows = day_repo.get_week_rows(instructor_id, week_start)

        # Or via service for windows format:
        svc = AvailabilityService(db=db)
        week_map = svc.get_week_availability(instructor_id, week_start, use_cache=False)

        # Query pattern:
        # - Filter by instructor_id
        # - Filter by day_date range (week_start to week_end)
        # - Order by day_date
        # - No joins needed!

        assert isinstance(rows, list)
        assert isinstance(week_map, dict)
        # Verify all dates are within the week
        for day_date in week_map.keys():
            parsed_date = date.fromisoformat(day_date)
            assert week_start <= parsed_date <= week_end

    def test_bulk_create_slots_pattern(self, db: Session, repository: WeekOperationRepository):
        """Document pattern for bulk creating slots.

        Repository method signature:
        def bulk_create_slots(slots: List[Dict[str, any]]) -> int

        Uses bulk_insert_mappings for performance.
        """
        _slots_data = [
            {
                "instructor_id": 1,
                "specific_date": date(2025, 6, 23),  # FIXED: date → specific_date
                "start_time": time(9, 0),
                "end_time": time(10, 0),
            },
            {
                "instructor_id": 1,
                "specific_date": date(2025, 6, 23),  # FIXED: date → specific_date
                "start_time": time(10, 0),
                "end_time": time(11, 0),
            },
        ]

        # Pattern uses bulk_insert_mappings for best performance
        # No need for returned IDs
        # Direct insert into availability_slots table

    def test_delete_slots_by_dates_pattern(self, db: Session, service: WeekOperationService):
        """Document pattern for deleting slots by dates.

        This pattern is in AvailabilityRepository:
        def delete_slots_by_dates(instructor_id: int, dates: List[date]) -> int

        Simple DELETE with IN clause.
        """
        # Pattern for bulk delete:
        # DELETE FROM availability_slots
        # WHERE instructor_id = ? AND specific_date IN (?, ?, ?)

    def test_get_week_bookings_pattern(self, db: Session, repository: WeekOperationRepository):
        """Document pattern for getting bookings in a week.

        Repository method signature:
        def get_week_bookings_with_slots(instructor_id: int, week_dates: List[date]) -> Dict

        UPDATED: Work Stream #9 - Returns time ranges, not slot IDs
        """
        instructor_id = generate_ulid()
        week_dates = [date(2025, 6, 23) + timedelta(days=i) for i in range(7)]

        result = repository.get_week_bookings_with_slots(instructor_id, week_dates)

        # Simplified query pattern:
        # - Query bookings table directly
        # - Filter by instructor_id and dates
        # - Filter by status (CONFIRMED, COMPLETED)
        # - Return time ranges, not slot IDs

        assert isinstance(result, dict)
        # FIXED: No more booked_slot_ids - bookings are independent of slots
        assert "booked_time_ranges_by_date" in result
        assert "total_bookings" in result

    def test_get_bookings_in_range_pattern(self, db: Session, repository: WeekOperationRepository):
        """Document pattern for getting bookings in a date range.

        Repository method signature:
        def get_bookings_in_date_range(instructor_id: int, start_date: date, end_date: date) -> Dict

        UPDATED: Work Stream #9 - Returns bookings by date, not slot IDs
        """
        instructor_id = generate_ulid()
        start_date = date(2025, 6, 1)
        end_date = date(2025, 6, 30)

        result = repository.get_bookings_in_date_range(instructor_id, start_date, end_date)

        # Pattern includes:
        # - Direct query on bookings table
        # - Date range filtering
        # - Status filtering
        # - Grouping by date

        assert "bookings_by_date" in result
        # FIXED: No more booked_slot_ids - bookings are independent
        assert "total_bookings" in result

    def test_get_windows_with_booking_status_pattern(self, db: Session):
        """Document pattern for getting windows with booking status (bitmap).

        Repository method signature:
        def get_week_rows(instructor_id: str, week_start: date) -> List[AvailabilityDay]
        Then use ConflictChecker to check booking overlaps.

        UPDATED: Checks time overlaps with bookings, not slot IDs
        """
        from app.services.conflict_checker import ConflictChecker

        instructor_id = generate_ulid()
        target_date = date(2025, 6, 23)

        # Bitmap-era: get windows from AvailabilityDay
        day_repo = AvailabilityDayRepository(db)
        day_row = day_repo.get_day_bits(instructor_id, target_date)

        windows_with_status = []
        if day_row:
            windows = windows_from_bits(day_row)
            # Get booked times for the date
            conflict_checker = ConflictChecker(db)
            booked_times = conflict_checker.get_booked_times_for_date(instructor_id, target_date)

            # Check each window for booking overlap
            for start_str, end_str in windows:
                is_booked = False
                for booked_info in booked_times:
                    # booked_info has "start_time" and "end_time" as ISO format strings
                    booked_start_str = booked_info["start_time"]
                    booked_end_str = booked_info["end_time"]
                    # Convert to HH:MM:SS format for comparison
                    if "T" in booked_start_str:
                        booked_start_str = booked_start_str.split("T")[1].split("+")[0][:8]
                    if "T" in booked_end_str:
                        booked_end_str = booked_end_str.split("T")[1].split("+")[0][:8]
                    # Check for overlap
                    if start_str < booked_end_str and end_str > booked_start_str:
                        is_booked = True
                        break

                windows_with_status.append({
                    "start_time": start_str,
                    "end_time": end_str,
                    "is_booked": is_booked,
                })

        # Pattern:
        # 1. Get availability day bits for the date
        # 2. Convert bits to windows
        # 3. Get bookings for the same date/instructor
        # 4. Check time overlaps to determine if window has booking
        # 5. Return window info with is_booked flag

        assert isinstance(windows_with_status, list)
        if windows_with_status:
            assert "start_time" in windows_with_status[0]
            assert "end_time" in windows_with_status[0]
            assert "is_booked" in windows_with_status[0]

    def test_bulk_delete_slots_pattern(self, db: Session, repository: WeekOperationRepository):
        """Document pattern for bulk deleting slots.

        Repository method signature:
        def bulk_delete_slots(slot_ids: List[int]) -> int

        Uses IN clause for efficient deletion.
        Note: Still uses slot IDs for direct slot operations
        """
        # Pattern uses IN clause for bulk delete
        # DELETE FROM availability_slots WHERE id IN (?, ?, ?)
        # Returns count of deleted records
        # Uses synchronize_session=False for performance

    def test_delete_non_booked_slots_pattern(self, db: Session, repository: WeekOperationRepository):
        """Document pattern for deleting non-booked slots.

        Repository method signature:
        def delete_non_booked_slots(instructor_id: int, week_dates: List[date], booked_times: Dict[date, List[Dict]]) -> int

        UPDATED: Uses time ranges to determine which slots to keep
        """
        # Pattern:
        # 1. Get all slots for instructor/dates
        # 2. For each slot, check if its time overlaps with any booked time
        # 3. Delete slots that don't overlap with bookings
        #
        # This is more complex after Work Stream #9 since we can't just
        # use slot IDs, but maintains the same functionality

    def test_simple_slot_queries_pattern(self, db: Session, service: WeekOperationService):
        """Document simple slot query patterns.

        With single-table design, many queries are now simple:
        - No joins needed
        - Direct filters on availability_slots
        - Better performance
        """
        # Examples of simplified queries:
        # 1. Get slots by instructor and specific_date - simple WHERE clause
        # 2. Count slots - simple COUNT query
        # 3. Check slot exists - simple EXISTS query
        # 4. Delete by specific_date - simple DELETE with date filter

    def test_week_pattern_extraction_pattern(self, db: Session, service: WeekOperationService):
        """Document how week patterns are extracted from availability data.

        This is mostly business logic but shows how data is structured
        for pattern operations.
        """
        # Pattern groups availability by day name (Monday, Tuesday, etc.)
        # Used for applying patterns across different weeks
        # With single-table design, data comes directly from slots

    def test_no_cascade_operations_pattern(self, db: Session, service: WeekOperationService):
        """Document that cascade operations are no longer needed.

        Repository notes:
        1. No InstructorAvailability to cascade from
        2. Direct slot operations only
        3. Simpler transaction handling
        """
        # These patterns are NO LONGER NEEDED:
        # - Cascade delete from availability to slots
        # - Managing empty availability entries
        # - Two-step create operations

    def test_time_based_booking_queries(self, db: Session, repository: WeekOperationRepository):
        """Document time-based booking query patterns.

        Work Stream #9 means all booking queries are time-based:
        - No slot_id references
        - Check overlaps by comparing times
        - Return time ranges instead of slot IDs
        """
        # Example patterns:
        # 1. Find bookings overlapping with time range:
        #    WHERE booking_date = ? AND start_time < ? AND end_time > ?
        #
        # 2. Group bookings by time:
        #    Return {"09:00-10:00": booking_count, ...}
        #
        # 3. Check if time is booked:
        #    EXISTS query with time overlap check
