# backend/tests/integration/test_conflict_checker_query_patterns.py
"""
Document all query patterns used in ConflictChecker.

This serves as the specification for the ConflictCheckerRepository
that will be implemented in the repository pattern.
"""

from datetime import date, time, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from app.models.availability import AvailabilitySlot, BlackoutDate, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User


class TestConflictCheckerQueryPatterns:
    """Document every query pattern that needs repository implementation."""

    def test_query_pattern_check_booking_conflicts(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Document the complex JOIN query for booking conflicts."""
        instructor_id = test_instructor_with_availability.id
        check_date = test_booking.booking_date
        time(10, 0)
        time(12, 0)

        # Document the exact query pattern used in check_booking_conflicts
        query = (
            db.query(Booking)
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .join(
                InstructorAvailability,
                AvailabilitySlot.availability_id == InstructorAvailability.id,
            )
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                Booking.booking_date == check_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
        )

        bookings = query.all()

        # Repository method signature:
        # def get_bookings_for_conflict_check(self, instructor_id: int, check_date: date,
        #                                    exclude_slot_id: Optional[int] = None) -> List[Booking]

        # Verify the complex JOIN works
        assert len(bookings) >= 0
        for booking in bookings:
            assert booking.instructor_id == instructor_id
            assert booking.booking_date == check_date
            assert booking.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]

    def test_query_pattern_check_slot_availability(self, db: Session, test_instructor_with_availability: User):
        """Document query pattern for slot availability checking."""
        # Get a slot ID
        availability = (
            db.query(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        if availability and availability.time_slots:
            slot_id = availability.time_slots[0].id

            # Document the query pattern
            slot = (
                db.query(AvailabilitySlot)
                .options(joinedload(AvailabilitySlot.availability))
                .filter(AvailabilitySlot.id == slot_id)
                .first()
            )

            # Repository method:
            # def get_slot_with_availability(self, slot_id: int) -> Optional[AvailabilitySlot]

            assert slot is not None
            assert slot.availability is not None
            assert slot.availability.instructor_id == test_instructor_with_availability.id

    def test_query_pattern_get_booked_slots_for_date(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Document query pattern for getting booked slots on a specific date."""
        instructor_id = test_instructor_with_availability.id
        target_date = test_booking.booking_date

        # Document the complex query with multiple JOINs and field selection
        booked_slots = (
            db.query(
                AvailabilitySlot.id,
                AvailabilitySlot.start_time,
                AvailabilitySlot.end_time,
                Booking.id.label("booking_id"),
                Booking.student_id,
                Booking.service_name,
                Booking.status,
            )
            .join(Booking, AvailabilitySlot.id == Booking.availability_slot_id)
            .join(
                InstructorAvailability,
                AvailabilitySlot.availability_id == InstructorAvailability.id,
            )
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date == target_date,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .all()
        )

        # Repository method:
        # def get_booked_slots_for_date(self, instructor_id: int, target_date: date) -> List[BookedSlotData]

        assert len(booked_slots) >= 1  # We have test_booking
        for slot in booked_slots:
            assert hasattr(slot, "id")
            assert hasattr(slot, "booking_id")
            assert hasattr(slot, "student_id")

    def test_query_pattern_get_booked_slots_for_week(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Document query pattern for weekly booked slots."""
        instructor_id = test_instructor_with_availability.id
        week_start = test_booking.booking_date - timedelta(days=test_booking.booking_date.weekday())
        week_dates = [week_start + timedelta(days=i) for i in range(7)]

        # Document the week-based query pattern
        booked_slots = (
            db.query(
                InstructorAvailability.date,
                AvailabilitySlot.id,
                AvailabilitySlot.start_time,
                AvailabilitySlot.end_time,
                Booking.id.label("booking_id"),
                Booking.student_id,
                Booking.service_name,
                Booking.status,
            )
            .join(
                AvailabilitySlot,
                InstructorAvailability.id == AvailabilitySlot.availability_id,
            )
            .join(Booking, AvailabilitySlot.id == Booking.availability_slot_id)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date.in_(week_dates),
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .order_by(InstructorAvailability.date, AvailabilitySlot.start_time)
            .all()
        )

        # Repository method:
        # def get_booked_slots_for_week(self, instructor_id: int, week_dates: List[date]) -> List[WeeklyBookedSlotData]

        assert len(booked_slots) >= 1
        for slot in booked_slots:
            assert hasattr(slot, "date")
            assert slot.date in week_dates

    def test_query_pattern_find_overlapping_slots(self, db: Session, test_instructor_with_availability: User):
        """Document query pattern for finding overlapping slots."""
        instructor_id = test_instructor_with_availability.id
        target_date = date.today()
        start_time = time(10, 0)
        end_time = time(12, 0)

        # Document the overlapping slots query
        slots = (
            db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date == target_date,
            )
            .all()
        )

        # Repository method:
        # def get_slots_for_date(self, instructor_id: int, target_date: date) -> List[AvailabilitySlot]

        # Document the overlap logic (business logic that stays in service)
        overlapping = []
        for slot in slots:
            if slot.start_time < end_time and slot.end_time > start_time:
                overlapping.append(slot)

        # This demonstrates the separation: query in repository, overlap logic in service

    def test_query_pattern_check_blackout_date(self, db: Session, test_instructor: User):
        """Document query pattern for blackout date checking."""
        instructor_id = test_instructor.id
        target_date = date.today() + timedelta(days=30)

        # Add a test blackout date first
        blackout = BlackoutDate(instructor_id=instructor_id, date=target_date, reason="Test blackout")
        db.add(blackout)
        db.commit()

        # Document the query pattern
        blackout_check = (
            db.query(BlackoutDate)
            .filter(
                BlackoutDate.instructor_id == instructor_id,
                BlackoutDate.date == target_date,
            )
            .first()
        )

        # Repository method:
        # def get_blackout_date(self, instructor_id: int, target_date: date) -> Optional[BlackoutDate]

        assert blackout_check is not None
        assert blackout_check.date == target_date

    def test_query_pattern_check_minimum_advance_booking(self, db: Session, test_instructor: User):
        """Document query pattern for instructor profile validation."""
        instructor_id = test_instructor.id

        # Document the instructor profile query
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

            # Document the service validation query
            service_check = db.query(Service).filter(Service.id == service_id, Service.is_active == True).first()

            # Repository method:
            # def get_active_service(self, service_id: int) -> Optional[Service]

            assert service_check is not None
            assert service_check.is_active == True

    def test_query_pattern_complex_booking_validation(self, db: Session, test_instructor_with_availability: User):
        """Document combined query patterns for comprehensive validation."""
        instructor_id = test_instructor_with_availability.id

        # Document the pattern for getting all data needed for validation
        # This shows what repositories will need to provide efficiently

        # 1. Get instructor profile
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == instructor_id).first()

        # 2. Get blackout dates for date range
        date_range_start = date.today()
        date_range_end = date.today() + timedelta(days=7)

        blackouts = (
            db.query(BlackoutDate)
            .filter(
                BlackoutDate.instructor_id == instructor_id, BlackoutDate.date.between(date_range_start, date_range_end)
            )
            .all()
        )

        # 3. Get existing bookings for conflict checking
        existing_bookings = (
            db.query(Booking)
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
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

    def test_complex_pattern_instructor_availability_summary(
        self, db: Session, test_instructor_with_availability: User
    ):
        """Document query for getting comprehensive instructor availability status."""
        instructor_id = test_instructor_with_availability.id
        start_date = date.today()
        end_date = date.today() + timedelta(days=7)

        # Complex query that gets availability, bookings, and blackouts in one operation
        # This type of query would be optimized in repository layer

        from sqlalchemy import func

        summary = (
            db.query(
                InstructorAvailability.date,
                func.count(AvailabilitySlot.id).label("total_slots"),
                func.count(Booking.id).label("booked_slots"),
                func.count(BlackoutDate.id).label("blackout_count"),
            )
            .outerjoin(AvailabilitySlot, InstructorAvailability.id == AvailabilitySlot.availability_id)
            .outerjoin(
                Booking,
                and_(
                    AvailabilitySlot.id == Booking.availability_slot_id,
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                ),
            )
            .outerjoin(
                BlackoutDate,
                and_(BlackoutDate.instructor_id == instructor_id, BlackoutDate.date == InstructorAvailability.date),
            )
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date.between(start_date, end_date),
            )
            .group_by(InstructorAvailability.date)
            .all()
        )

        # Repository method:
        # def get_instructor_availability_summary(self, instructor_id: int, start: date, end: date) -> List[AvailabilitySummary]

        for row in summary:
            assert hasattr(row, "date")
            assert hasattr(row, "total_slots")
            assert hasattr(row, "booked_slots")

    def test_complex_pattern_conflict_detection_with_details(
        self, db: Session, test_instructor_with_availability: User, test_booking
    ):
        """Document advanced conflict detection query with full booking details."""
        instructor_id = test_instructor_with_availability.id
        check_date = test_booking.booking_date

        # Advanced query that gets conflicts with full student and service details
        conflicts = (
            db.query(
                Booking.id,
                Booking.start_time,
                Booking.end_time,
                Booking.service_name,
                Booking.status,
                User.full_name.label("student_name"),
                Service.skill.label("service_skill"),
                AvailabilitySlot.id.label("slot_id"),
            )
            .join(User, Booking.student_id == User.id)
            .join(Service, Booking.service_id == Service.id)
            .join(AvailabilitySlot, Booking.availability_slot_id == AvailabilitySlot.id)
            .join(InstructorAvailability, AvailabilitySlot.availability_id == InstructorAvailability.id)
            .filter(
                InstructorAvailability.instructor_id == instructor_id,
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
            assert hasattr(conflict, "slot_id")

    def test_complex_pattern_time_slot_efficiency_check(self, db: Session, test_instructor_with_availability: User):
        """Document query for checking slot utilization efficiency."""
        instructor_id = test_instructor_with_availability.id

        # Query to analyze slot utilization - useful for instructor dashboard
        from sqlalchemy import case, func

        utilization = (
            db.query(
                InstructorAvailability.date,
                func.count(AvailabilitySlot.id).label("available_slots"),
                func.sum(case((Booking.id.isnot(None), 1), else_=0)).label("booked_slots"),
                func.avg(func.extract("epoch", AvailabilitySlot.end_time - AvailabilitySlot.start_time) / 3600).label(
                    "avg_slot_duration_hours"
                ),
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
                InstructorAvailability.instructor_id == instructor_id,
                InstructorAvailability.date >= date.today() - timedelta(days=30),
            )
            .group_by(InstructorAvailability.date)
            .all()
        )

        # Repository method:
        # def get_slot_utilization_stats(self, instructor_id: int, days_back: int = 30) -> List[UtilizationStats]

        for util in utilization:
            assert hasattr(util, "available_slots")
            assert hasattr(util, "booked_slots")
