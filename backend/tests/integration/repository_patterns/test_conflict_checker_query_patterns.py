# backend/tests/integration/repository_patterns/test_conflict_checker_query_patterns.py
"""
Document all query patterns used in ConflictChecker.

This serves as the specification for the ConflictCheckerRepository
that will be implemented in the repository pattern.

UPDATED FOR CLEAN ARCHITECTURE: All conflict checking now uses Booking's
own fields (booking_date, start_time, end_time) without any reference to
availability slots. This reflects the complete separation of layers.
"""

from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.availability import BlackoutDate
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User


class TestConflictCheckerQueryPatterns:
    """Document every query pattern that needs repository implementation."""

    def test_query_pattern_check_booking_conflicts(
        self, db: Session, test_instructor_with_availability: User, test_booking: Booking
    ):
        """Document the query pattern for booking conflicts using booking fields directly."""
        instructor_id = test_instructor_with_availability.id
        check_date = test_booking.booking_date

        # Document the exact query pattern - NO SLOT JOINS
        query = (
            db.query(Booking)
            .options(joinedload(Booking.student), joinedload(Booking.instructor))
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == check_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
        )

        bookings = query.all()

        # Repository method signature:
        # def get_bookings_for_conflict_check(self, instructor_id: int, check_date: date,
        #                                    exclude_booking_id: Optional[int] = None) -> List[Booking]

        # Verify the query works without slot references
        assert len(bookings) >= 0
        for booking in bookings:
            assert booking.instructor_id == instructor_id
            assert booking.booking_date == check_date
            assert booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]
            # These fields exist directly on booking now
            assert hasattr(booking, "start_time")
            assert hasattr(booking, "end_time")

    def test_query_pattern_get_bookings_for_date(
        self, db: Session, test_instructor_with_availability: User, test_booking: Booking
    ):
        """Document query pattern for getting bookings on a specific date."""
        instructor_id = test_instructor_with_availability.id
        target_date = test_booking.booking_date

        # Direct query on bookings table - no slot references
        bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .order_by(Booking.start_time)
            .all()
        )

        # Repository method:
        # def get_bookings_for_date(self, instructor_id: int, target_date: date) -> List[Booking]

        assert len(bookings) >= 1  # We have test_booking
        for booking in bookings:
            assert booking.instructor_id == instructor_id
            assert booking.booking_date == target_date
            # Booking has its own time fields
            assert hasattr(booking, "start_time")
            assert hasattr(booking, "end_time")

    def test_query_pattern_get_bookings_for_week(
        self, db: Session, test_instructor_with_availability: User, test_booking: Booking
    ):
        """Document query pattern for weekly bookings."""
        instructor_id = test_instructor_with_availability.id
        week_start = test_booking.booking_date - timedelta(days=test_booking.booking_date.weekday())
        week_dates = [week_start + timedelta(days=i) for i in range(7)]

        # Direct query on bookings - no slot joins
        bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date.in_(week_dates),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .order_by(Booking.booking_date, Booking.start_time)
            .all()
        )

        # Repository method:
        # def get_bookings_for_week(self, instructor_id: int, week_dates: List[date]) -> List[Booking]

        assert len(bookings) >= 1
        for booking in bookings:
            assert booking.booking_date in week_dates
            assert booking.instructor_id == instructor_id

    def test_query_pattern_check_blackout_date(self, db: Session, test_instructor: User):
        """Document query pattern for blackout date checking."""
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=30)

        # Add a test blackout date first
        blackout = BlackoutDate(instructor_id=instructor_id, date=target_date, reason="Test blackout")
        db.add(blackout)
        db.commit()

        # Document the query pattern (unchanged)
        blackout_check = (
            db.query(BlackoutDate)
            .filter(BlackoutDate.instructor_id == instructor_id, BlackoutDate.date == target_date)
            .first()
        )

        # Repository method:
        # def get_blackout_date(self, instructor_id: int, target_date: date) -> Optional[BlackoutDate]

        assert blackout_check is not None
        assert blackout_check.date == target_date

    def test_query_pattern_check_minimum_advance_booking(self, db: Session, test_instructor: User):
        """Document query pattern for instructor profile validation."""
        instructor_id = test_instructor.id

        # Document the instructor profile query (unchanged)
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()

        # Repository method:
        # def get_instructor_profile(self, instructor_id: int) -> Optional[InstructorProfile]

        assert profile is not None
        assert hasattr(profile, "min_advance_booking_hours")
        assert hasattr(profile, "buffer_time_minutes")

    def test_query_pattern_validate_service_constraints(self, db: Session, test_instructor: User):
        """Document query pattern for service validation."""
        # Get an active service
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        if service:
            service_id = service.id

            # Document the service validation query (unchanged)
            service_check = db.query(Service).filter(Service.id == service_id, Service.is_active == True).first()

            # Repository method:
            # def get_active_service(self, service_id: int) -> Optional[Service]

            assert service_check is not None
            assert service_check.is_active == True

    def test_query_pattern_complex_booking_validation(self, db: Session, test_instructor_with_availability: User):
        """Document combined query patterns for comprehensive validation."""
        instructor_id = test_instructor_with_availability.id

        # 1. Get instructor profile (unchanged)
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()

        # 2. Get blackout dates for date range (unchanged)
        date_range_start = date.today()
        date_range_end = date.today() + timedelta(days=7)

        blackouts = (
            db.query(BlackoutDate)
            .filter(
                BlackoutDate.instructor_id == instructor_id, BlackoutDate.date.between(date_range_start, date_range_end)
            )
            .all()
        )

        # 3. Get existing bookings for conflict checking - NO SLOT JOINS
        existing_bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date.between(date_range_start, date_range_end),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .all()
        )

        # Repository methods needed:
        # def get_instructor_profile(self, instructor_id: int) -> Optional[InstructorProfile]
        # def get_blackouts_in_range(self, instructor_id: int, start: date, end: date) -> List[BlackoutDate]
        # def get_bookings_in_range(self, instructor_id: int, start: date, end: date) -> List[Booking]

        assert profile is not None
        assert isinstance(blackouts, list)
        assert isinstance(existing_bookings, list)


class TestConflictCheckerComplexQueries:
    """Document the most complex query patterns for repository optimization."""

    def test_complex_pattern_instructor_booking_summary(self, db: Session, test_instructor_with_availability: User):
        """Document query for getting comprehensive instructor booking summary."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = date.today() + timedelta(days=7)

        # Query bookings directly without slot references
        summary = (
            db.query(
                Booking.booking_date,
                func.count(Booking.id).label("total_bookings"),
                func.sum(Booking.duration_minutes).label("total_minutes_booked"),
            )
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date.between(start_date, end_date),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .group_by(Booking.booking_date)
            .all()
        )

        # Repository method:
        # def get_instructor_booking_summary(self, instructor_id: int, start: date, end: date) -> List[BookingSummary]

        for row in summary:
            assert hasattr(row, "booking_date")
            assert hasattr(row, "total_bookings")
            assert hasattr(row, "total_minutes_booked")

    def test_complex_pattern_conflict_detection_with_details(
        self, db: Session, test_instructor_with_availability: User, test_booking: Booking
    ):
        """Document advanced conflict detection query with full booking details."""
        instructor_id = test_instructor_with_availability.id
        check_date = test_booking.booking_date

        # Direct booking query with related data - NO SLOT JOINS
        conflicts = (
            db.query(
                Booking.id,
                Booking.start_time,
                Booking.end_time,
                Booking.service_name,
                Booking.status,
                Booking.duration_minutes,
                User.full_name.label("student_name"),
                Service.skill.label("service_skill"),
            )
            .join(User, Booking.student_id == User.id)
            .join(Service, Booking.service_id == Service.id)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == check_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .all()
        )

        # Repository method:
        # def get_detailed_bookings_for_conflict_check(self, instructor_id: int, check_date: date) -> List[DetailedBookingData]

        for conflict in conflicts:
            assert hasattr(conflict, "student_name")
            assert hasattr(conflict, "service_skill")
            assert hasattr(conflict, "start_time")
            assert hasattr(conflict, "end_time")

    def test_complex_pattern_time_utilization_check(self, db: Session, test_instructor_with_availability: User):
        """Document query for checking time utilization efficiency."""
        instructor_id = test_instructor_with_availability.id

        # Query to analyze time utilization based on bookings only
        utilization = (
            db.query(
                Booking.booking_date,
                func.count(Booking.id).label("total_bookings"),
                func.sum(Booking.duration_minutes).label("total_minutes_booked"),
                func.min(Booking.start_time).label("earliest_booking"),
                func.max(Booking.end_time).label("latest_booking"),
            )
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date >= date.today() - timedelta(days=30),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .group_by(Booking.booking_date)
            .all()
        )

        # Repository method:
        # def get_time_utilization_stats(self, instructor_id: int, days_back: int = 30) -> List[UtilizationStats]

        for util in utilization:
            assert hasattr(util, "total_bookings")
            assert hasattr(util, "total_minutes_booked")
            assert hasattr(util, "earliest_booking")
            assert hasattr(util, "latest_booking")

    def test_query_pattern_instructor_bookings_for_date(self, db: Session, test_instructor_with_availability: User):
        """Document the exact query pattern used by the repository."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()

        # This matches the actual repository method
        bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_id,
                Booking.booking_date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .order_by(Booking.start_time)
            .all()
        )

        # Repository method:
        # def get_instructor_bookings_for_date(self, instructor_id: int, target_date: date) -> List[Booking]

        # Verify the bookings have all needed fields
        for booking in bookings:
            assert booking.instructor_id == instructor_id
            assert booking.booking_date == target_date
            assert hasattr(booking, "start_time")
            assert hasattr(booking, "end_time")
            assert hasattr(booking, "status")
